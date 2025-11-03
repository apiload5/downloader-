# ==============================
# SaveMedia Downloader Helper (Zero-Load Mode)
# Author: amir + GPT-5
# ==============================

import asyncio
from yt_dlp import YoutubeDL
from typing import Dict, Optional, Any

YDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "simulate": True,
    "forcejson": True,
    "restrictfilenames": True,
    "ignoreerrors": True,
    "nocheckcertificate": True,
    "geo_bypass": True,
    "source_address": "0.0.0.0",
}


async def extract_info(url: str) -> Dict[str, Any]:
    loop = asyncio.get_event_loop()

    def _run():
        with YoutubeDL(YDL_OPTS) as ydl:
            return ydl.extract_info(url, download=False)

    return await loop.run_in_executor(None, _run)


async def get_best_format_stream_url(url: str, format_id: Optional[str] = None) -> Dict[str, Any]:
    info = await extract_info(url)
    if not info:
        raise RuntimeError("Failed to fetch info from URL")

    formats = info.get("formats", [])
    if not formats:
        raise RuntimeError("No formats available")

    chosen = None

    if format_id:
        for f in formats:
            if f.get("format_id") == format_id:
                chosen = f
                break

    if not chosen:
        progressive = [f for f in formats if f.get("acodec") != "none" and f.get("vcodec") != "none"]
        if progressive:
            progressive.sort(key=lambda x: (x.get("height") or 0), reverse=True)
            chosen = progressive[0]

    if not chosen and formats:
        chosen = formats[0]

    if not chosen or not chosen.get("url"):
        raise RuntimeError("No playable format found")

    ext = chosen.get("ext", "mp4")
    safe_title = (info.get("title") or "video").replace("/", "_").replace("\\", "_")

    return {
        "url": chosen.get("url"),
        "ext": ext,
        "format_id": chosen.get("format_id"),
        "filesize": chosen.get("filesize") or chosen.get("filesize_approx"),
        "filename": f"{safe_title}.{ext}",
    }
    
