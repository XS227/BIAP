'use strict';

const crypto = require('crypto');
const express = require('express');
const { query } = require('../config/db');
const { ensureAccountOpsSchema } = require('../services/account-ops.service');

const router = express.Router();

function secureEqual(a, b) {
  const left = Buffer.from(String(a || ''));
  const right = Buffer.from(String(b || ''));
  return left.length === right.length && left.length > 0 && crypto.timingSafeEqual(left, right);
}

function requireAdminApi(req, res, next) {
  const expected = process.env.BIAP_ADMIN_API_TOKEN || '';
  if (!expected) return res.status(503).json({ error: 'admin analytics API is not configured' });
  const header = String(req.headers['x-biap-admin-token'] || req.headers.authorization || '');
  const supplied = header.toLowerCase().startsWith('bearer ') ? header.slice(7).trim() : header.trim();
  if (!secureEqual(supplied, expected)) return res.status(401).json({ error: 'invalid admin token' });
  next();
}

router.use(requireAdminApi);

router.get('/ops/summary', async (req, res, next) => {
  try {
    await ensureAccountOpsSchema();
    const [users, installs, sessions, active, versions] = await Promise.all([
      query('SELECT COUNT(*)::int AS count FROM users'),
      query('SELECT COUNT(*)::int AS count FROM app_installations'),
      query('SELECT COUNT(*)::int AS count FROM auth_sessions WHERE expires_at > now()'),
      query(`
        SELECT
          COUNT(DISTINCT user_id) FILTER (WHERE user_id IS NOT NULL AND created_at >= now() - interval '24 hours')::int AS d1,
          COUNT(DISTINCT user_id) FILTER (WHERE user_id IS NOT NULL AND created_at >= now() - interval '7 days')::int AS d7,
          COUNT(DISTINCT user_id) FILTER (WHERE user_id IS NOT NULL AND created_at >= now() - interval '30 days')::int AS d30
        FROM app_activity_events
      `),
      query(`
        SELECT COALESCE(NULLIF(app_version, ''), 'unknown') AS version, COUNT(*)::int AS installs
        FROM app_installations
        GROUP BY 1 ORDER BY installs DESC, version ASC LIMIT 30
      `),
    ]);
    res.json({
      registeredUsers: users.rows[0]?.count || 0,
      approximateInstalls: installs.rows[0]?.count || 0,
      activeSessions: sessions.rows[0]?.count || 0,
      activeUsers24h: active.rows[0]?.d1 || 0,
      activeUsers7d: active.rows[0]?.d7 || 0,
      activeUsers30d: active.rows[0]?.d30 || 0,
      appVersions: versions.rows,
    });
  } catch (err) {
    next(err);
  }
});

router.get('/ops/users', async (req, res, next) => {
  try {
    await ensureAccountOpsSchema();
    const limit = Math.max(1, Math.min(Number(req.query.limit) || 200, 500));
    const { rows } = await query(`
      SELECT
        u.id, u.email, u.full_name, u.plan, u.is_active, u.created_at,
        u.last_login_at, u.last_seen_at,
        COUNT(s.id) FILTER (WHERE s.expires_at > now())::int AS active_sessions,
        (SELECT ai.app_version FROM app_installations ai WHERE ai.user_id = u.id ORDER BY ai.last_seen_at DESC LIMIT 1) AS app_version,
        (SELECT ai.platform FROM app_installations ai WHERE ai.user_id = u.id ORDER BY ai.last_seen_at DESC LIMIT 1) AS platform
      FROM users u
      LEFT JOIN auth_sessions s ON s.user_id = u.id
      GROUP BY u.id
      ORDER BY COALESCE(u.last_seen_at, u.last_login_at, u.created_at) DESC
      LIMIT $1
    `, [limit]);
    res.json({ items: rows });
  } catch (err) {
    next(err);
  }
});

router.get('/ops/installs', async (req, res, next) => {
  try {
    await ensureAccountOpsSchema();
    const limit = Math.max(1, Math.min(Number(req.query.limit) || 250, 1000));
    const { rows } = await query(`
      SELECT installation_id, user_id, platform, app_version, first_seen_at, last_seen_at
      FROM app_installations
      ORDER BY last_seen_at DESC
      LIMIT $1
    `, [limit]);
    res.json({ items: rows });
  } catch (err) {
    next(err);
  }
});

router.get('/ops/activity', async (req, res, next) => {
  try {
    await ensureAccountOpsSchema();
    const limit = Math.max(1, Math.min(Number(req.query.limit) || 300, 1000));
    const userId = req.query.userId ? String(req.query.userId) : null;
    const params = userId ? [userId, limit] : [limit];
    const where = userId ? 'WHERE e.user_id = $1' : '';
    const limitParam = userId ? '$2' : '$1';
    const { rows } = await query(`
      SELECT e.id, e.user_id, u.email, e.installation_id, e.event_type, e.metadata_json,
             e.platform, e.app_version, e.created_at
      FROM app_activity_events e
      LEFT JOIN users u ON u.id = e.user_id
      ${where}
      ORDER BY e.created_at DESC
      LIMIT ${limitParam}
    `, params);
    res.json({ items: rows });
  } catch (err) {
    next(err);
  }
});

module.exports = router;
