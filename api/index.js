const express = require('express');
const cors = require('cors');
const ytdl = require('ytdl-core'); // Stable ytdl-core use ho raha hai
const ffmpeg = require('fluent-ffmpeg');
const ffmpegPath = require('ffmpeg-static');

// FFmpeg path ko set karna
if (ffmpegPath) {
    ffmpeg.setFfmpegPath(ffmpegPath);
}

const app = express();
app.use(cors());
app.use(express.json());

// 1. Health Check
app.get('/', (req, res) => {
    res.send('✅ Final Video Downloader Backend is Running!');
});

// 2. Fetch Video Information (Quality and MP3 Support)
app.post('/api/fetch-info', async (req, res) => {
    const { url } = req.body;

    if (!url) {
        return res.status(400).json({ error: 'Video URL is required.' });
    }
    
    // ytdl-core sirf YouTube links ko support karta hai.
    // Agar future mein dusre platforms chahiye, to alag paid service ya yt-dlp binary use karna padega.
    if (!ytdl.validateURL(url)) {
         return res.status(400).json({ error: 'Kripya ek valid YouTube URL daalein. (Is version mein sirf YouTube supported hai)' });
    }

    try {
        const info = await ytdl.getInfo(url);
        
        // Formats filter karna: sirf video+audio formats ko mp4 container mein nikalna
        let formats = info.formats
            .filter(f => f.qualityLabel && f.container === 'mp4' && f.hasVideo && f.hasAudio)
            .sort((a, b) => b.height - a.height); // Highest quality pehle

        // Formats list taiyar karna
        const finalFormats = formats.map(f => ({
            quality: f.qualityLabel,
            container: f.container,
            itag: f.itag, // Download ke liye zaruri
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
                        res.status(500).end('MP3 conversion mein galti ho gayi.');
                    }
                })
                .pipe(res, { end: true });

        } else {
            // --- Standard Video Download Logic (Video + Audio) ---
            res.header('Content-Disposition', `attachment; filename="${cleanTitle}_${quality.replace(/\s/g, '_')}.mp4"`);
            res.header('Content-Type', 'video/mp4');

            // Video aur audio ko merge karke stream karna
            const videoStream = ytdl(url, { 
                filter: format => format.itag == itag && format.hasVideo && format.hasAudio, // Specific itag ko filter karein
                quality: 'highestvideo' // Fallback
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
