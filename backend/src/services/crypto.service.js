/**
 * رمزنگاری توکن‌های OAuth قبل از ذخیره در دیتابیس
 * هرگز توکن خام (access_token / refresh_token) را در دیتابیس ذخیره نکنید.
 */
const crypto = require('crypto');

const ALGORITHM = 'aes-256-gcm';
const KEY = Buffer.from(process.env.TOKEN_ENCRYPTION_KEY, 'hex'); // باید ۳۲ بایت (۶۴ کاراکتر hex) باشد

function encrypt(plainText) {
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv(ALGORITHM, KEY, iv);
  const encrypted = Buffer.concat([cipher.update(plainText, 'utf8'), cipher.final()]);
  const authTag = cipher.getAuthTag();
  // ذخیره به‌صورت: iv:authTag:encryptedData (همه hex)
  return `${iv.toString('hex')}:${authTag.toString('hex')}:${encrypted.toString('hex')}`;
}

function decrypt(payload) {
  const [ivHex, authTagHex, encryptedHex] = payload.split(':');
  const iv = Buffer.from(ivHex, 'hex');
  const authTag = Buffer.from(authTagHex, 'hex');
  const encrypted = Buffer.from(encryptedHex, 'hex');
  const decipher = crypto.createDecipheriv(ALGORITHM, KEY, iv);
  decipher.setAuthTag(authTag);
  const decrypted = Buffer.concat([decipher.update(encrypted), decipher.final()]);
  return decrypted.toString('utf8');
}

module.exports = { encrypt, decrypt };
