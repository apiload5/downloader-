from flask import Flask, request, jsonify, send_file, render_template_string
from flask_cors import CORS
import yt_dlp
import os
import tempfile
import threading
import time
import subprocess
import gc
import shutil
from werkzeug.utils import secure_filename
import logging
import uuid

# Configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# AWS Elastic Beanstalk compatibility
application = app

# --- SECURITY: CORS CONFIGURATION ---

# Allow all specified origins
CORS(app, origins=ALLOWED_ORIGINS, supports_credentials=True)
# ---

# Global variables for download management
downloads = {}
download_lock = threading.Lock()

def get_ffmpeg_path():
    """Get FFmpeg path for Health Check"""
    # yt-dlp now relies on the system PATH set by .ebextensions.
    paths = ['/usr/local/bin/ffmpeg', '/usr/bin/ffmpeg', 'ffmpeg']
    for path in paths:
        try:
            subprocess.run([path, '-version'], capture_output=True, check=True, timeout=5)
            return path
        except:
            continue
    return 'ffmpeg'

def get_temp_dir():
    """Get temporary directory for file storage"""
    # Use /tmp as primary temp dir in Linux environments
    temp_dir = tempfile.gettempdir()
    try:
        os.makedirs(temp_dir, exist_ok=True)
        return temp_dir
    except:
        return tempfile.gettempdir()

def cleanup_temp_files(temp_dir):
    """Clean up temporary directory"""
    try:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        gc.collect()
    except Exception as e:
        logger.error(f"Cleanup failed for {temp_dir}: {e}")

