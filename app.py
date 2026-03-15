from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
import uvicorn

from agent import run_job_agent

app = FastAPI()

# ── use absolute path so it works from any directory ─────────────────────────
BASE_DIR    = Path(__file__).parent
STATIC_DIR  = BASE_DIR / "static"
INDEX_FILE  = STATIC_DIR / "index.html"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class SearchRequest(BaseModel):
    location: str
    max_days_old: Optional[int] = None


@app.post("/search")
async def search_jobs(request: SearchRequest):
    result = await run_job_agent(
        location=request.location,
        max_days_old=request.max_days_old
    )
    return result


@app.get("/")
async def root():
    return FileResponse(str(INDEX_FILE))


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)