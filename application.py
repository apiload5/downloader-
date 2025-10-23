from flask import Flask, request, jsonify, send_file, render_template_string
import yt_dlp
import os
import tempfile
import threading
import time
import subprocess
import gc
import shutil
from werkzeug.utils import secure_filename

app = Flask(__name__)

# AWS Elastic Beanstalk compatibility
application = app

# Global variables for download management
downloads = {}
download_lock = threading.Lock()

def get_ffmpeg_path():
    """Get FFmpeg path for AWS Elastic Beanstalk"""
    paths = ['/usr/local/bin/ffmpeg', '/usr/bin/ffmpeg', 'ffmpeg']
    for path in paths:
        try:
            subprocess.run([path, '-version'], capture_output=True, check=True, timeout=5)
            return path
        except:
            continue
    return 'ffmpeg'

def get_temp_dir():
    """Get temporary directory for AWS Elastic Beanstalk"""
    temp_dirs = ['/tmp/downloads', tempfile.gettempdir(), '/var/tmp']
    for temp_dir in temp_dirs:
        try:
            os.makedirs(temp_dir, exist_ok=True)
            return temp_dir
        except:
            continue
    return tempfile.gettempdir()

def cleanup_temp_files(temp_dir):
    """Clean up temporary files after processing"""
    try:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        gc.collect()
    except:
        pass

@app.route('/')
def index():
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
                            <p><strong>Title:</strong> ${data.title}</p>
                            <p><strong>Duration:</strong> ${data.duration}</p>
                            <a href="${data.download_url}" download class="button">📥 Download File</a>
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
            "status": "healthy",
            "ffmpeg_available": False,
            "timestamp": time.time()
        }), 200

@app.route('/download', methods=['POST'])
def download_video():
    try:
        data = request.get_json()
        if not data or 'url' not in data:
            return jsonify({'success': False, 'message': 'URL is required'})
        
        url = data['url']
        quality = data.get('quality', 'best')
        
        # Validate URL
        if not url.startswith(('http://', 'https://')):
            return jsonify({'success': False, 'message': 'Invalid URL format'})
        
        # Generate unique download ID
        download_id = str(int(time.time() * 1000))
        
        with download_lock:
            downloads[download_id] = {
                'status': 'processing',
                'progress': 0,
                'message': 'Starting download...'
            }
        
        # Start download in background thread
        thread = threading.Thread(
            target=process_download,
            args=(download_id, url, quality)
        )
        thread.daemon = True
        thread.start()
        
        return jsonify({
            'success': True,
            'download_id': download_id,
            'message': 'Download started'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

def process_download(download_id, url, quality):
    temp_dir = None
    try:
        # Update status
        with download_lock:
            downloads[download_id]['message'] = 'Extracting video info...'
            downloads[download_id]['progress'] = 10
        
        # Create temporary directory
        temp_dir = tempfile.mkdtemp(dir=get_temp_dir())
        
        # Configure yt-dlp options based on quality
        if quality == 'audio':
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'ffmpeg_location': get_ffmpeg_path(),
                'quiet': True,
                'no_warnings': True,
            }
        else:
            if quality == 'best':
                format_selector = 'best[height<=1080]'
            elif quality == '720p':
                format_selector = 'best[height<=720]'
            elif quality == '480p':
                format_selector = 'best[height<=480]'
            elif quality == '360p':
                format_selector = 'best[height<=360]'
            else:
                format_selector = 'best'
            
            ydl_opts = {
                'format': format_selector,
                'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
                'ffmpeg_location': get_ffmpeg_path(),
                'quiet': True,
                'no_warnings': True,
            }
        
        # Progress hook
        def progress_hook(d):
            if d['status'] == 'downloading':
                try:
                    percent = d.get('_percent_str', '0%').replace('%', '')
                    progress = int(float(percent))
                    with download_lock:
                        downloads[download_id]['progress'] = min(progress, 90)
                        downloads[download_id]['message'] = f'Downloading... {percent}%'
                except:
                    pass
        
        ydl_opts['progress_hooks'] = [progress_hook]
        
        # Download video
        with download_lock:
            downloads[download_id]['message'] = 'Downloading video...'
            downloads[download_id]['progress'] = 20
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'video')
            duration = info.get('duration', 0)
            
            # Format duration
            if duration:
                minutes = duration // 60
                seconds = duration % 60
                duration_str = f"{minutes}:{seconds:02d}"
            else:
                duration_str = "Unknown"
        
        # Find downloaded file
        downloaded_files = [f for f in os.listdir(temp_dir) if os.path.isfile(os.path.join(temp_dir, f))]
        
        if not downloaded_files:
            raise Exception("No file was downloaded")
        
        downloaded_file = downloaded_files[0]
        file_path = os.path.join(temp_dir, downloaded_file)
        
        # Update final status
        with download_lock:
            downloads[download_id].update({
                'status': 'completed',
                'progress': 100,
                'message': 'Download completed successfully!',
                'title': title,
                'duration': duration_str,
                'file_path': file_path,
                'filename': downloaded_file
            })
        
        # Schedule cleanup after 1 hour
        cleanup_timer = threading.Timer(3600, cleanup_temp_files, [temp_dir])
        cleanup_timer.start()
        
    except Exception as e:
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
            return jsonify({'status': 'not_found', 'message': 'Download not found'})

@app.route('/file/<download_id>')
def download_file(download_id):
    with download_lock:
        if download_id not in downloads:
            return jsonify({'error': 'Download not found'}), 404
        
        download_info = downloads[download_id]
        
        if download_info['status'] != 'completed':
            return jsonify({'error': 'Download not completed'}), 400
        
        file_path = download_info['file_path']
        filename = download_info['filename']
        
        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found'}), 404
        
        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/octet-stream'
        )

@app.route('/api/info', methods=['POST'])
def get_video_info():
    try:
        data = request.get_json()
        if not data or 'url' not in data:
            return jsonify({'success': False, 'message': 'URL is required'})
        
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
        return jsonify({'success': False, 'message': str(e)})

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
    # AWS Elastic Beanstalk port configuration
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
