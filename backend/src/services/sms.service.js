/**
 * ارسال SMS برای کد OTP — نمونه با سرویس کاوه‌نگار (قابل تغییر به سایر providers ایرانی)
 */
const axios = require('axios');
const logger = require('../config/logger');

async function sendSms(phone, message) {
  if (process.env.NODE_ENV === 'development') {
    logger.info(`[SMS DEV MODE] به ${phone}: ${message}`);
    return { success: true, dev: true };
  }

  try {
    const response = await axios.post('https://api.kavenegar.com/v1/' + process.env.KAVENEGAR_API_KEY + '/sms/send.json', null, {
      params: {
        receptor: phone,
        message,
        sender: process.env.SMS_SENDER_NUMBER,
      },
    });
    return response.data;
  } catch (err) {
    logger.error('خطا در ارسال SMS:', err.message);
    throw new Error('ارسال پیامک ناموفق بود');
  }
}

module.exports = { sendSms };
