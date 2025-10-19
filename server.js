// File: server.js - Local Testing/Development Ke Liye

const app = require('./api/index'); // Vercel code import kiya

const PORT = process.env.PORT || 3000;

app.listen(PORT, () => {
    console.log(`\n======================================================`);
    console.log(`✅ Multi-Platform Backend Server is Ready!`);
    console.log(`Server running on: http://localhost:${PORT}`);
    console.log(`======================================================`);
    console.log(`Testing Tips:`);
    console.log(` - Use POST on /api/fetch-info with { "url": "video-link" }`);
    console.log(` - Make sure FFmpeg is installed on your local machine for MP3 to work.`);
    console.log(`\n`);
});
