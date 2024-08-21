const functions = require("firebase-functions");
const admin = require("firebase-admin");
const ytDlp = require("yt-dlp-wrap").default;
const { v4: uuidv4 } = require("uuid");
const path = require("path");
const os = require("os");
const fs = require("fs");

admin.initializeApp();
const db = admin.firestore();
const bucket = admin.storage().bucket();

exports.downloadVideo = functions.https.onRequest(async (req, res) => {
  const videoUrl = req.body.url;
  const downloadId = uuidv4();

  const ytdlp = new ytDlp();

  try {
    const info = await ytdlp.getVideoInfo(videoUrl);
    const formats = info.formats.map((format) => ({
      format_id: format.format_id,
      format_note: format.format_note,
      resolution: format.resolution,
      filesize: format.filesize,
    }));

    await db.collection("downloads").doc(downloadId).set({
      progress: "0%",
      formats: formats,
    });

    res.status(200).json({ downloadId, formats });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

exports.startDownload = functions.https.onRequest(async (req, res) => {
  const { downloadId, formatId, url } = req.body;

  const ytdlp = new ytDlp();
  const tempFilePath = path.join(os.tmpdir(), `${downloadId}.mp4`);

  ytdlp
    .exec([
      url,
      "--format",
      formatId,
      "--output",
      tempFilePath,
    ])
    .on("progress", (progress) => {
      db.collection("downloads")
        .doc(downloadId)
        .update({ progress: `${progress.percent}%` });
    })
    .on("close", async () => {
      const [file] = await bucket.upload(tempFilePath, {
        destination: `videos/${downloadId}.mp4`,
        metadata: { metadata: { firebaseStorageDownloadTokens: uuidv4() } },
      });

      fs.unlinkSync(tempFilePath);

      await db.collection("downloads").doc(downloadId).update({
        progress: "100%",
        downloadUrl: file.metadata.mediaLink,
      });

      res.status(200).json({ downloadUrl: file.metadata.mediaLink });
    })
    .on("error", (error) => {
      res.status(500).json({ error: error.message });
    });
});
