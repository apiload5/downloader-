// Frontend mein download function mein yeh add karo
async function initiateSaveFromStyleDownload(formatId, quality) {
    try {
        const url = videoUrlInput.value;
        
        updateProgress(90, 'Getting download link...');
        
        const response = await fetch(`${API_BASE_URL}/download`, {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify({ 
                url: url, 
                format_id: formatId, 
                quality: quality 
            })
        });

        if (!response.ok) throw new Error('Download failed');

        const downloadData = await response.json();
        
        // ✅ HLS URL CHECK
        if (downloadData.direct_url.includes('manifest.googlevideo.com/api/manifest/hls_playlist')) {
            // HLS URL hai - user ko manual download guide show karo
            showManualDownloadGuide(downloadData.direct_url, downloadData.filename);
        } else {
            // Normal URL hai - direct download karo
            triggerDirectDownload(downloadData.direct_url, downloadData.filename);
            showSuccess('Download started successfully! File will save automatically.');
        }

        updateProgress(100, 'Download process started!');
        
        downloadCount++;
        localStorage.setItem('downloadCount', downloadCount.toString());
        
        setTimeout(() => {
            hideProgress();
            downloadInProgress = false;
            localStorage.removeItem('pendingDownload');
        }, 2000);

    } catch (error) {
        console.error('Download error:', error);
        hideProgress();
        downloadInProgress = false;
        localStorage.removeItem('pendingDownload');
        showError('Download failed: ' + error.message);
    }
}

// Manual download guide for HLS URLs
function showManualDownloadGuide(hlsUrl, filename) {
    const guideHTML = `
        <div style="background: #e3f2fd; padding: 20px; border-radius: 10px; margin: 15px 0; border: 1px solid #bbdefb;">
            <h4 style="color: #1565c0; margin-bottom: 15px;">📺 Video Ready for Download</h4>
            <p style="color: #1565c0; margin-bottom: 15px;">
                <strong>Follow these simple steps to download:</strong>
            </p>
            <ol style="color: #1565c0; text-align: left; margin-bottom: 20px;">
                <li>Click the button below to open video</li>
                <li>Right-click on the video player</li>
                <li>Select "Save video as..." or "Download"</li>
                <li>Choose location and save the file</li>
            </ol>
            <div style="display: flex; gap: 10px; flex-wrap: wrap; justify-content: center;">
                <button onclick="window.open('${hlsUrl}', '_blank')" 
                        style="background: #2196F3; color: white; border: none; padding: 12px 20px; border-radius: 8px; cursor: pointer; font-weight: bold;">
                    🎬 Open Video for Download
                </button>
                <button onclick="tryDifferentFormat()" 
                        style="background: #4CAF50; color: white; border: none; padding: 12px 20px; border-radius: 8px; cursor: pointer;">
                    🔄 Try Different Quality
                </button>
            </div>
        </div>
    `;
    
    successContainer.innerHTML = guideHTML;
    successContainer.style.display = 'block';
}

// Try different format function
async function tryDifferentFormat() {
    const alternativeFormats = ['22', '18', '136', '137']; // MP4 formats
    for (let formatId of alternativeFormats) {
        try {
            startDownload(formatId, 'Alternative Format');
            break;
        } catch (e) {
            continue;
        }
    }
}
