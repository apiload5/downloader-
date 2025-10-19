const express = require('express');
const cors = require('cors');
const ytdl = require('ytdl-core-muxer'); // Nayi aur stable library
const ffmpeg = require('fluent-ffmpeg');

const app = express();
app.use(cors());
app.use(express.json());

// 1. Health Check
app.get('/', (req, res) => {
    res.send('Node.js Multi-Platform Downloader Backend is Running Successfully (Fixed)!');
});

// 2. Fetch Video Information 
app.post('/api/fetch-info', async (req, res) => {
    const { url } = req.body;

    if (!url) {
        return res.status(400).json({ error: 'Video URL is required.' });
    }

    try {
        const info = await ytdl.getInfo(url);
        
        // ytdl-core-muxer mein formats ko filter aur map karna
        let formats = ytdl.filterFormats(info.formats, 'videoandaudio')
            .filter(f => f.qualityLabel && f.container === 'mp4') // MP4 container aur quality label waale formats
            .sort((a, b) => b.height - a.height); // Highest resolution pehle

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
            itag: 'bestaudio', // MP3 ke liye ek special ID
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
            // --- MP3 Conversion Logic using FFmpeg ---
            res.header('Content-Disposition', `attachment; filename="${cleanTitle}_audio.mp3"`);
            res.header('Content-Type', 'audio/mpeg');

            // ytdl se best audio stream nikalna
            const audioStream = ytdl(url, { filter: 'audioonly' });

            // FFmpeg se audio ko MP3 mein convert karke stream karna
            ffmpeg(audioStream)
                .noVideo() // Sirf audio chahiye
                .audioCodec('libmp3lame')
                .format('mp3')
                .on('error', (err) => {
                    console.error('FFmpeg MP3 Error:', err.message);
                    if (!res.headersSent) {
                        res.status(500).end('MP3 conversion mein galti ho gayi. (FFmpeg missing?)');
                    }
                })
                .pipe(res, { end: true });

        } else {
            // --- Standard Video Download Logic (Video + Audio) ---
            res.header('Content-Disposition', `attachment; filename="${cleanTitle}_${quality}.mp4"`);
            res.header('Content-Type', 'video/mp4');

            // Video aur audio ko merge karke stream karna
            const videoStream = ytdl(url, { 
                filter: 'videoandaudio', // Video aur audio dono chahiye
                quality: itag // Specific itag quality
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
