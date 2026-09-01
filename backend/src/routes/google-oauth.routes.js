/**
 * اتصال واقعی به Google Analytics و Google Ads با OAuth 2.0
 * این فایل مستقیماً نیاز «اتصال واقعی Analytics» که در چت درخواست شد را پیاده می‌کند.
 *
 * جریان کار (Flow):
 *  ۱. کاربر روی «اتصال Google Analytics» کلیک می‌کند
 *  ۲. به صفحه login.google.com هدایت می‌شود (نه ما — گوگل خودش این صفحه را نشان می‌دهد)
 *  ۳. کاربر دسترسی را تایید می‌کند → گوگل او را به callback ما برمی‌گرداند با یک کد
 *  ۴. سرور آن کد را به access_token و refresh_token تبدیل می‌کند
 *  ۵. توکن‌ها رمزنگاری و در دیتابیس ذخیره می‌شوند (هرگز خام ذخیره نمی‌شوند)
 */
const express = require('express');
const { google } = require('googleapis');
const { requireAuth } = require('../middleware/auth.middleware');
const { query } = require('../config/db');
const { encrypt, decrypt } = require('../services/crypto.service');
const logger = require('../config/logger');

const router = express.Router();

const SCOPES = {
  analytics: ['https://www.googleapis.com/auth/analytics.readonly'],
  ads: ['https://www.googleapis.com/auth/adwords'],
};

function getOAuthClient() {
  return new google.auth.OAuth2(
    process.env.GOOGLE_CLIENT_ID,
    process.env.GOOGLE_CLIENT_SECRET,
    process.env.GOOGLE_OAUTH_REDIRECT_URI // مثلاً https://api.biap.ir/api/oauth/google/callback
  );
}

// ── گام ۱: شروع اتصال — کاربر را به صفحه گوگل هدایت می‌کند ──
router.get('/connect/:provider', requireAuth, (req, res) => {
  const { provider } = req.params; // 'analytics' یا 'ads'
  const { projectId } = req.query;

  if (!SCOPES[provider]) {
    return res.status(400).json({ error: 'سرویس نامعتبر است' });
  }

  const oauth2Client = getOAuthClient();

  // state شامل اطلاعاتی است که بعد از بازگشت از گوگل نیاز داریم (کاربر، پروژه، نوع سرویس)
  const state = Buffer.from(JSON.stringify({ userId: req.user.id, projectId, provider })).toString('base64');

  const authUrl = oauth2Client.generateAuthUrl({
    access_type: 'offline',       // برای دریافت refresh_token
    scope: SCOPES[provider],
    prompt: 'consent',
    state,
  });

  res.json({ authUrl }); // فرانت‌اند کاربر را به این آدرس redirect می‌کند
});

// ── گام ۲: Callback — گوگل کاربر را اینجا برمی‌گرداند ──
router.get('/callback', async (req, res) => {
  try {
    const { code, state } = req.query;
    const { userId, projectId, provider } = JSON.parse(Buffer.from(state, 'base64').toString());

    const oauth2Client = getOAuthClient();
    const { tokens } = await oauth2Client.getToken(code);
    // tokens = { access_token, refresh_token, expiry_date, scope, ... }

    // دریافت اطلاعات اکانت (مثلاً GA Property ID) برای نمایش به کاربر
    let accountId = null;
    if (provider === 'analytics') {
      oauth2Client.setCredentials(tokens);
      const analyticsAdmin = google.analyticsadmin({ version: 'v1beta', auth: oauth2Client });
      const accounts = await analyticsAdmin.accounts.list();
      accountId = accounts.data.accounts?.[0]?.name || null;
    }

    const accessTokenEnc = encrypt(tokens.access_token);
    const refreshTokenEnc = tokens.refresh_token ? encrypt(tokens.refresh_token) : null;

    await query(
      `INSERT INTO external_integrations
        (user_id, project_id, provider, provider_account_id, access_token_enc, refresh_token_enc, token_expires_at, scopes, status)
       VALUES ($1, $2, $3, $4, $5, $6, to_timestamp($7/1000.0), $8, 'connected')
       ON CONFLICT (user_id, provider, provider_account_id)
       DO UPDATE SET access_token_enc = $5, refresh_token_enc = COALESCE($6, external_integrations.refresh_token_enc),
                      token_expires_at = to_timestamp($7/1000.0), status = 'connected', updated_at = now()`,
      [userId, projectId, `google_${provider}`, accountId, accessTokenEnc, refreshTokenEnc, tokens.expiry_date, tokens.scope]
    );

    // ریدایرکت به فرانت‌اند با پیام موفقیت
    res.redirect(`${process.env.FRONTEND_URL}/integrations?status=success&provider=${provider}`);
  } catch (err) {
    logger.error('خطا در OAuth callback:', err);
    res.redirect(`${process.env.FRONTEND_URL}/integrations?status=error`);
  }
});

