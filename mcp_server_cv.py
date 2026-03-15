# mcp_server_cv.py
#
# CV MCP Server — reads from a DYNAMIC cv path
# Path is passed via environment variable CV_PATH
# This allows each user session to have their own cv.json

import json
import asyncio
import os
from pathlib import Path
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

app = Server("cv-server")

def load_cv() -> dict:
    """
    Load CV from path specified in CV_PATH env var.
    Falls back to cv.json in same directory.
    """
    cv_path = os.environ.get("CV_PATH")
    if not cv_path:
        cv_path = str(Path(__file__).parent / "cv.json")
    with open(cv_path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_cv_skills",
            description=(
                "Returns all technical skills from the candidate's CV as a flat list. "
                "Use this first to understand what the candidate knows."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        types.Tool(
            name="get_cv_summary",
            description=(
                "Returns the candidate's full profile: name, title, summary, "
                "and work experience."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        types.Tool(
            name="get_cv_preferences",
            description=(
                "Returns preferred job titles and preferred location."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    cv = load_cv()

    if name == "get_cv_skills":
        all_skills = []
        for skill_list in cv["skills"].values():
            all_skills.extend(skill_list)
        result = {
            "all_skills":   all_skills,
            "by_category":  cv["skills"],
            "total":        len(all_skills)
        }

    elif name == "get_cv_summary":
        result = {
            "name":       cv["name"],
            "title":      cv["title"],
            "location":   cv["location"],
            "summary":    cv["summary"],
            "experience": cv["experience"],
            "projects":   cv["projects"],
            "education":  cv["education"]
        }

    elif name == "get_cv_preferences":
        result = {
            "preferred_job_titles": cv["preferred_job_titles"],
            "preferred_location":   cv["preferred_location"],
            "name":                 cv["name"]
        }

    else:
        result = {"error": f"Unknown tool: {name}"}

    return [types.TextContent(type="text", text=json.dumps(result, indent=2))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream,
                      app.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())