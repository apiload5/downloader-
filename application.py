# ==============================
# SaveMedia Backend (AWS + Replit + Heroku Compatible)
# Author: Muhammad Amir Khursheed Ahmed Khan [Ticnodeveloper]
# ==============================

import os
import asyncio
import time
import httpx
from typing import Optional, Dict, List
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
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
application = FastAPI(title="SaveMedia Backend", version="1.0")

# ✅ CORS Middleware
application.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://crispy0921.blogspot.com",
        "https://savemedia.online",
        "https://4f1afd56-6dff-4d5f-99c0-7d1702a92a3d-00-2qrni89n41qhi.sisko.replit.dev",
        "http://localhost:3000",
        "*"  # remove "*" after testing for security
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
        raise HTTPException(status_code=429, detail="Too many requests")
    history.append(now)
    ip_requests[client_ip] = history


# ------------------------------
# Routes
# ------------------------------
@application.get("/")
async def home():
    return {"status": "ok", "message": "SaveMedia Backend running fine"}


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

        # ✅ Filter: only video+audio formats + filesize in MB
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
# Download Endpoint
# ------------------------------
@application.api_route("/api/download", methods=["GET", "POST"])
async def download(req: Request, url: str = "", format_id: Optional[str] = None):
    client_ip = _client_ip(req)

    if req.method == "POST":
        try:
            body = await req.json()
            url = body.get("url") or url
            format_id = body.get("format_id") or format_id
        except Exception:
            form = await req.form()
            url = form.get("url") or url
            format_id = form.get("format_id") or format_id

    if not url:
        raise HTTPException(status_code=400, detail="URL required")

    rate_limit_check(client_ip)
    await download_sem.acquire()
    try:
        print(f"[DOWNLOAD] Resolving stream for: {url} (format={format_id})", flush=True)
        stream_info = await get_best_format_stream_url(url, format_id=format_id)
        if not stream_info or "url" not in stream_info:
            raise HTTPException(status_code=500, detail="Cannot fetch media stream")

        remote_url = stream_info["url"]
        filename = stream_info.get("filename", f"video.{stream_info.get('ext', 'mp4')}")

        async def stream_remote():
            timeout = httpx.Timeout(300.0, connect=60.0)
            headers = {"user-agent": "savemedia-backend/1.0"}
            try:
                async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
                    async with client.stream("GET", remote_url) as resp:
                        if resp.status_code >= 400:
                            yield b""
                            return
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            yield chunk
            except Exception as e:
                print("[ERROR] stream_remote:", repr(e), flush=True)

        response = StreamingResponse(stream_remote(), media_type="application/octet-stream")
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        return response
    finally:
        download_sem.release()


# ------------------------------
# Run Locally or on AWS / Replit / Heroku
# ------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("application:application", host="0.0.0.0", port=8080, reload=False)
