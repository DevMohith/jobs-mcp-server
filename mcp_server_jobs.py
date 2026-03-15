# mcp_server_jobs.py
#
# THIS IS MCP SERVER 2 — the Jobs Server
# Left side  → speaks MCP (to MCP Client / Gemini)
# Right side → speaks REST HTTP (to Adzuna API)

import json
import asyncio
import os
import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types
from dotenv import load_dotenv

load_dotenv()

app = Server("jobs-server")

ADZUNA_APP_ID  = os.getenv("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY")
ADZUNA_BASE    = "https://api.adzuna.com/v1/api/jobs/de/search/1"


# RIGHT SIDE: talks to Adzuna REST API 

async def call_adzuna(params: dict) -> dict:
    params = dict(params)  # copy so we don't mutate original
    count = int(params.pop("count", 10))

    base_params = {
        "app_id":           ADZUNA_APP_ID,
        "app_key":          ADZUNA_APP_KEY,
        "results_per_page": count,
        "content-type":     "application/json"
    }

    # cast max_days_old to int if present
    if "max_days_old" in params:
        params["max_days_old"] = int(params["max_days_old"])

    base_params.update(params)

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(ADZUNA_BASE, params=base_params)

        # return empty result instead of crashing on 500
        if response.status_code == 500:
            return {"results": [], "count": 0, "error": "Adzuna returned 500"}

        response.raise_for_status()
        return response.json()


def format_job(job: dict) -> dict:
    return {
        "id":          job.get("id", ""),
        "title":       job.get("title", ""),
        "company":     job.get("company", {}).get("display_name", "Unknown"),
        "location":    job.get("location", {}).get("display_name", "Unknown"),
        "description": job.get("description", "")[:500],
        "salary_min":  job.get("salary_min", "Not specified"),
        "salary_max":  job.get("salary_max", "Not specified"),
        "url":         job.get("redirect_url", ""),
        "created":     job.get("created", ""),
        "category":    job.get("category", {}).get("label", "")
    }


# TOOL REGISTRY

# this is the shared inputSchema block for time filter
# same for both search tools — defined once, reused twice
TIME_FILTER_SCHEMA = {
    "max_days_old": {
        "type": "integer",
        "description": (
            "Filter jobs by how recently they were posted. "
            "1=last 24hrs, 2=last 2 days, 5=last 5 days, "
            "10=last 10 days, 15=last 15 days, 18=last 18 days, 24=last 24 days. "
            "Omit for no filter (all jobs)."
        ),
        "enum": [1, 2, 5, 10, 15, 18, 24]
    }
}


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [

        types.Tool(
            name="search_jobs_by_skills",
            description=(
                "Search for jobs on Adzuna matching a list of skills. "
                "Use this after reading the candidate's CV skills. "
                "Returns jobs with title, company, location, salary, and URL."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "skills": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Top skills to search for e.g. ['Python', 'FastAPI', 'Kubernetes']"
                    },
                    "location": {
                        "type": "string",
                        "description": "City or country e.g. 'Munich', 'Berlin', 'Deutschland'"
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of jobs to return (default 10, max 20)",
                        "default": 10
                    },
                    **TIME_FILTER_SCHEMA   # ← filter injected here
                },
                "required": ["skills", "location"]
            }
        ),

        types.Tool(
            name="search_jobs_by_title",
            description=(
                "Search jobs by exact job title. Use when you know the role name. "
                "e.g. 'AI Engineer', 'ML Engineer', 'Platform Engineer'."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Job title to search for"
                    },
                    "location": {
                        "type": "string",
                        "description": "City or country to search in"
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of jobs to return",
                        "default": 10
                    },
                    **TIME_FILTER_SCHEMA   # ← filter injected here too
                },
                "required": ["title", "location"]
            }
        ),

        types.Tool(
            name="get_job_detail",
            description=(
                "Get full details of a specific job by its ID. "
                "Use after search to get the full description "
                "for proper CV matching."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "job_id": {
                        "type": "string",
                        "description": "Job ID from search results"
                    }
                },
                "required": ["job_id"]
                # no time filter here — detail fetch doesn't need it
            }
        )
    ]


# TOOL HANDLERS 

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:

    #tool 1: search_jobs_by_skills
    if name == "search_jobs_by_skills":
        skills       = arguments.get("skills", [])
        location     = arguments.get("location", "Deutschland")
        count        = arguments.get("count", 10)
        max_days_old = arguments.get("max_days_old")
        if max_days_old is not None:
            max_days_old = int(max_days_old)

        query = " ".join(skills[:5])  # top 5 skills → search string

        params = {
            "what":  query,
            "where": location,
            "count": count
        }

        # only add time filter if user actually selected one
        if max_days_old:
            params["max_days_old"] = max_days_old

        data = await call_adzuna(params)
        jobs = [format_job(j) for j in data.get("results", [])]

        result = {
            "query_used":   query,
            "location":     location,
            "filter":       f"last {max_days_old} days" if max_days_old else "all time",
            "total_found":  data.get("count", 0),
            "jobs":         jobs
        }

        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    # ── tool 2: search_jobs_by_title ─────────────────────────────────────────
    elif name == "search_jobs_by_title":
        title        = arguments.get("title", "")
        location     = arguments.get("location", "Deutschland")
        count        = arguments.get("count", 10)
        max_days_old = arguments.get("max_days_old")
        if max_days_old is not None:
            max_days_old = int(max_days_old)

        params = {
            "what":  title,
            "where": location,
            "count": count
        }

        if max_days_old:
            params["max_days_old"] = max_days_old

        data = await call_adzuna(params)
        jobs = [format_job(j) for j in data.get("results", [])]

        result = {
            "title_searched": title,
            "location":       location,
            "filter":         f"last {max_days_old} days" if max_days_old else "all time",
            "total_found":    data.get("count", 0),
            "jobs":           jobs
        }

        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    # tool 3: get_job_detail
    elif name == "get_job_detail":
        job_id = arguments.get("job_id", "")

        data = await call_adzuna({"what": job_id, "count": 1})
        jobs = data.get("results", [])

        if not jobs:
            result = {"error": f"Job {job_id} not found"}
        else:
            job = jobs[0]
            result = {
                "id":          job.get("id", ""),
                "title":       job.get("title", ""),
                "company":     job.get("company", {}).get("display_name", ""),
                "location":    job.get("location", {}).get("display_name", ""),
                "description": job.get("description", ""),
                "salary_min":  job.get("salary_min", "Not specified"),
                "salary_max":  job.get("salary_max", "Not specified"),
                "url":         job.get("redirect_url", ""),
                "category":    job.get("category", {}).get("label", "")
            }

        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    else:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Unknown tool: {name}"})
        )]


# START THE SERVER
async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())