// ── همگام‌سازی داده واقعی از Google Analytics ──
router.post('/sync/analytics/:integrationId', requireAuth, async (req, res, next) => {
  try {
    const { rows } = await query(
      'SELECT * FROM external_integrations WHERE id = $1 AND user_id = $2',
      [req.params.integrationId, req.user.id]
    );
    if (!rows.length) return res.status(404).json({ error: 'اتصال یافت نشد' });

    const integration = rows[0];
    const oauth2Client = getOAuthClient();
    oauth2Client.setCredentials({
      access_token: decrypt(integration.access_token_enc),
      refresh_token: integration.refresh_token_enc ? decrypt(integration.refresh_token_enc) : undefined,
    });

    const analyticsData = google.analyticsdata({ version: 'v1beta', auth: oauth2Client });

    const response = await analyticsData.properties.runReport({
      property: integration.provider_account_id,
      requestBody: {
        dateRanges: [{ startDate: '30daysAgo', endDate: 'today' }],
        dimensions: [{ name: 'date' }],
        metrics: [
          { name: 'sessions' },
          { name: 'conversions' },
          { name: 'bounceRate' },
          { name: 'averageSessionDuration' },
        ],
      },
    });

    // ذخیره داده روزانه در دیتابیس
    const rowsData = response.data.rows || [];
    for (const row of rowsData) {
      const date = row.dimensionValues[0].value; // فرمت YYYYMMDD
      const formattedDate = `${date.slice(0, 4)}-${date.slice(4, 6)}-${date.slice(6, 8)}`;
      const metrics = {
        sessions: Number(row.metricValues[0].value),
        conversions: Number(row.metricValues[1].value),
        bounce_rate: Number(row.metricValues[2].value),
        avg_session_duration: Number(row.metricValues[3].value),
      };

      await query(
        `INSERT INTO integration_sync_data (integration_id, metric_date, metrics_json)
         VALUES ($1, $2, $3)
         ON CONFLICT (integration_id, metric_date) DO UPDATE SET metrics_json = $3, synced_at = now()`,
        [integration.id, formattedDate, JSON.stringify(metrics)]
      );
    }

    await query('UPDATE external_integrations SET last_synced_at = now() WHERE id = $1', [integration.id]);

    res.json({ message: `${rowsData.length} روز داده با موفقیت همگام‌سازی شد`, syncedDays: rowsData.length });
  } catch (err) {
    next(err);
  }
});

// ── لیست اتصال‌های فعال کاربر ──
router.get('/list', requireAuth, async (req, res, next) => {
  try {
    const { rows } = await query(
      `SELECT id, provider, provider_account_id, status, last_synced_at, created_at
       FROM external_integrations WHERE user_id = $1 ORDER BY created_at DESC`,
      [req.user.id]
    );
    res.json({ integrations: rows });
  } catch (err) {
    next(err);
  }
});

// ── قطع اتصال ──
router.delete('/:integrationId', requireAuth, async (req, res, next) => {
  try {
    await query('DELETE FROM external_integrations WHERE id = $1 AND user_id = $2', [req.params.integrationId, req.user.id]);
    res.json({ message: 'اتصال با موفقیت قطع شد' });
  } catch (err) {
    next(err);
  }
});

module.exports = router;
