/**
 * مسیرهای احراز هویت: ثبت‌نام، ورود، OTP
 * رفع نیاز «مرحله ۲: حساب کاربری» از برنامه تکمیل MVP
 */
const express = require('express');
const bcrypt = require('bcrypt');
const jwt = require('jsonwebtoken');
const { query } = require('../config/db');

const router = express.Router();

function generateTokens(userId) {
  const accessToken = jwt.sign({ userId }, process.env.JWT_SECRET, { expiresIn: '15m' });
  const refreshToken = jwt.sign({ userId }, process.env.JWT_REFRESH_SECRET, { expiresIn: '30d' });
  return { accessToken, refreshToken };
}

// ── ثبت‌نام با ایمیل و رمز عبور ──
router.post('/signup', async (req, res, next) => {
  try {
    const { email, password, fullName, companyName } = req.body;
    if (!email || !password || password.length < 8) {
      return res.status(400).json({ error: 'ایمیل و رمز عبور حداقل ۸ کاراکتری الزامی است' });
    }

    const existing = await query('SELECT id FROM users WHERE email = $1', [email]);
    if (existing.rows.length) {
      return res.status(409).json({ error: 'این ایمیل قبلاً ثبت شده است' });
    }

    const passwordHash = await bcrypt.hash(password, 12);
    const { rows } = await query(
      `INSERT INTO users (email, password_hash, full_name, company_name)
       VALUES ($1, $2, $3, $4) RETURNING id, email, plan`,
      [email, passwordHash, fullName, companyName]
    );

    const user = rows[0];
    const { accessToken, refreshToken } = generateTokens(user.id);

    await query(
      `INSERT INTO auth_sessions (user_id, refresh_token, user_agent, ip_address, expires_at)
       VALUES ($1, $2, $3, $4, now() + interval '30 days')`,
      [user.id, refreshToken, req.headers['user-agent'], req.ip]
    );

    res.cookie('refresh_token', refreshToken, { httpOnly: true, secure: true, sameSite: 'strict', maxAge: 30 * 24 * 3600 * 1000 });
    res.status(201).json({ user, accessToken });
  } catch (err) {
    next(err);
  }
});

// ── ورود با ایمیل و رمز عبور ──
router.post('/login', async (req, res, next) => {
  try {
    const { email, password } = req.body;
    const { rows } = await query('SELECT * FROM users WHERE email = $1', [email]);
    if (!rows.length) return res.status(401).json({ error: 'ایمیل یا رمز عبور اشتباه است' });

    const user = rows[0];
    const valid = await bcrypt.compare(password, user.password_hash || '');
    if (!valid) return res.status(401).json({ error: 'ایمیل یا رمز عبور اشتباه است' });

    const { accessToken, refreshToken } = generateTokens(user.id);

    await query(
      `INSERT INTO auth_sessions (user_id, refresh_token, user_agent, ip_address, expires_at)
       VALUES ($1, $2, $3, $4, now() + interval '30 days')`,
      [user.id, refreshToken, req.headers['user-agent'], req.ip]
    );
    await query('UPDATE users SET last_login_at = now() WHERE id = $1', [user.id]);

    res.cookie('refresh_token', refreshToken, { httpOnly: true, secure: true, sameSite: 'strict', maxAge: 30 * 24 * 3600 * 1000 });
    res.json({
      user: { id: user.id, email: user.email, plan: user.plan, fullName: user.full_name },
      accessToken,
    });
  } catch (err) {
    next(err);
  }
});

// ── تازه‌سازی access token با استفاده از refresh token ──
router.post('/refresh', async (req, res, next) => {
  try {
    const refreshToken = req.cookies?.refresh_token;
    if (!refreshToken) return res.status(401).json({ error: 'نشست یافت نشد' });

    const payload = jwt.verify(refreshToken, process.env.JWT_REFRESH_SECRET);

    const session = await query(
      'SELECT * FROM auth_sessions WHERE user_id = $1 AND refresh_token = $2 AND expires_at > now()',
      [payload.userId, refreshToken]
    );
    if (!session.rows.length) return res.status(401).json({ error: 'نشست منقضی شده. دوباره وارد شوید' });

    const accessToken = jwt.sign({ userId: payload.userId }, process.env.JWT_SECRET, { expiresIn: '15m' });
    res.json({ accessToken });
  } catch (err) {
    res.status(401).json({ error: 'توکن نامعتبر است' });
  }
});

// ── خروج از حساب ──
router.post('/logout', async (req, res) => {
  const refreshToken = req.cookies?.refresh_token;
  if (refreshToken) {
    await query('DELETE FROM auth_sessions WHERE refresh_token = $1', [refreshToken]);
  }
  res.clearCookie('refresh_token');
  res.json({ message: 'خروج با موفقیت انجام شد' });
});

module.exports = router;