@app.route('/')
def index():
    # ... (HTML template remains the same for simplicity)
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Video Downloader</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
            .container { background: #f5f5f5; padding: 20px; border-radius: 10px; }
            input, select, button { padding: 10px; margin: 5px; border: 1px solid #ddd; border-radius: 5px; }
            input[type="url"] { width: 70%; }
            button { background: #007bff; color: white; cursor: pointer; }
            button:hover { background: #0056b3; }
            .result { margin-top: 20px; padding: 15px; background: white; border-radius: 5px; }
            .progress { width: 100%; background: #f0f0f0; border-radius: 5px; margin: 10px 0; }
            .progress-bar { height: 20px; background: #007bff; border-radius: 5px; transition: width 0.3s; }
            .error { color: red; }
            .success { color: green; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🎥 Video Downloader</h1>
            <p>Download videos from YouTube, Instagram, TikTok, and more!</p>
            
            <form id="downloadForm">
                <input type="url" id="videoUrl" placeholder="Enter video URL..." required>
                <select id="quality">
                    <option value="best">Best Quality</option>
                    <option value="720p">720p</option>
                    <option value="480p">480p</option>
                    <option value="360p">360p</option>
                    <option value="audio">Audio Only (MP3)</option>
                </select>
                <button type="submit">Download</button>
            </form>
            
            <div id="result" class="result" style="display:none;"></div>
        </div>

        <script>
            document.getElementById('downloadForm').addEventListener('submit', async function(e) {
                e.preventDefault();
                
                const url = document.getElementById('videoUrl').value;
                const quality = document.getElementById('quality').value;
                const resultDiv = document.getElementById('result');
                
                resultDiv.style.display = 'block';
                resultDiv.innerHTML = '<p>🔄 Processing your request...</p>';
                
                try {
                    const response = await fetch('/download', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ url: url, quality: quality })
                    });
                    
                    const data = await response.json();
                    
                    if (data.success) {
                        resultDiv.innerHTML = `
                            <p class="success">✅ ${data.message}</p>
                            <p><strong>Download ID:</strong> ${data.download_id}</p>
                            <a href="/status/${data.download_id}">Check Status</a>
                            <p>Once completed, use the /file/${data.download_id} link to download.</p>
                        `;
                    } else {
                        resultDiv.innerHTML = `<p class="error">❌ ${data.message}</p>`;
                    }
                } catch (error) {
                    resultDiv.innerHTML = `<p class="error">❌ Network error: ${error.message}</p>`;
                }
            });
        </script>
    </body>
    </html>
    ''')

@app.route('/health')
def health():
    """Health check endpoint for AWS Elastic Beanstalk"""
    try:
        ffmpeg_path = get_ffmpeg_path()
        result = subprocess.run([ffmpeg_path, '-version'], 
                              capture_output=True, timeout=5)
        ffmpeg_ok = result.returncode == 0
        
        return jsonify({
            "status": "healthy",
            "ffmpeg_available": ffmpeg_ok,
            "ffmpeg_path": ffmpeg_path,
            "timestamp": time.time()
        }), 200
    except:
        return jsonify({
            "status": "degraded",
            "ffmpeg_available": False,
            "message": "FFmpeg not found or not callable. Check .ebextensions.",
            "timestamp": time.time()
        }), 503

@app.route('/download', methods=['POST'])
def download_video():
    try:
        data = request.get_json()
        if not data or 'url' not in data:
            return jsonify({'success': False, 'message': 'URL is required'}), 400
        
        url = data['url']
        quality = data.get('quality', 'best')
        
        if not url.startswith(('http://', 'https://')):
            return jsonify({'success': False, 'message': 'Invalid URL format'}), 400
        
        # Use a proper unique ID
        download_id = uuid.uuid4().hex
        
        with download_lock:
            downloads[download_id] = {
                'status': 'processing',
                'progress': 0,
                'message': 'Starting download...'
            }
        
        thread = threading.Thread(
            target=process_download,
            args=(download_id, url, quality)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'download_id': download_id,
            'message': 'Download started. Check status endpoint for progress.'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

def process_download(download_id, url, quality):
    temp_dir = None
    try:
        with download_lock:
            downloads[download_id]['message'] = 'Extracting video info...'
            downloads[download_id]['progress'] = 10
        
        temp_dir = tempfile.mkdtemp(dir=get_temp_dir())
        
        if quality == 'audio':
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'quiet': True,
                'no_warnings': True,
            }
        else:
            if quality == 'best':
                format_selector = 'bestvideo[height<=1080]+bestaudio/best'
            elif quality == '720p':
                format_selector = 'bestvideo[height<=720]+bestaudio/best'
            elif quality == '480p':
                format_selector = 'bestvideo[height<=480]+bestaudio/best'
            elif quality == '360p':
                format_selector = 'bestvideo[height<=360]+bestaudio/best'
            else:
                format_selector = 'bestvideo[height<=1080]+bestaudio/best'
            
            ydl_opts = {
                'format': format_selector,
                'merge_output_format': 'mp4',
                'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
                'postprocessors': [
                    {'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}
                ],
                'quiet': True,
                'no_warnings': True,
            }
        
        def progress_hook(d):
            if d['status'] == 'downloading':
                try:
                    percent = d.get('_percent_str', '0%').replace('%', '')
                    progress = int(float(percent.strip()))
                    with download_lock:
                        downloads[download_id]['progress'] = min(progress, 90)
                        downloads[download_id]['message'] = f'Downloading... {percent}%'
                except:
                    pass
        
        ydl_opts['progress_hooks'] = [progress_hook]
        
        with download_lock:
            downloads[download_id]['message'] = 'Downloading video...'
            downloads[download_id]['progress'] = 20
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'video')
            duration = info.get('duration', 0)
            
            if duration:
                minutes = duration // 60
                seconds = duration % 60
                duration_str = f"{minutes}:{seconds:02d}"
            else:
                duration_str = "Unknown"
        
        downloaded_files = [f for f in os.listdir(temp_dir) if os.path.isfile(os.path.join(temp_dir, f))]
        
        if not downloaded_files:
            raise Exception("No file was downloaded. Check if FFmpeg is installed correctly.")
        
        final_file = None
        for f in downloaded_files:
            if f.endswith('.mp4') or f.endswith('.mp3'):
                final_file = f
                break
        
        if not final_file:
             final_file = downloaded_files[0]
        
        file_path = os.path.join(temp_dir, final_file)
        
        with download_lock:
            downloads[download_id].update({
                'status': 'completed',
                'progress': 100,
                'message': 'Download completed successfully! Use /file endpoint to download.',
                'title': title,
                'duration': duration_str,
                'file_path': file_path,
                'filename': final_file,
                'temp_dir': temp_dir # Keep track of the temp dir for cleanup
            })
        
    except Exception as e:
        logger.error(f"Download thread error: {e}")
        with download_lock:
            downloads[download_id].update({
                'status': 'error',
                'message': f'Download failed: {str(e)}'
            })
        if temp_dir:
            cleanup_temp_files(temp_dir)

@app.route('/status/<download_id>')
def get_download_status(download_id):
    with download_lock:
        if download_id in downloads:
            return jsonify(downloads[download_id])
        else:
            return jsonify({'status': 'not_found', 'message': 'Download not found'}), 404

@app.route('/file/<download_id>')
def download_file(download_id):
    """Serve the downloaded file and clean up immediately."""
    with download_lock:
        if download_id not in downloads:
            return jsonify({'error': 'Download not found'}), 404
        
        download_info = downloads[download_id]
        
        if download_info['status'] != 'completed':
            return jsonify({'error': 'Download not completed'}), 400
        
        file_path = download_info['file_path']
        filename = download_info['filename']
        temp_dir = download_info.get('temp_dir')
        
        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found'}), 404
        
        # --- CRITICAL: File Serving and Cleanup ---
        response = send_file(
            file_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/octet-stream'
        )
        
        @response.call_on_close
        def cleanup():
            """This function executes after the file has been successfully sent to the user."""
            try:
                if temp_dir:
                    cleanup_temp_files(temp_dir)
                with download_lock:
                    if download_id in downloads:
                         del downloads[download_id]
            except Exception as e:
                logger.error(f"Post-download cleanup failed for {download_id}: {e}")
        
        return response

@app.route('/api/info', methods=['POST'])
def get_video_info():
    try:
        data = request.get_json()
        if not data or 'url' not in data:
            return jsonify({'success': False, 'message': 'URL is required'}), 400
        
        url = data['url']
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            return jsonify({
                'success': True,
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0),
                'uploader': info.get('uploader', 'Unknown'),
                'view_count': info.get('view_count', 0),
                'thumbnail': info.get('thumbnail', ''),
                'description': info.get('description', '')[:200] + '...' if info.get('description') else ''
            })
            
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# Error handlers
@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        "error": "Internal server error",
        "message": "Please try again later"
    }), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "error": "Endpoint not found",
        "message": "Check API documentation"
    }), 404

@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({
        "error": "File too large",
        "message": "Please try a smaller file"
    }), 413

if __name__ == '__main__':
    # Using 8080 as the standard default port for cloud deployment
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
