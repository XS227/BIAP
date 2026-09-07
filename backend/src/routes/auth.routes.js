/**
 * مسیرهای احراز هویت: ثبت‌نام، ورود، refresh، بازیابی و تغییر رمز عبور
 */
const crypto = require('crypto');
const express = require('express');
const rateLimit = require('express-rate-limit');
const bcrypt = require('bcrypt');
const jwt = require('jsonwebtoken');
const { query } = require('../config/db');
const { requireAuth } = require('../middleware/auth.middleware');
const {
  ensureAccountOpsSchema,
  normalizeClientContext,
  recordActivity,
  issuePasswordResetToken,
  consumePasswordResetToken,
  sendPasswordResetEmail,
} = require('../services/account-ops.service');

const router = express.Router();
const ACCESS_TTL_SECONDS = 15 * 60;
const REFRESH_TTL_DAYS = 30;

const resetRequestLimiter = rateLimit({ windowMs: 15 * 60 * 1000, max: 5, standardHeaders: true, legacyHeaders: false });
const resetSubmitLimiter = rateLimit({ windowMs: 15 * 60 * 1000, max: 10, standardHeaders: true, legacyHeaders: false });

function normalizeEmail(value) {
  return String(value || '').trim().toLowerCase();
}

function generateTokens(userId) {
  const accessToken = jwt.sign({ userId }, process.env.JWT_SECRET, { expiresIn: '15m' });
  const refreshToken = jwt.sign({ userId }, process.env.JWT_REFRESH_SECRET, { expiresIn: '30d' });
  return { accessToken, refreshToken };
}

function publicUser(user) {
  return {
    id: user.id,
    email: user.email,
    plan: user.plan,
    fullName: user.full_name || user.fullName || null,
  };
}

function authPayload(user, accessToken, refreshToken) {
  return {
    user: publicUser(user),
    accessToken,
    refreshToken,
    accessTokenExpiresAt: Math.floor(Date.now() / 1000) + ACCESS_TTL_SECONDS,
    refreshTokenTtlDays: REFRESH_TTL_DAYS,
  };
}

async function createSession(userId, refreshToken, req, context) {
  await ensureAccountOpsSchema();
  await query(
    `INSERT INTO auth_sessions
       (user_id, refresh_token, user_agent, ip_address, expires_at, last_seen_at, installation_id, app_version, platform)
     VALUES ($1, $2, $3, $4, now() + interval '30 days', now(), $5, $6, $7)`,
    [userId, refreshToken, req.headers['user-agent'], req.ip, context.installationId, context.appVersion, context.platform]
  );
}

function setRefreshCookie(res, refreshToken) {
  res.cookie('refresh_token', refreshToken, {
    httpOnly: true,
    secure: true,
    sameSite: 'strict',
    maxAge: REFRESH_TTL_DAYS * 24 * 3600 * 1000,
  });
}

// ── ثبت‌نام با ایمیل و رمز عبور ──
router.post('/signup', async (req, res, next) => {
  try {
    await ensureAccountOpsSchema();
    const email = normalizeEmail(req.body?.email);
    const { password, fullName, companyName } = req.body || {};
    const context = normalizeClientContext(req.body || {});
    if (!email || !password || password.length < 8) {
      return res.status(400).json({ error: 'ایمیل و رمز عبور حداقل ۸ کاراکتری الزامی است' });
    }

    const existing = await query('SELECT id FROM users WHERE email = $1', [email]);
    if (existing.rows.length) {
      return res.status(409).json({ error: 'این ایمیل قبلاً ثبت شده است' });
    }

    const passwordHash = await bcrypt.hash(password, 12);
    const { rows } = await query(
      `INSERT INTO users (email, password_hash, full_name, company_name, last_seen_at)
       VALUES ($1, $2, $3, $4, now()) RETURNING id, email, plan, full_name`,
      [email, passwordHash, fullName, companyName]
    );

    const user = rows[0];
    const { accessToken, refreshToken } = generateTokens(user.id);
    await createSession(user.id, refreshToken, req, context);
    await recordActivity({ eventType: 'signup', userId: user.id, ...context });

    setRefreshCookie(res, refreshToken);
    res.status(201).json(authPayload(user, accessToken, refreshToken));
  } catch (err) {
    next(err);
  }
});

// ── ورود با ایمیل و رمز عبور ──
router.post('/login', async (req, res, next) => {
  try {
    await ensureAccountOpsSchema();
    const email = normalizeEmail(req.body?.email);
    const password = req.body?.password;
    const context = normalizeClientContext(req.body || {});
    const { rows } = await query('SELECT * FROM users WHERE email = $1', [email]);
    if (!rows.length) return res.status(401).json({ error: 'ایمیل یا رمز عبور اشتباه است' });

    const user = rows[0];
    const valid = await bcrypt.compare(password || '', user.password_hash || '');
    if (!valid) return res.status(401).json({ error: 'ایمیل یا رمز عبور اشتباه است' });

    const { accessToken, refreshToken } = generateTokens(user.id);
    await createSession(user.id, refreshToken, req, context);
    await query('UPDATE users SET last_login_at = now(), last_seen_at = now(), updated_at = now() WHERE id = $1', [user.id]);
    await recordActivity({ eventType: 'login', userId: user.id, ...context });

    setRefreshCookie(res, refreshToken);
    res.json(authPayload(user, accessToken, refreshToken));
  } catch (err) {
    next(err);
  }
});

