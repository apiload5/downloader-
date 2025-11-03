# ==============================
# SaveMedia Backend (Direct Download Mode + .bin Fallback)
# Author: Muhammad Amir Khursheed Ahmed Khan [Ticnodeveloper] + GPT-5
# ==============================

import os
import asyncio
import time
import httpx
from typing import Optional, Dict, List
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from downloader import extract_info, get_best_format_stream_url

# ------------------------------
# Load Environment Variables
# ------------------------------
load_dotenv()
API_ALLOW_HOST = os.getenv("API_ALLOW_HOST", "savemedia.online")
API_KEY = os.getenv("API_KEY", "")
MAX_CONCURRENT_DOWNLOADS = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "3"))
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "30"))

# ------------------------------
# Initialize FastAPI App
# ------------------------------
application = FastAPI(title="SaveMedia Backend (Direct Mode)", version="2.1")

application.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://crispy0921.blogspot.com",
        "https://savemedia.online",
        "http://localhost:3000",
        "*"  # disable for production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------
# Rate Limiter
# ------------------------------
ip_requests: Dict[str, List[float]] = {}
download_sem = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)


def _client_ip(req: Request) -> str:
    try:
        return req.client.host or "unknown"
    except Exception:
        return "unknown"


def rate_limit_check(client_ip: str):
    now = time.time()
    window = 60
    history = ip_requests.get(client_ip, [])
    history = [t for t in history if t > now - window]
    if len(history) >= RATE_LIMIT_PER_MIN:
        raise HTTPException(status_code=429, detail="Too many requests per minute")
    history.append(now)
    ip_requests[client_ip] = history


# ------------------------------
# Models
# ------------------------------
class InfoRequest(BaseModel):
    url: str


# ------------------------------
# Quick HEAD check helper
# ------------------------------
async def head_check(url: str, timeout: int = 8):
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            r = await client.head(url)
            return {
                "status_code": r.status_code,
                "content_type": r.headers.get("content-type"),
                "content_disposition": r.headers.get("content-disposition"),
            }
    except Exception:
        return None


# ------------------------------
# Routes
# ------------------------------
@application.get("/")
async def home():
    return {"status": "ok", "message": "SaveMedia Direct Link Backend running fine"}


@application.post("/api/info")
async def info(req: Request, body: InfoRequest):
    client_ip = _client_ip(req)
    rate_limit_check(client_ip)
    url = (body.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL required")

    try:
        info = await extract_info(url)
        formats = []
        for f in info.get("formats", []):
            if f.get("acodec") in [None, "none"]:
                continue
            quality = str(f.get("format_note") or f.get("height") or "Unknown")
            if quality.lower() in ["", "none", "unknown"]:
                quality = f"{f.get('height', '')}p" if f.get("height") else "Standard"

            size_bytes = f.get("filesize") or f.get("filesize_approx") or 0
            size_mb = round(size_bytes / (1024 * 1024), 2) if size_bytes else None
            size_label = f"{size_mb} MB" if size_mb else "N/A"

            formats.append({
                "format_id": f.get("format_id"),
                "ext": f.get("ext"),
                "quality": quality,
                "filesize": size_label,
            })

        return JSONResponse({
            "id": info.get("id"),
            "title": info.get("title"),
            "uploader": info.get("uploader"),
            "thumbnail": info.get("thumbnail"),
            "duration": info.get("duration"),
            "view_count": info.get("view_count"),
            "formats": formats
        })
    except Exception as e:
        print("[ERROR] info() exception:", repr(e), flush=True)
        raise HTTPException(status_code=500, detail="Failed to fetch info")


# ------------------------------
# Download Endpoint (.bin Support)
# ------------------------------
@application.api_route("/api/download", methods=["GET", "POST"])
async def download(req: Request, url: str = "", format_id: Optional[str] = None, mode: str = "json"):
    client_ip = _client_ip(req)
    rate_limit_check(client_ip)

    # read params
    if req.method == "POST":
        try:
            body = await req.json()
            url = body.get("url", url)
            format_id = body.get("format_id", format_id)
            mode = body.get("mode", mode)
        except Exception:
            pass
    else:
        url = url or req.query_params.get("url", "")
        format_id = format_id or req.query_params.get("format_id", None)
        mode = req.query_params.get("mode", mode)

    if not url:
        raise HTTPException(status_code=400, detail="URL required")

    await download_sem.acquire()
    try:
        stream_info = await get_best_format_stream_url(url, format_id=format_id)
        if not stream_info or "url" not in stream_info:
            raise HTTPException(status_code=500, detail="Cannot fetch direct media link")

        direct_url = stream_info["url"]
        filename = stream_info.get("filename") or f"media.{stream_info.get('ext','mp4')}"
        ext = stream_info.get("ext") or "mp4"

        # check remote headers
        head = await head_check(direct_url)
        remote_cd = head and head.get("content_disposition")
        remote_ct = head and head.get("content_type")
        remote_will_force_download = bool(remote_cd) or (remote_ct and not str(remote_ct).startswith("video/"))

        wants_redirect = str(mode).lower() == "redirect"

        # ✅ if redirect & remote already download-friendly
        if wants_redirect and remote_will_force_download:
            return RedirectResponse(url=direct_url, status_code=302)

        # ✅ if redirect but remote streams inline — suggest .bin file
        if wants_redirect and not remote_will_force_download:
            base, _ = os.path.splitext(filename)
            safe_filename = base + ".bin"
            headers = {
                "Content-Disposition": f'attachment; filename="{safe_filename}"',
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            }
            return RedirectResponse(url=direct_url, headers=headers, status_code=302)

        # ✅ JSON mode (normal)
        return JSONResponse({
            "status": "success",
            "direct_url": direct_url,
            "filename": filename,
            "ext": ext,
            "filesize": stream_info.get("filesize"),
            "mode": "json"
        })

    finally:
        download_sem.release()


# ------------------------------
# Run Locally
# ------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("application:application", host="0.0.0.0", port=8080, reload=False)
