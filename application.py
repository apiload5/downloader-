# ==============================
# SaveMedia Backend (Direct Download Mode)
# Author: Muhammad Amir Khursheed Ahmed Khan [Ticnodeveloper]
# Updated with GPT-5
# ==============================

import os
import asyncio
import time
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
application = FastAPI(title="SaveMedia Backend (Direct Mode)", version="2.0")

# ✅ CORS Middleware
application.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://crispy0921.blogspot.com",
        "https://savemedia.online",
        "https://ticnotester.blogspot.com",
        "*"  # for testing; remove in production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------
# Simple Rate Limiter
# ------------------------------
ip_requests: Dict[str, List[float]] = {}
download_sem = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)


class InfoRequest(BaseModel):
    url: str


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
# Root Route
# ------------------------------
@application.get("/")
async def home():
    return {"status": "ok", "message": "SaveMedia Direct Link Backend running fine"}


# ------------------------------
# Video Info Endpoint
# ------------------------------
@application.post("/api/info")
async def info(req: Request, body: InfoRequest):
    client_ip = _client_ip(req)
    rate_limit_check(client_ip)
    url = (body.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL required")

    print(f"[INFO] Fetching info for: {url}", flush=True)
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
# Direct Download Link Endpoint (Smart Mode)
# ------------------------------
@application.api_route("/api/download", methods=["GET", "POST"])
async def download(req: Request, url: str = "", format_id: Optional[str] = None, mode: str = "json"):
    """
    Returns either:
    - JSON response (for app use)
    - 302 Redirect (for browser download) when ?mode=redirect or body.mode="redirect"
    """
    client_ip = _client_ip(req)
    rate_limit_check(client_ip)

    # Read URL and parameters
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
        print(f"[DIRECT LINK] Fetching for: {url} (format={format_id}, mode={mode})", flush=True)
        stream_info = await get_best_format_stream_url(url, format_id=format_id)
        if not stream_info or "url" not in stream_info:
            raise HTTPException(status_code=500, detail="Cannot fetch direct media link")

        direct_url = stream_info["url"]
        filename = stream_info["filename"]

        # ✅ Force download if mode=redirect
        if str(mode).lower() == "redirect":
            response_headers = {
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            }
            return RedirectResponse(
                url=direct_url,
                status_code=302,
                headers=response_headers
            )

        # Otherwise, return JSON
        return JSONResponse({
            "status": "success",
            "direct_url": direct_url,
            "filename": filename,
            "ext": stream_info.get("ext"),
            "filesize": stream_info.get("filesize"),
            "mode": "json"
        })

    finally:
        try:
            download_sem.release()
        except Exception:
            pass


# ------------------------------
# Run Locally or Deploy on Server
# ------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("application:application", host="0.0.0.0", port=8080, reload=False)
