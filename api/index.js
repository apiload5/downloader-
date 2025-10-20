const express = require('express');
const cors = require('cors');
const ytdl = require('ytdl-core');

// FFmpeg dependencies ko import karein
const ffmpeg = require('fluent-ffmpeg');
const ffmpegStatic = require('ffmpeg-static');

// ⚠️ Vercel par FFmpeg path set karna mandatory hai (Isi line se pichla bug fix hua hai)
if (ffmpegStatic) {
    ffmpeg.setFfmpegPath(ffmpegStatic);
}

const app = express();
app.use(cors());
app.use(express.json());

// 1. Root and API Health Check Route
// Isse / aur /api dono par success message milega
app.get(['/', '/api'], (req, res) => {
    res.send('✅ Vercel Backend is Running and Ready for Use!');
});

// 2. Fetch Video Information Route (POST)
app.post('/api/fetch-info', async (req, res) => {
    const { url } = req.body;

    if (!url || !ytdl.validateURL(url)) {
         return res.status(400).json({ error: 'Kripya ek valid YouTube URL daalein.' });
    }

    try {
        const info = await ytdl.getInfo(url);
        
        // Video/Audio formats filter karna
        let formats = info.formats
            .filter(f => f.qualityLabel && f.container === 'mp4' && f.hasVideo && f.hasAudio)
            .sort((a, b) => b.height - a.height);

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
            itag: 'bestaudio', // Special itag for audio stream
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
        res.status(500).json({ error: 'Video information nahi mil payi. URL ya network check karein.' });
    }
});

// 3. Video Download Route (GET)
app.get('/api/download', async (req, res) => {
    const { url, itag, quality, title = 'video' } = req.query;

    if (!url || !itag) {
        return res.status(400).send('Video URL aur Format ID (itag) zaruri hai.');
    }
    
    // File name ke liye title ko sanitize karna
    const cleanTitle = title.replace(/[^\w\s-]/g, '').trim(); 

    try {
        if (itag === 'bestaudio') {
            // --- MP3 Conversion Logic (using FFmpeg) ---
            res.header('Content-Disposition', `attachment; filename="${cleanTitle}_audio.mp3"`);
            res.header('Content-Type', 'audio/mpeg');

            const audioStream = ytdl(url, { filter: 'audioonly', quality: 'highestaudio' });

            ffmpeg(audioStream)
                .noVideo()
                .audioCodec('libmp3lame')
                .format('mp3')
                // Bug fix: Vercel environment mein logging level ko kam karte hain
                .outputOptions(['-loglevel error', '-acodec libmp3lame']) 
                .on('error', (err) => {
                    console.error('FFmpeg MP3 Error:', err.message);
                    if (!res.headersSent) {
                        // Agar error aaye to stream close kar dein
                        res.status(500).end('MP3 conversion mein galti ho gayi.');
                    }
                })
                .pipe(res, { end: true });

        } else {
            // --- Standard Video Download Logic (MP4) ---
            res.header('Content-Disposition', `attachment; filename="${cleanTitle}_${quality.replace(/\s/g, '_')}.mp4"`);
            res.header('Content-Type', 'video/mp4');

            // Video stream bina audio ke bhi download ho sakti hai. ytdl khud merge karta hai.
            const videoStream = ytdl(url, { 
                filter: format => format.itag == itag && format.hasVideo && format.hasAudio,
                quality: 'highestvideo' 
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
