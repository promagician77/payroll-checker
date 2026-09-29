"""FastAPI app. Files are checked in memory and never written to disk."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .rules import validate
from .settings import Settings

MAX_BYTES = 10 * 1024 * 1024
WEB = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="Payroll file check", docs_url="/api/docs", openapi_url="/api/openapi.json")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/settings")
def default_settings():
    return Settings.load().as_dict()


@app.post("/api/validate")
async def validate_file(file: UploadFile = File(...), settings: str | None = Form(None)):
    raw = await file.read()
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "The file is over 10 MB. Split it or raise MAX_BYTES in app/main.py.")
    try:
        overrides = json.loads(settings) if settings else None
        s = Settings.load(overrides)
    except (ValueError, TypeError) as e:
        raise HTTPException(400, f"Settings couldn't be read: {e}")
    result = validate(raw, s)
    result["file"]["name"] = file.filename
    return result


# Local use: the same app serves the page. On Vercel, the page is served as static files.
if WEB.exists():
    app.mount("/web", StaticFiles(directory=WEB), name="web")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(WEB / "index.html")
