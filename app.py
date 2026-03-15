# app.py
#
# FastAPI web server
# New endpoints:
#   POST /upload-cv  → receives .docx, parses it, saves user's cv.json
#   POST /search     → runs agent with user's cv.json
#   GET  /           → serves index.html

import uuid
import shutil
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn

from agent import run_job_agent
from parse_cv import parse_and_save

app = FastAPI()

BASE_DIR   = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
INDEX_FILE = STATIC_DIR / "index.html"

# folder where each user's parsed cv.json is stored
# each user gets a unique session_id subfolder
CV_STORE = BASE_DIR / "cv_store"
CV_STORE.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── upload CV endpoint ────────────────────────────────────────────────────────
@app.post("/upload-cv")
async def upload_cv(file: UploadFile = File(...)):
    """
    User uploads their .docx CV.
    We parse it, save cv.json, return a session_id.
    Browser stores session_id and sends it with every search.
    """

    # validate file type
    if not file.filename.endswith(".docx"):
        raise HTTPException(
            status_code=400,
            detail="Only .docx files are supported"
        )

    # create a unique folder for this user session
    session_id = str(uuid.uuid4())
    session_dir = CV_STORE / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    # save uploaded .docx
    docx_path = session_dir / "cv.docx"
    with open(docx_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # parse .docx → cv.json
    try:
        json_path = session_dir / "cv.json"
        cv = parse_and_save(str(docx_path), str(json_path))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Could not parse CV: {str(e)}"
        )

    return {
        "session_id":  session_id,
        "name":        cv.get("name", ""),
        "title":       cv.get("title", ""),
        "skills_count": sum(len(v) for v in cv.get("skills", {}).values()),
        "message":     "CV parsed successfully"
    }


# ── search endpoint ───────────────────────────────────────────────────────────
class SearchRequest(BaseModel):
    session_id:  str            # which user's cv.json to use
    location:    str
    max_days_old: Optional[int] = None


@app.post("/search")
async def search_jobs(request: SearchRequest):
    """
    Run job matching agent for a specific user's CV.
    """
    # find this user's cv.json
    cv_path = CV_STORE / request.session_id / "cv.json"

    if not cv_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Session not found. Please upload your CV first."
        )

    result = await run_job_agent(
        location=request.location,
        max_days_old=request.max_days_old,
        cv_path=str(cv_path)        # ← pass user's cv.json to agent
    )
    return result


@app.get("/")
async def root():
    return FileResponse(str(INDEX_FILE))


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)