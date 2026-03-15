# agent.py
#
# THIS IS THE MCP CLIENT + GEMINI AGENT
# Using Vertex AI (GCP service account) instead of simple API key
#
# Only difference from before:
#   Before → genai.configure(api_key=...)
#   Now    → vertexai.init(project=..., location=..., credentials=...)
#
# MCP Client logic is identical — servers don't know or care which AI you use

import asyncio
import json
import os
import sys
from pathlib import Path

# Vertex AI imports (replaces google.generativeai)
import vertexai
from vertexai.generative_models import (
    GenerativeModel,
    Tool,
    FunctionDeclaration,
    Part,
    Content
)
from google.oauth2 import service_account

# MCP imports
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv


# ── where are the server scripts? ────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
CV_SERVER  = str(BASE_DIR / "mcp_server_cv.py")
JOB_SERVER = str(BASE_DIR / "mcp_server_jobs.py")

# ── Vertex AI setup using service account JSON ────────────────────────────────
# This is the ONLY thing that changes vs simple API key version

CREDENTIALS_FILE = str(BASE_DIR / "service-account.json")
GCP_PROJECT      = os.getenv("GCP_PROJECT_ID")
GCP_LOCATION     = os.getenv("GCP_LOCATION", "us-central1")

# load service account credentials from JSON file
credentials = service_account.Credentials.from_service_account_file(
    CREDENTIALS_FILE,
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)

# initialize Vertex AI with your GCP project + credentials
vertexai.init(
    project=GCP_PROJECT,
    location=GCP_LOCATION,
    credentials=credentials
)

# ── helper: convert MCP tool → Vertex AI FunctionDeclaration ─────────────────
# Vertex AI uses FunctionDeclaration instead of dict like simple Gemini API
# But the data is identical — just wrapped differently

def clean_schema_for_vertexai(schema: dict) -> dict:
    """
    Vertex AI's protobuf is strict about what it accepts in schemas.
    It rejects:
      - enum with integer values (only string enums allowed)
      - $schema key
      - additionalProperties key
      - default key inside properties
    
    This function recursively cleans the schema.
    """
    if not isinstance(schema, dict):
        return schema

    cleaned = {}

    for key, value in schema.items():
        # skip keys Vertex AI rejects entirely
        if key in ["$schema", "additionalProperties", "default"]:
            continue

        # skip enum with integer values — Vertex AI only allows string enums
        # our max_days_old enum is integers [1,2,5,10...] — must remove it
        if key == "enum":
            continue

        # recursively clean nested properties
        if key == "properties" and isinstance(value, dict):
            cleaned["properties"] = {
                prop_name: clean_schema_for_vertexai(prop_schema)
                for prop_name, prop_schema in value.items()
            }

        # recursively clean items (for array types)
        elif key == "items" and isinstance(value, dict):
            cleaned["items"] = clean_schema_for_vertexai(value)

        else:
            cleaned[key] = value

    return cleaned


def mcp_tool_to_vertexai(tool) -> FunctionDeclaration:
    """
    INPUT — MCP Tool (what server sent to MCP Client):
        tool.name        = "search_jobs_by_skills"
        tool.description = "Search for jobs..."
        tool.inputSchema = { "type": "object", "properties": {...} }

    MCP Client translates this into Vertex AI FunctionDeclaration
    and gives it to Gemini as a menu card so Gemini knows what tools exist.

    OUTPUT — Vertex AI FunctionDeclaration (what Gemini reads):
        FunctionDeclaration(
            name="search_jobs_by_skills",
            description="Search for jobs...",
            parameters={ "type": "object", "properties": {...} }
        )

    Gemini reads this menu, then TELLS the MCP Client:
        "I want to call search_jobs_by_skills with these args"

    MCP Client then routes that call back to the correct server.
    Gemini never calls the server directly. Ever.
    """
    schema = dict(tool.inputSchema or {})

    # clean schema recursively — removes enum integers, $schema, etc.
    schema = clean_schema_for_vertexai(schema)

    return FunctionDeclaration(
        name=tool.name,
        description=tool.description or "",
        parameters=schema
    )
    
