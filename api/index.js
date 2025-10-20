const express = require('express');
const cors = require('cors');
const ytdl = require('ytdl-core');

// ⚠️ FFmpeg dependencies ka load aur path set karna zaroori hai
const ffmpeg = require('fluent-ffmpeg');
const ffmpegStatic = require('ffmpeg-static');

// Vercel serverless environment ke liye FFmpeg binary ka path set karein.
if (ffmpegStatic) {
    ffmpeg.setFfmpegPath(ffmpegStatic);
}

const app = express();
app.use(cors());
app.use(express.json());

// 1. Root Health Check Route
// URL: https://downloader5.vercel.app/
app.get('/', (req, res) => {
    res.send('✅ Vercel Root Backend is Running Successfully!');
});

// 2. API Health Check Route (Fixes the Cannot GET /api error)
// URL: https://downloader5.vercel.app/api
app.get('/api', (req, res) => {
    res.send('✅ Vercel API Endpoint is Running Successfully!');
});

// 3. Fetch Video Information Route
// Method: POST | URL: /api/fetch-info
app.post('/api/fetch-info', async (req, res) => {
    const { url } = req.body;

    if (!url || !ytdl.validateURL(url)) {
        return res.status(400).json({ error: 'Kripya ek valid YouTube URL daalein.' });
    }

    try {
        const info = await ytdl.getInfo(url);
        
        // Filter and sort video formats (only MP4 with video and audio)
        let formats = info.formats
            .filter(f => f.qualityLabel && f.container === 'mp4' && f.hasVideo && f.hasAudio)
            .sort((a, b) => b.height - a.height);

        const finalFormats = formats.map(f => ({
            quality: f.qualityLabel,
            container: f.container,
            itag: f.itag,
            contentLength: f.contentLength ? (parseInt(f.contentLength) / (1024 * 1024)).toFixed(2) + ' MB' : 'Unknown Size'
        }));

        // Add MP3 (Audio Only) option
        finalFormats.push({
            quality: 'MP3 (Audio Only)',
            container: 'mp3',
            itag: 'bestaudio',
            contentLength: 'Varies'
        });

        const responseData = {
            title: info.videoDetails.title,
            thumbnail: info.videoDetails.thumbnails.slice(-1)[0].url,
            formats: finalFormats,
        };

        res.json(responseData);

    } catch (error) {
        console.error('Error fetching video info:', error.message);
        res.status(500).json({ error: 'Video information nahi mil payi. URL ya video ki availability check karein.' });
    }
});

// 4. Video Download Route
// Method: GET | URL: /api/download
app.get('/api/download', async (req, res) => {
    const { url, itag, quality, title = 'video' } = req.query;

    if (!url || !itag) {
        return res.status(400).send('Video URL aur Format ID (itag) zaruri hai.');
    }
    
    // File name ko safe banane ke liye cleaning
    const cleanTitle = title.replace(/[^\w\s-]/g, '').trim(); 

    try {
        if (itag === 'bestaudio') {
            // --- MP3 Conversion Logic (using FFmpeg) ---
            res.header('Content-Disposition', `attachment; filename="${cleanTitle}_audio.mp3"`);
            res.header('Content-Type', 'audio/mpeg');

            const audioStream = ytdl(url, { filter: 'audioonly' });

            ffmpeg(audioStream)
                .noVideo()
                .audioCodec('libmp3lame')
                .format('mp3')
                .on('error', (err) => {
                    console.error('FFmpeg MP3 Error:', err.message);
                    if (!res.headersSent) {
                        res.status(500).end('MP3 conversion mein galti ho gayi. (Check Vercel Logs)');
                    }
                })
                .pipe(res, { end: true });

        } else {
            // --- Standard Video Download Logic (MP4) ---
            res.header('Content-Disposition', `attachment; filename="${cleanTitle}_${quality.replace(/\s/g, '_')}.mp4"`);
            res.header('Content-Type', 'video/mp4');

            const videoStream = ytdl(url, { 
                filter: format => format.itag == itag && format.hasVideo && format.hasAudio,
                quality: 'highestvideo' 
            });

            videoStream.pipe(res);

            videoStream.on('error', (err) => {
                console.error('Download Stream Error:', err.message);
                if (!res.headersSent) {
                    res.status(500).end('Video download stream mein galti ho gayi.');
                }
            });
        }

    } catch (error) {
        console.error('General Download Error:', error.message);
        if (!res.headersSent) {
            res.status(500).send('Unexpected error during download processing.');
        }
    }
});

// Express app ko Vercel ke liye export karna
module.exports = app;
