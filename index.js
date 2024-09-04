const express = require('express');
const { exec } = require('child_process');
const bodyParser = require('body-parser');
const app = express();

// Middleware
app.use(bodyParser.json());
app.use(bodyParser.urlencoded({ extended: true }));

// API Endpoint for downloading videos
app.post('/download', (req, res) => {
    const videoUrl = req.body.url;
    const platform = req.body.platform; // Example: 'youtube', 'facebook'

    if (!videoUrl || !platform) {
        return res.status(400).json({ error: 'Missing URL or platform' });
    }

    // Call Python script with URL and platform arguments
    exec(`python3 download_video.py ${videoUrl} ${platform}`, (error, stdout, stderr) => {
        if (error) {
            console.error(`exec error: ${error}`);
            return res.status(500).json({ error: 'Failed to download the video' });
        }

        // Respond with the file path if download is successful
        res.json({ message: 'Video downloaded successfully', path: stdout.trim() });
    });
});

// Server setup
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`Server running on port ${PORT}`);
});