# ── MAIN AGENT FUNCTION ───────────────────────────────────────────────────────

async def run_job_agent(location: str, max_days_old: int = None, cv_path: str = None) -> dict:
    """
    Full agent flow:
    1. Connect to both MCP servers
    2. Collect all tools from both servers
    3. Pass tools + prompt to Gemini via Vertex AI
    4. Gemini calls tools → MCP Client routes to correct server
    5. Return ranked job matches
    """

    time_filter_text = (
        f"Only show jobs posted in the last {max_days_old} days."
        if max_days_old
        else "Show jobs from any time."
    )

    user_prompt = f"""
You are a job matching agent. Find the best matching jobs for this candidate.

Follow these steps IN ORDER:
1. Call get_cv_skills() to get the candidate's technical skills
2. Call get_cv_preferences() to get preferred job titles and location
3. Call search_jobs_by_skills() using top skills and location="{location}", count=20
4. Call search_jobs_by_title() for each preferred job title with location="{location}", count=20
5. Analyze ALL jobs found, rank the top 10 by match quality against the CV
6. Return ONLY this exact JSON structure, no extra text:

{{
    "candidate_name": "...",
    "search_location": "{location}",
    "time_filter": "{time_filter_text}",
    "total_jobs_analyzed": 0,
    "top_matches": [
        {{
            "rank": 1,
            "title": "...",
            "company": "...",
            "location": "...",
            "match_score": 85,
            "match_reason": "Matches your Python, FastAPI, Kubernetes skills",
            "salary": "...",
            "url": "...",
            "posted": "..."
        }}
    ],
    "summary": "Found X jobs, top match is Y at Z company"
}}

IMPORTANT: Return exactly 10 items in top_matches, ranked 1 to 10.
{time_filter_text}
Search location: {location}
"""

    # ── Step 1: Launch both MCP servers ──────────────────────────────────────
    # Windows needs env vars explicitly passed to subprocess
    # env=None means the subprocess gets NO environment — dotenv won't work
    current_env = os.environ.copy()

    # inject the user's cv path into the CV server's environment
    # CV server reads CV_PATH env var to know which cv.json to load
    if cv_path:
        current_env["CV_PATH"] = cv_path

    cv_server_params = StdioServerParameters(
        command=sys.executable,
        args=[CV_SERVER],
        env=current_env      # ← CV_PATH is now inside this env
    )

    job_server_params = StdioServerParameters(
        command=sys.executable,
        args=[JOB_SERVER],
        env=current_env      # ← same here
    )

    async with stdio_client(cv_server_params) as (cv_read, cv_write), \
               stdio_client(job_server_params) as (job_read, job_write):

        async with ClientSession(cv_read, cv_write) as cv_session, \
                   ClientSession(job_read, job_write) as job_session:

            # MCP handshake with both servers
            await cv_session.initialize()
            await job_session.initialize()

            # ── Step 2: Collect tools from both servers ───────────────────────
            cv_tools_result  = await cv_session.list_tools()
            job_tools_result = await job_session.list_tools()

            cv_tools  = cv_tools_result.tools
            job_tools = job_tools_result.tools

            cv_tool_names  = [t.name for t in cv_tools]
            job_tool_names = [t.name for t in job_tools]

            print(f"✅ CV Server tools:   {cv_tool_names}")
            print(f"✅ Jobs Server tools: {job_tool_names}")

            # ── Step 3: Convert to Vertex AI format ───────────────────────────
            all_declarations = [
                mcp_tool_to_vertexai(t)
                for t in cv_tools + job_tools
            ]

            # wrap in Vertex AI Tool object
            vertex_tool = Tool(function_declarations=all_declarations)

            # ── Step 4: Initialize Gemini via Vertex AI ───────────────────────
            model = GenerativeModel(
                model_name="gemini-2.0-flash-001",
                tools=[vertex_tool]
            )

            # start conversation history
            # Vertex AI uses Content/Part objects for message history
            chat_history = []

            # send first message
            print("\n🤖 Gemini starting agent loop...\n")

            first_content = Content(
                role="user",
                parts=[Part.from_text(user_prompt)]
            )
            chat_history.append(first_content)

            response = await asyncio.to_thread(
                model.generate_content,
                chat_history
            )

            # add response to history
            chat_history.append(response.candidates[0].content)

            # ── Step 5: Agentic tool call loop ────────────────────────────────
            max_rounds = 10
            round_num  = 0

            while round_num < max_rounds:
                round_num += 1

                # check if Gemini wants to call tools
                tool_calls = []
                for part in response.candidates[0].content.parts:
                    if (hasattr(part, "function_call") 
                            and part.function_call is not None 
                            and part.function_call.name):
                        tool_calls.append(part.function_call)

                # no tool calls = Gemini finished, has final text answer
                if not tool_calls:
                    break

                # execute each tool call
                tool_response_parts = []

                for fc in tool_calls:
                    tool_name = fc.name
                    tool_args = dict(fc.args)

                    print(f"  → Gemini calling: {tool_name}({tool_args})")

                    # MCP Client routing 
                    # route to the correct server based on which owns this tool

                    if tool_name in cv_tool_names:
                        # CV server owns this tool
                        mcp_result = await cv_session.call_tool(tool_name, tool_args)

                    elif tool_name in job_tool_names:
                        # Jobs server owns this tool
                        # inject time filter if user selected one
                        if max_days_old and tool_name in [
                            "search_jobs_by_skills",
                            "search_jobs_by_title"
                        ]:
                            tool_args.setdefault("max_days_old", int(max_days_old))

                        mcp_result = await job_session.call_tool(tool_name, tool_args)

                    else:
                        mcp_result = type("R", (), {
                            "content": [type("C", (), {"text": json.dumps({"error": f"Unknown tool: {tool_name}"})})()]
                        })()

                    # extract text from MCP response
                    result_text = ""
                    for content in mcp_result.content:
                        if hasattr(content, "text"):
                            result_text += content.text

                    print(f"  ← Got: {result_text[:120]}...")

                    # package as Vertex AI function response part
                    tool_response_parts.append(
                        Part.from_function_response(
                            name=tool_name,
                            response={"result": result_text}
                        )
                    )

                # send tool results back to Gemini
                tool_content = Content(
                    role="user",
                    parts=tool_response_parts
                )
                chat_history.append(tool_content)

                response = await asyncio.to_thread(
                    model.generate_content,
                    chat_history
                )

                chat_history.append(response.candidates[0].content)

            # ── Step 6: Extract final JSON answer ─────────────────────────────
            final_text = ""
            for part in response.candidates[0].content.parts:
                if hasattr(part, "text") and part.text:
                    final_text += part.text

            # strip markdown code fences if Gemini added them
            final_text = final_text.strip()
            for fence in ["```json", "```"]:
                if final_text.startswith(fence):
                    final_text = final_text[len(fence):]
            if final_text.endswith("```"):
                final_text = final_text[:-3]
            final_text = final_text.strip()

            try:
                return json.loads(final_text)
            except json.JSONDecodeError:
                return {
                    "error": "Could not parse Gemini response",
                    "raw":   final_text
                }


# ── quick test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    async def test():
        print("🔍 Job Agent — Vertex AI Edition")
        print("   Location:   Munich")
        print("   Time filter: last 5 days")
        print("=" * 50)

        result = await run_job_agent(
            location="Munich",
            max_days_old=5
        )

        print("\n📋 FINAL RESULT:")
        print(json.dumps(result, indent=2))

    asyncio.run(test())