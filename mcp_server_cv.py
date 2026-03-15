# mcp_server_cv.py
#
# THIS IS MCP SERVER 1 — the CV Server
#
# Its "real owner" is cv.json (your local file)
# It speaks MCP on the left (to your agent)
# It speaks plain file read on the right (to cv.json)
#
# It exposes 3 tools to Gemini:
#   - get_cv_skills()       → returns all your skills flat
#   - get_cv_summary()      → returns name, title, summary, experience
#   - get_cv_preferences()  → returns preferred job titles + location


import json
import asyncio
from pathlib import Path
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

app = Server("cv-server")

# where is the real owner (cv.json)?
CV_PATH = Path(__file__).parent / "cv.json"




# Step 1 — connect to source
# helper function to load the CV data from the JSON file
def load_cv():
    with open(CV_PATH, "r", encoding="utf-8") as f:
        return json.load(f)
    




# Step 2 — define tools (the menu)
# Tool registry
# This is what Gemini sees when it asks "what tools do you have?"
# Think of it as the MCP Server's menu card
@app.list_tools()
async def list_tools():
    return [
        types.Tool (
            name="get_cv_skills",
            description=(
                "Returns all technical skills from the candidate's CV as a flat list."
                "Use this first to understand what the candidate knows before searching jobs."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        
        types.Tool (
            name="get_cv_summary",
            description=(
                "Returns the candidate's full profile: name, title, summary, "
                "and work experience with bullet points."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        
        types.Tool (
            name="get_cv_preferences",
            description=(
                "Returns what kind of jobs the candidate is looking for:"
                "preferred job titles and preferred location."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    ]
    





# Step 3 — when called, read source, return that section
# Tool implementations - right side logic of mcP server it talks to cv.json
# When Gemini calls a tool, this runs.
@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    
    cv = load_cv()
    
    # tool 1 - get_cv_skills
    if name == "get_cv_skills":
        skills = cv["skills"]
        
        # flatten all skills into a single list
        all_skills = []
        for categeory, skill_list in skills.items():
            all_skills.extend(skill_list)
            
        result = {
            "all_skills": all_skills,
            "by_category": skills,
            "total": len(all_skills)
        }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
        
    # tool 2 - get_cv_summary
    elif name == "get_cv_summary":
        result = {
            "name": cv["name"],
            "title": cv["title"],
            "location": cv["location"],
            "summary": cv["summary"],
            "experience": cv["experience"],
            "projects": cv["projects"],
            "education": cv["education"]
        }

        return [types.TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
        
    # tool 3 - get_cv_preferences
    elif name == "get_cv_preferences":
        result = {
            "preferred_job_titles": cv["preferred_job_titles"],
            "preferred_location": cv["preferred_location"],
            "name": cv["name"]
        }

        return [types.TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]

    else:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Unknown tool: {name}"})
        )]
        
        
# start the server
# stdio = it communicates via standard input/output
# This is how MCP servers talk locally (the MCP Client launches this process)
async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())