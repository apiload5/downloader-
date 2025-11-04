# ==============================
# SaveMedia Backend (Zero-Load Direct Download)
# Author: Muhammad Amir Khursheed Ahmed Khan [Ticnodeveloper] + GPT-5
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

# Attempt to make static ffmpeg available on PATH, but don't crash if it fails.
# This keeps the app up even if the package wasn't installed correctly.
try:
    import static_ffmpeg
    try:
        ffpath = static_ffmpeg.get_ffmpeg_path()
        if ffpath:
            os.environ["PATH"] += os.pathsep + ffpath
            print(f"[INFO] static-ffmpeg path added: {ffpath}", flush=True)
        else:
            print("[WARN] static-ffmpeg returned empty path", flush=True)
    except Exception as e:
        print(f"[WARN] static_ffmpeg.get_ffmpeg_path() failed: {e}", flush=True)
except Exception as e:
    print(f"[WARN] static-ffmpeg import failed: {e}", flush=True)

# load environment variables after path adjustments (optional)
load_dotenv()