// ── تازه‌سازی access token ──
router.post('/refresh', async (req, res) => {
  try {
    await ensureAccountOpsSchema();
    const refreshToken = req.body?.refreshToken || req.cookies?.refresh_token;
    if (!refreshToken) return res.status(401).json({ error: 'نشست یافت نشد' });

    const payload = jwt.verify(refreshToken, process.env.JWT_REFRESH_SECRET);
    const session = await query(
      `SELECT * FROM auth_sessions
       WHERE user_id = $1 AND refresh_token = $2 AND expires_at > now()`,
      [payload.userId, refreshToken]
    );
    if (!session.rows.length) return res.status(401).json({ error: 'نشست منقضی شده. دوباره وارد شوید' });

    await query('UPDATE auth_sessions SET last_seen_at = now() WHERE id = $1', [session.rows[0].id]);
    await query('UPDATE users SET last_seen_at = now() WHERE id = $1', [payload.userId]);
    const accessToken = jwt.sign({ userId: payload.userId }, process.env.JWT_SECRET, { expiresIn: '15m' });
    res.json({ accessToken, refreshToken, accessTokenExpiresAt: Math.floor(Date.now() / 1000) + ACCESS_TTL_SECONDS, refreshTokenTtlDays: REFRESH_TTL_DAYS });
  } catch (err) {
    res.status(401).json({ error: 'توکن نامعتبر است' });
  }
});

// ── خروج از حساب ──
router.post('/logout', async (req, res, next) => {
  try {
    await ensureAccountOpsSchema();
    const refreshToken = req.body?.refreshToken || req.cookies?.refresh_token;
    let userId = null;
    if (refreshToken) {
      try { userId = jwt.verify(refreshToken, process.env.JWT_REFRESH_SECRET)?.userId || null; } catch {}
      await query('DELETE FROM auth_sessions WHERE refresh_token = $1', [refreshToken]);
    }
    if (userId) await recordActivity({ eventType: 'logout', userId });
    res.clearCookie('refresh_token');
    res.json({ message: 'خروج با موفقیت انجام شد' });
  } catch (err) {
    next(err);
  }
});

// ── تغییر رمز برای کاربر واردشده ──
router.post('/change-password', requireAuth, async (req, res, next) => {
  try {
    await ensureAccountOpsSchema();
    const currentPassword = String(req.body?.currentPassword || '');
    const newPassword = String(req.body?.newPassword || '');
    const context = normalizeClientContext(req.body || {});
    if (newPassword.length < 8) return res.status(400).json({ error: 'رمز جدید باید حداقل ۸ کاراکتر باشد' });

    const { rows } = await query('SELECT * FROM users WHERE id = $1', [req.user.id]);
    const user = rows[0];
    const valid = user && await bcrypt.compare(currentPassword, user.password_hash || '');
    if (!valid) return res.status(400).json({ error: 'رمز فعلی صحیح نیست' });

    const passwordHash = await bcrypt.hash(newPassword, 12);
    await query('UPDATE users SET password_hash = $1, updated_at = now(), last_seen_at = now() WHERE id = $2', [passwordHash, req.user.id]);
    await query('DELETE FROM auth_sessions WHERE user_id = $1', [req.user.id]);

    const { accessToken, refreshToken } = generateTokens(req.user.id);
    await createSession(req.user.id, refreshToken, req, context);
    await recordActivity({ eventType: 'password_changed', userId: req.user.id, ...context });
    setRefreshCookie(res, refreshToken);
    res.json(authPayload(user, accessToken, refreshToken));
  } catch (err) {
    next(err);
  }
});

// ── درخواست بازیابی؛ پاسخ همیشه عمومی است تا وجود ایمیل افشا نشود ──
router.post('/forgot-password', resetRequestLimiter, async (req, res, next) => {
  const generic = { message: 'اگر این ایمیل در BIAP ثبت شده باشد، کد بازیابی ارسال می‌شود.' };
  try {
    await ensureAccountOpsSchema();
    const email = normalizeEmail(req.body?.email);
    const context = normalizeClientContext(req.body || {});
    if (!email) return res.status(202).json(generic);

    const { rows } = await query('SELECT id, email FROM users WHERE email = $1 AND is_active = true', [email]);
    const emailHash = crypto.createHash('sha256').update(email).digest('hex').slice(0, 16);
    if (!rows.length) {
      await recordActivity({ eventType: 'password_reset_request', ...context, metadata: { accountMatched: false, emailHash } });
      return res.status(202).json(generic);
    }

    const user = rows[0];
    const token = await issuePasswordResetToken(user.id, 30);
    const delivery = await sendPasswordResetEmail(user.email, token);
    await recordActivity({
      eventType: 'password_reset_request',
      userId: user.id,
      ...context,
      metadata: { accountMatched: true, mailConfigured: delivery.configured, mailSent: delivery.sent },
    });
    return res.status(202).json(generic);
  } catch (err) {
    next(err);
  }
});

// ── مصرف کد یک‌بارمصرف و ابطال همه refresh sessionهای قبلی ──
router.post('/reset-password', resetSubmitLimiter, async (req, res, next) => {
  try {
    const token = String(req.body?.token || '').trim();
    const newPassword = String(req.body?.newPassword || '');
    const context = normalizeClientContext(req.body || {});
    if (!token || newPassword.length < 8) return res.status(400).json({ error: 'کد بازیابی و رمز جدید حداقل ۸ کاراکتری الزامی است' });

    const passwordHash = await bcrypt.hash(newPassword, 12);
    const userId = await consumePasswordResetToken(token, passwordHash);
    if (!userId) return res.status(400).json({ error: 'کد بازیابی نامعتبر یا منقضی شده است' });

    await recordActivity({ eventType: 'password_reset_completed', userId, ...context });
    res.json({ message: 'رمز عبور تغییر کرد. لطفاً دوباره وارد شوید.' });
  } catch (err) {
    next(err);
  }
});

module.exports = router;
