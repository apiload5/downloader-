const express = require('express');
const cors = require('cors');
const ytdl = require('ytdl-core-muxer'); // Multi-platform support
const ffmpeg = require('fluent-ffmpeg');
const ffmpegPath = require('ffmpeg-static'); // FFmpeg binary path
const { PassThrough } = require('stream');

// FFmpeg path ko set karna taaki fluent-ffmpeg use kar sake
if (ffmpegPath) {
    ffmpeg.setFfmpegPath(ffmpegPath);
}

const app = express();
app.use(cors());
app.use(express.json());

// 1. Health Check Route
app.get('/', (req, res) => {
    res.send('✅ Video Downloader Backend is Running!');
});

// 2. Fetch Video Information (Multi-platform & Quality Support)
app.post('/api/fetch-info', async (req, res) => {
    const { url } = req.body;

    if (!url) {
        return res.status(400).json({ error: 'Video URL is required.' });
    }

    try {
        const info = await ytdl.getInfo(url);
        
        // Video and Audio formats filter karna
        let formats = ytdl.filterFormats(info.formats, 'videoandaudio')
            .filter(f => f.qualityLabel && f.container === 'mp4')
            .sort((a, b) => b.height - a.height);

        // Formats list taiyar karna
        const finalFormats = formats.map(f => ({
            quality: f.qualityLabel,
            container: f.container,
            itag: f.itag,
            contentLength: f.contentLength ? (parseInt(f.contentLength) / (1024 * 1024)).toFixed(2) + ' MB' : 'Unknown Size'
        }));

        // MP3 (Audio Only) option add karna
        finalFormats.push({
            quality: 'MP3 (Audio Only)',
            container: 'mp3',
            itag: 'bestaudio', // MP3 ke liye special ID
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
        res.status(500).json({ error: 'Video information nahi mil payi. Kripya URL check karein.' });
    }
});

// 3. Video Download Route (Streaming)
app.get('/api/download', async (req, res) => {
    const { url, itag, quality, title = 'video' } = req.query;

    if (!url || !itag) {
        return res.status(400).send('Video URL aur Format ID (itag) zaruri hai.');
    }
    
    const cleanTitle = title.replace(/[^\w\s-]/g, '').trim(); 

    try {
        if (itag === 'bestaudio') {
            // --- MP3 Conversion Logic ---
            res.header('Content-Disposition', `attachment; filename="${cleanTitle}_audio.mp3"`);
            res.header('Content-Type', 'audio/mpeg');

            // ytdl se best audio stream nikalna
            const audioStream = ytdl(url, { filter: 'audioonly' });

            // FFmpeg se audio ko MP3 mein convert karke stream karna
            ffmpeg(audioStream)
                .noVideo()
                .audioCodec('libmp3lame')
                .format('mp3')
                .on('error', (err) => {
                    console.error('FFmpeg MP3 Error:', err.message);
                    if (!res.headersSent) {
                        res.status(500).end('MP3 conversion mein galti ho gayi. FFmpeg configuration check karein.');
                    }
                })
                .pipe(res, { end: true });

        } else {
            // --- Standard Video Download Logic (Video + Audio) ---
            res.header('Content-Disposition', `attachment; filename="${cleanTitle}_${quality.replace(/\s/g, '_')}.mp4"`);
            res.header('Content-Type', 'video/mp4');

            // Video aur audio ko merge karke stream karna
            const videoStream = ytdl(url, { 
                filter: 'videoandaudio',
                quality: itag
            });

            videoStream.pipe(res);

            videoStream.on('error', (err) => {
                console.error('Download Stream Error:', err.message);
                if (!res.headersSent) {
                    res.status(500).end('Video download mein galti ho gayi.');
                }
            });
        }

    } catch (error) {
        console.error('General Download Error:', error.message);
        if (!res.headersSent) {
            res.status(500).send('Unexpected error during download.');
        }
    }
});

module.exports = app;
