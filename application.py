# ==============================
# SaveMedia Backend (Zero-Load Direct Download)
# Author: Muhammad Amir Khursheed Ahmed Khan [Ticnodeveroper] + GPT-5
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

# ✅ Safe FFmpeg setup (no crash on Railway)
try:
    import static_ffmpeg
    try:
        ffmpeg_path = static_ffmpeg.get_ffmpeg_path()
        if ffmpeg_path and os.path.exists(ffmpeg_path):
            os.environ["PATH"] += os.pathsep + ffmpeg_path
            print(f"[INFO] FFmpeg path added: {ffmpeg_path}", flush=True)
        else:
            print("[WARN] FFmpeg path empty or missing", flush=True)
    except Exception as inner_e:
        print(f"[WARN] static_ffmpeg path retrieval failed: {inner_e}", flush=True)
except ImportError:
    print("[WARN] static_ffmpeg not installed, skipping FFmpeg path setup", flush=True)

# ✅ Load .env variables
load_dotenv()

API_ALLOW_HOST = os.getenv("API_ALLOW_HOST", "savemedia.online")
API_KEY = os.getenv("API_KEY", "")
MAX_CONCURRENT_DOWNLOADS = int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "3"))
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "30"))

# ✅ FastAPI app
application = FastAPI(title="SaveMedia Backend", version="2.0")

# ✅ CORS setup
application.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://crispy0921.blogspot.com",
        "https://savemedia.online",
        "http://localhost:3000",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Rate limit + concurrency control
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

# ✅ Root test
@application.get("/")
async def home():
    return {"status": "ok", "message": "SaveMedia Zero-Load Backend running fine"}

# ✅ Info extractor
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
            size_bytes = f.get("filesize") or f.get("filesize_approx") or 0
            size_mb = round(size_bytes / (1024 * 1024), 2) if size_bytes else None
            formats.append({
                "format_id": f.get("format_id"),
                "ext": f.get("ext"),
                "quality": quality,
                "filesize": f"{size_mb} MB" if size_mb else "N/A",
            })

        return JSONResponse({
            "id": info.get("id"),
            "title": info.get("title"),
            "uploader": info.get("uploader"),
            "thumbnail": info.get("thumbnail"),
            "duration": info.get("duration"),
            "formats": formats,
        })
    except Exception as e:
        print("[ERROR] info() exception:", repr(e))
        raise HTTPException(status_code=500, detail="Failed to fetch info")

# ✅ Direct link provider
@application.api_route("/api/download", methods=["GET", "POST"])
async def download(req: Request, url: str = "", format_id: Optional[str] = None):
    client_ip = _client_ip(req)
    rate_limit_check(client_ip)

    if req.method == "POST":
        try:
            body = await req.json()
            url = body.get("url", url)
            format_id = body.get("format_id", format_id)
        except Exception:
            pass
    else:
        url = url or req.query_params.get("url", "")
        format_id = format_id or req.query_params.get("format_id", None)

    if not url:
        raise HTTPException(status_code=400, detail="URL required")

    await download_sem.acquire()
    try:
        stream_info = await get_best_format_stream_url(url, format_id=format_id)
        if not stream_info or "url" not in stream_info:
            raise HTTPException(status_code=500, detail="Cannot fetch media link")

        return JSONResponse({
            "status": "success",
            "direct_url": stream_info["url"],
            "filename": stream_info["filename"],
            "ext": stream_info["ext"],
            "filesize": stream_info.get("filesize"),
        })
    finally:
        download_sem.release()

# ✅ Redirect endpoint
@application.get("/api/direct")
async def force_download(file_url: str, filename: str = "video.mp4"):
    return RedirectResponse(
        url=file_url,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# ✅ Run (local dev mode)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("application:application", host="0.0.0.0", port=8080, reload=False)
