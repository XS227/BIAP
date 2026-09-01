/**
 * مدیریت اتصال‌های غیر-OAuth (مثل آپلود فایل از CRM های دیگر)
 * اتصال‌های OAuth واقعی (Google Analytics/Ads) در google-oauth.routes.js هستند
 */
const express = require('express');
const { requireAuth } = require('../middleware/auth.middleware');
const { query } = require('../config/db');

const router = express.Router();

// ── لیست انواع اتصال پشتیبانی‌شده ──
router.get('/providers', (req, res) => {
  res.json({
    providers: [
      { id: 'google_analytics', name: 'Google Analytics', authType: 'oauth', tabs: ['data', 'bizdev'] },
      { id: 'google_ads', name: 'Google Ads', authType: 'oauth', tabs: ['bizdev', 'data'] },
      { id: 'tsetmc', name: 'بورس تهران (TSETMC)', authType: 'none', tabs: ['stock'] },
      { id: 'manual_crm', name: 'فایل CRM دستی', authType: 'csv_upload', tabs: ['bizdev'] },
    ],
  });
});

// ── وضعیت کلی اتصال‌های کاربر برای یک پروژه ──
router.get('/status/:projectId', requireAuth, async (req, res, next) => {
  try {
    const { rows } = await query(
      `SELECT provider, status, last_synced_at FROM external_integrations
       WHERE project_id = $1 AND user_id = $2`,
      [req.params.projectId, req.user.id]
    );
    res.json({ integrations: rows });
  } catch (err) {
    next(err);
  }
});

module.exports = router;
