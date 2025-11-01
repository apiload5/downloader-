
# ==============================
# SaveMedia Downloader Helper
# Author: Muhammad Amir Khursheed Ahmed + GPT-5
# ==============================

import asyncio
from yt_dlp import YoutubeDL
from typing import Dict, Optional, Any

# ------------------------------
# Common YT-DLP Configuration
# ------------------------------
YDL_OPTS = {
    "quiet": True,                # no logs in console
    "no_warnings": True,          # hide warnings
    "skip_download": True,        # metadata only
    "simulate": True,             # don't actually download
    "forcejson": True,            # always return JSON
    "restrictfilenames": True,    # safe filenames
    "ignoreerrors": True,
    "nocheckcertificate": True,
    "geo_bypass": True,
    "source_address": "0.0.0.0",
    
    # ✅ FIXED: Video aur Audio dono formats include karo
    "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo[ext=webm]+bestaudio[ext=webm]/best[ext=mp4]/best[ext=webm]/bestaudio/best",
    "prefer_free_formats": False,
}

# ------------------------------
# Extract full info from URL
# ------------------------------
async def extract_info(url: str) -> Dict[str, Any]:
    """
    Returns metadata (title, uploader, formats, etc.) for a given URL.
    Uses yt-dlp in a background thread so FastAPI remains async.
    """
    loop = asyncio.get_event_loop()

    def _run():
        with YoutubeDL(YDL_OPTS) as ydl:
            return ydl.extract_info(url, download=False)

    return await loop.run_in_executor(None, _run)

# ------------------------------
# Get Best Available Direct Download URL
# ------------------------------
async def get_best_format_stream_url(url: str, format_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns direct file download link (not stream proxy) with best quality.
    HLS formats ko avoid karta hai.
    Video aur Audio dono formats support karta hai.
    """
    info = await extract_info(url)
    if not info:
        raise RuntimeError("Failed to fetch info from URL")

    formats = info.get("formats", [])
    if not formats:
        raise RuntimeError("No formats available for this media")

    chosen = None

    # --- If format_id specified
    if format_id:
        for f in formats:
            if f.get("format_id") == format_id:
                chosen = f
                break

    # --- Audio-only formats (MP3, M4A, etc.)
    if not chosen and format_id and format_id in ["bestaudio", "mp3", "m4a", "aac"]:
        audio_formats = [
            f for f in formats 
            if f.get("acodec") != "none" 
            and f.get("vcodec") == "none"  # Audio only
            and "hls" not in (f.get("format_note") or "").lower()
            and "manifest" not in (f.get("url") or "")
        ]
        
        if audio_formats:
            # Best quality audio format select karo
            audio_formats.sort(key=lambda x: (x.get("abr") or 0), reverse=True)
            chosen = audio_formats[0]
            print(f"✅ Selected audio format: {chosen.get('format_id')} - {chosen.get('format_note')}")

    # --- Video formats (MP4, WebM, etc.)
    if not chosen:
        # ✅ FIXED: HLS formats ko completely avoid karo
        progressive_formats = [
            f for f in formats 
            if f.get("acodec") != "none" 
            and f.get("vcodec") != "none"
            and "hls" not in (f.get("format_note") or "").lower()
            and "manifest" not in (f.get("url") or "")
            and "m3u8" not in (f.get("url") or "")
        ]
        
        if progressive_formats:
            # Best quality progressive format select karo
            progressive_formats.sort(key=lambda x: (x.get("height") or 0), reverse=True)
            chosen = progressive_formats[0]
            print(f"✅ Selected progressive format: {chosen.get('format_id')} - {chosen.get('format_note')}")

    # --- Fallback: Agar progressive format nahi mila, toh koi bhi non-HLS format
    if not chosen:
        non_hls_formats = [
            f for f in formats 
            if "hls" not in (f.get("format_note") or "").lower()
            and "manifest" not in (f.get("url") or "")
            and "m3u8" not in (f.get("url") or "")
        ]
        
        if non_hls_formats:
            non_hls_formats.sort(key=lambda x: (x.get("height") or 0), reverse=True)
            chosen = non_hls_formats[0]
            print(f"⚠️  Selected non-HLS fallback format: {chosen.get('format_id')} - {chosen.get('format_note')}")

    # --- Last resort: Koi bhi format
    if not chosen and formats:
        chosen = formats[0]
        print(f"🚨 Selected any available format: {chosen.get('format_id')} - {chosen.get('format_note')}")

    if not chosen or not chosen.get("url"):
        raise RuntimeError("No playable format found")

    # ✅ FINAL CHECK: Agar HLS URL hai toh warning dena
    final_url = chosen.get("url")
    if any(keyword in final_url for keyword in ["manifest.googlevideo.com/api/manifest/hls_playlist", "m3u8", "hls"]):
        print(f"🚨 WARNING: HLS URL still detected: {final_url}")
        # Try to find alternative format
        alternative_formats = [
            f for f in formats 
            if f.get("format_id") in ["22", "18", "136", "137", "398", "399", "400", "140", "141"]  # Common MP4 & Audio formats
            and "hls" not in (f.get("format_note") or "").lower()
        ]
        if alternative_formats:
            chosen = alternative_formats[0]
            final_url = chosen.get("url")
            print(f"✅ Switched to alternative format: {chosen.get('format_id')}")

    # ✅ File extension set karo based on format type
    ext = chosen.get("ext", "mp4")
    if chosen.get("vcodec") == "none":  # Audio only format
        if ext == "m4a":
            ext = "mp3"  # Convert m4a to mp3 for better compatibility
        elif ext == "webm":
            ext = "mp3"
    
    safe_title = (info.get("title") or "video").replace("/", "_").replace("\\", "_")

    return {
        "url": final_url,
        "ext": ext,
        "format_id": chosen.get("format_id"),
        "filesize": chosen.get("filesize") or chosen.get("filesize_approx"),
        "filename": f"{safe_title}.{ext}",
        "is_audio": chosen.get("vcodec") == "none",  # Audio format hai ya nahi
    }
