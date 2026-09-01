/**
 * ذخیره فایل (گزارش‌های PDF/Excel) — سازگار با S3/MinIO/Arvan Object Storage
 */
const { S3Client, PutObjectCommand, GetObjectCommand } = require('@aws-sdk/client-s3');
const { getSignedUrl } = require('@aws-sdk/s3-request-presigner');

const s3 = new S3Client({
  endpoint: process.env.S3_ENDPOINT,        // مثلاً Arvan Cloud Object Storage برای میزبانی داخل ایران
  region: process.env.S3_REGION || 'default',
  credentials: {
    accessKeyId: process.env.S3_ACCESS_KEY,
    secretAccessKey: process.env.S3_SECRET_KEY,
  },
});

async function uploadToStorage(key, buffer, contentType) {
  await s3.send(new PutObjectCommand({
    Bucket: process.env.S3_BUCKET,
    Key: key,
    Body: buffer,
    ContentType: contentType,
  }));
  return key;
}

async function getSignedDownloadUrl(key, expiresInSeconds = 3600) {
  const command = new GetObjectCommand({ Bucket: process.env.S3_BUCKET, Key: key });
  return getSignedUrl(s3, command, { expiresIn: expiresInSeconds });
}

module.exports = { uploadToStorage, getSignedDownloadUrl };
