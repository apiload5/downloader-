const express = require('express');
const cors = require('cors');
const { createDownloader } = require('yt-dlp-core');
const ffmpeg = require('fluent-ffmpeg');

// FFmpeg binary ka path set karna
// Vercel ya Google Cloud par, FFmpeg ko manually include ya install karna pad sakta hai.
// Local testing ke liye, yeh line zaruri nahi hai agar aapke system mein FFmpeg installed hai.
// Vercel par iski zaroorat padegi: https://vercel.com/guides/using-ffmpeg-with-vercel
// Abhi hum assume karte hain ki environment mein FFmpeg accessible hai.

const app = express();
app.use(cors());
app.use(express.json());

// 1. Video Downloader Setup
const downloader = createDownloader();

// Video quality mapping (User request ke liye)
const QUALITY_MAP = {
    '144p': 160,
    '240p': 133,
    '360p': 134,
    '480p': 135,
    '720p': 136,
    '1080p': 137
    // MP3 will be handled separately by FFmpeg
};

// 2. Health Check
app.get('/', (req, res) => {
    res.send('Node.js Multi-Platform Downloader Backend is Running Successfully!');
});

// 3. Fetch Video Information (Multi-platform support)
app.post('/api/fetch-info', async (req, res) => {
    const { url } = req.body;

    if (!url) {
        return res.status(400).json({ error: 'Video URL is required.' });
    }

    try {
        // yt-dlp-core se video ki jaankari nikalna (jo multiple platforms ko support karta hai)
        const info = await downloader.getInfo(url);

        // Quality formats nikalna (video-only streams ko filter karna)
        let videoFormats = info.formats
            .filter(f => f.quality && f.ext === 'mp4') // mp4 files jo quality label rakhte hain
            .sort((a, b) => b.height - a.height); // Highest resolution pehle aayega

        const uniqueFormats = {};
        videoFormats.forEach(f => {
            if (!uniqueFormats[f.quality]) {
                uniqueFormats[f.quality] = {
                    quality: f.quality,
                    container: f.ext,
                    formatId: f.format_id, // yt-dlp ka format ID
                    contentLength: f.filesize ? (f.filesize / (1024 * 1024)).toFixed(2) + ' MB' : 'Unknown Size'
                };
            }
        });

        // Final formats list
        const formats = Object.values(uniqueFormats);
        
        // MP3 format ko manually add karna
        formats.push({
            quality: 'MP3 (Audio Only)',
            container: 'mp3',
            formatId: 'bestaudio', // Best audio stream ke liye special ID
            contentLength: 'Varies'
        });

        const responseData = {
            title: info.title,
            thumbnail: info.thumbnail || info.thumbnails[0].url,
            formats: formats,
        };

        res.json(responseData);

    } catch (error) {
        console.error('Error fetching video info:', error.message);
        res.status(500).json({ error: 'Video information nahi mil payi. Kripya link aur platform check karein.' });
    }
});

// 4. Video Download Route (Streaming)
app.get('/api/download', async (req, res) => {
    const { url, formatId, quality, title = 'video' } = req.query;

    if (!url || !formatId) {
        return res.status(400).send('Video URL aur Format ID zaruri hai.');
    }

    const cleanTitle = title.replace(/[^\w\s-]/g, '').trim(); // File name se special characters hatana

    try {
        if (formatId === 'bestaudio') {
            // --- MP3 Conversion Logic ---
            res.header('Content-Disposition', `attachment; filename="${cleanTitle}_audio.mp3"`);
            res.header('Content-Type', 'audio/mpeg');

            // yt-dlp se best audio stream nikalna
            const audioStream = downloader.download(url, {
                format: 'bestaudio',
                // isko yahan set karne se streaming better hoti hai
                // https://github.com/intrvntcn/yt-dlp-core#streaming-video-to-the-client
                dumpSingleJson: true
            });

            // FFmpeg se audio ko MP3 mein convert karke stream karna
            ffmpeg(audioStream)
                .noVideo() // Sirf audio chahiye
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
            // --- Standard Video Download Logic ---
            res.header('Content-Disposition', `attachment; filename="${cleanTitle}_${quality}.mp4"`);
            res.header('Content-Type', 'video/mp4');

            // yt-dlp se specified format ko stream karna
            const videoStream = downloader.download(url, {
                format: formatId,
                dumpSingleJson: true // isko yahan set karne se streaming better hoti hai
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


// Vercel/Cloud ke liye: Express app ko export karna
module.exports = app;
