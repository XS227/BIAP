'use strict';

const crypto = require('crypto');
const net = require('net');
const tls = require('tls');
const { pool, query } = require('../config/db');
const logger = require('../config/logger');

const SAFE_EVENTS = new Set([
  'install',
  'app_open',
  'signup',
  'login',
  'logout',
  'company_selected',
  'module_opened',
  'recommendation_viewed',
  'paper_order',
  'data_import',
  'password_reset_request',
  'password_reset_completed',
  'password_changed',
]);

const SENSITIVE_KEY = /(pass(word)?|token|secret|api.?key|authorization|cookie|raw|dataset|file.?data)/i;
let schemaPromise = null;

function ensureAccountOpsSchema() {
  if (!schemaPromise) {
    schemaPromise = (async () => {
      await query('ALTER TABLE users ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ');
      await query('ALTER TABLE auth_sessions ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ');
      await query('ALTER TABLE auth_sessions ADD COLUMN IF NOT EXISTS installation_id VARCHAR(160)');
      await query('ALTER TABLE auth_sessions ADD COLUMN IF NOT EXISTS app_version VARCHAR(64)');
      await query('ALTER TABLE auth_sessions ADD COLUMN IF NOT EXISTS platform VARCHAR(32)');

      await query(`
        CREATE TABLE IF NOT EXISTS app_installations (
          installation_id VARCHAR(160) PRIMARY KEY,
          user_id UUID REFERENCES users(id) ON DELETE SET NULL,
          platform VARCHAR(32),
          app_version VARCHAR(64),
          first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
      `);
      await query('CREATE INDEX IF NOT EXISTS idx_app_installations_user ON app_installations(user_id)');
      await query('CREATE INDEX IF NOT EXISTS idx_app_installations_last_seen ON app_installations(last_seen_at)');

      await query(`
        CREATE TABLE IF NOT EXISTS app_activity_events (
          id BIGSERIAL PRIMARY KEY,
          user_id UUID REFERENCES users(id) ON DELETE SET NULL,
          installation_id VARCHAR(160),
          event_type VARCHAR(64) NOT NULL,
          metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
          platform VARCHAR(32),
          app_version VARCHAR(64),
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
      `);
      await query('CREATE INDEX IF NOT EXISTS idx_activity_user_created ON app_activity_events(user_id, created_at DESC)');
      await query('CREATE INDEX IF NOT EXISTS idx_activity_install_created ON app_activity_events(installation_id, created_at DESC)');
      await query('CREATE INDEX IF NOT EXISTS idx_activity_type_created ON app_activity_events(event_type, created_at DESC)');

      await query(`
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
          id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          token_hash VARCHAR(64) UNIQUE NOT NULL,
          expires_at TIMESTAMPTZ NOT NULL,
          consumed_at TIMESTAMPTZ,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
      `);
      await query('CREATE INDEX IF NOT EXISTS idx_password_reset_user ON password_reset_tokens(user_id, created_at DESC)');
      await query('CREATE INDEX IF NOT EXISTS idx_password_reset_expiry ON password_reset_tokens(expires_at)');
    })().catch((err) => {
      schemaPromise = null;
      throw err;
    });
  }
  return schemaPromise;
}

function cleanString(value, max = 200) {
  if (value == null) return null;
  const text = String(value).trim();
  if (!text) return null;
  return text.slice(0, max);
}

function normalizeClientContext(input = {}) {
  return {
    installationId: cleanString(input.installationId || input.installation_id, 160),
    platform: cleanString(input.platform, 32),
    appVersion: cleanString(input.appVersion || input.app_version, 64),
  };
}

function safeMetadata(metadata) {
  if (!metadata || typeof metadata !== 'object' || Array.isArray(metadata)) return {};
  const out = {};
  for (const [key, value] of Object.entries(metadata).slice(0, 24)) {
    if (SENSITIVE_KEY.test(key)) continue;
    if (value == null || typeof value === 'boolean' || typeof value === 'number') {
      out[key.slice(0, 80)] = value;
    } else if (typeof value === 'string') {
      out[key.slice(0, 80)] = value.slice(0, 240);
    }
  }
  return out;
}

async function recordActivity({ eventType, userId = null, installationId = null, platform = null, appVersion = null, metadata = {} }) {
  if (!SAFE_EVENTS.has(eventType)) return false;
  await ensureAccountOpsSchema();
  const install = cleanString(installationId, 160);
  const plat = cleanString(platform, 32);
  const version = cleanString(appVersion, 64);
  const safe = safeMetadata(metadata);

  if (install) {
    await query(
      `INSERT INTO app_installations (installation_id, user_id, platform, app_version, first_seen_at, last_seen_at)
       VALUES ($1, $2, $3, $4, now(), now())
       ON CONFLICT (installation_id) DO UPDATE SET
         user_id = COALESCE(EXCLUDED.user_id, app_installations.user_id),
         platform = COALESCE(EXCLUDED.platform, app_installations.platform),
         app_version = COALESCE(EXCLUDED.app_version, app_installations.app_version),
         last_seen_at = now()`,
      [install, userId, plat, version]
    );
  }

  if (userId) {
    await query('UPDATE users SET last_seen_at = now(), updated_at = now() WHERE id = $1', [userId]);
  }

  await query(
    `INSERT INTO app_activity_events (user_id, installation_id, event_type, metadata_json, platform, app_version)
     VALUES ($1, $2, $3, $4::jsonb, $5, $6)`,
    [userId, install, eventType, JSON.stringify(safe), plat, version]
  );
  return true;
}

function makeResetToken() {
  return crypto.randomBytes(6).toString('hex').toUpperCase();
}

function hashResetToken(token) {
  return crypto.createHash('sha256').update(String(token || '').trim().toUpperCase()).digest('hex');
}

async function issuePasswordResetToken(userId, ttlMinutes = 30) {
  await ensureAccountOpsSchema();
  const token = makeResetToken();
  const tokenHash = hashResetToken(token);
  await query(
    `UPDATE password_reset_tokens
     SET consumed_at = COALESCE(consumed_at, now())
     WHERE user_id = $1 AND consumed_at IS NULL`,
    [userId]
  );
  await query(
    `INSERT INTO password_reset_tokens (user_id, token_hash, expires_at)
     VALUES ($1, $2, now() + ($3::text || ' minutes')::interval)`,
    [userId, tokenHash, Math.max(5, Math.min(Number(ttlMinutes) || 30, 120))]
  );
  return token;
}

async function consumePasswordResetToken(token, newPasswordHash) {
  await ensureAccountOpsSchema();
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const tokenHash = hashResetToken(token);
    const found = await client.query(
      `SELECT id, user_id FROM password_reset_tokens
       WHERE token_hash = $1 AND consumed_at IS NULL AND expires_at > now()
       FOR UPDATE`,
      [tokenHash]
    );
    if (!found.rows.length) {
      await client.query('ROLLBACK');
      return null;
    }
    const row = found.rows[0];
    await client.query('UPDATE users SET password_hash = $1, updated_at = now() WHERE id = $2', [newPasswordHash, row.user_id]);
    await client.query('UPDATE password_reset_tokens SET consumed_at = now() WHERE id = $1', [row.id]);
    await client.query('DELETE FROM auth_sessions WHERE user_id = $1', [row.user_id]);
    await client.query('COMMIT');
    return row.user_id;
  } catch (err) {
    await client.query('ROLLBACK').catch(() => {});
    throw err;
  } finally {
    client.release();
  }
}

function smtpConfigured() {
  return Boolean(process.env.SMTP_HOST && process.env.SMTP_FROM);
}

function waitEvent(emitter, event, errorEvent = 'error') {
  return new Promise((resolve, reject) => {
    const onEvent = (...args) => { cleanup(); resolve(args); };
    const onError = (err) => { cleanup(); reject(err); };
    const cleanup = () => {
      emitter.removeListener(event, onEvent);
      emitter.removeListener(errorEvent, onError);
    };
    emitter.once(event, onEvent);
    emitter.once(errorEvent, onError);
  });
}

function readReply(socket) {
  return new Promise((resolve, reject) => {
    let buffer = '';
    const onData = (chunk) => {
      buffer += chunk.toString('utf8');
      const lines = buffer.split(/\r?\n/).filter(Boolean);
      const last = lines[lines.length - 1] || '';
      if (/^\d{3} /.test(last)) {
        cleanup();
        resolve({ code: Number(last.slice(0, 3)), text: buffer });
      }
    };
    const onError = (err) => { cleanup(); reject(err); };
    const onClose = () => { cleanup(); reject(new Error('SMTP connection closed')); };
    const cleanup = () => {
      socket.removeListener('data', onData);
      socket.removeListener('error', onError);
      socket.removeListener('close', onClose);
    };
    socket.on('data', onData);
    socket.once('error', onError);
    socket.once('close', onClose);
  });
}

async function smtpCommand(socket, command, expected) {
  socket.write(`${command}\r\n`);
  const reply = await readReply(socket);
  const allowed = Array.isArray(expected) ? expected : [expected];
  if (!allowed.includes(reply.code)) throw new Error(`SMTP ${command.split(' ')[0]} failed: ${reply.code}`);
  return reply;
}

function encodeSubject(subject) {
  return `=?UTF-8?B?${Buffer.from(subject, 'utf8').toString('base64')}?=`;
}

async function sendSmtpMail({ to, subject, text }) {
  const host = process.env.SMTP_HOST;
  const port = Number(process.env.SMTP_PORT || 587);
  const user = process.env.SMTP_USER || '';
  const pass = process.env.SMTP_PASS || '';
  const from = process.env.SMTP_FROM;
  const directTls = String(process.env.SMTP_SECURE || '').toLowerCase() === 'true' || port === 465;
  if (!host || !from) throw new Error('SMTP is not configured');

  let socket;
  if (directTls) {
    socket = tls.connect({ host, port, servername: host, rejectUnauthorized: true });
    await waitEvent(socket, 'secureConnect');
  } else {
    socket = net.createConnection({ host, port });
    await waitEvent(socket, 'connect');
  }

  try {
    let reply = await readReply(socket);
    if (reply.code !== 220) throw new Error(`SMTP greeting failed: ${reply.code}`);
    reply = await smtpCommand(socket, 'EHLO biap.dadashi.no', 250);

    if (!directTls) {
      if (!/STARTTLS/i.test(reply.text)) throw new Error('SMTP server does not advertise STARTTLS');
      await smtpCommand(socket, 'STARTTLS', 220);
      socket = tls.connect({ socket, servername: host, rejectUnauthorized: true });
      await waitEvent(socket, 'secureConnect');
      await smtpCommand(socket, 'EHLO biap.dadashi.no', 250);
    }

    if (user || pass) {
      await smtpCommand(socket, 'AUTH LOGIN', 334);
      await smtpCommand(socket, Buffer.from(user).toString('base64'), 334);
      await smtpCommand(socket, Buffer.from(pass).toString('base64'), 235);
    }

    await smtpCommand(socket, `MAIL FROM:<${from}>`, 250);
    await smtpCommand(socket, `RCPT TO:<${to}>`, [250, 251]);
    await smtpCommand(socket, 'DATA', 354);
    const safeTextBody = String(text).replace(/^\./gm, '..');
    const message = [
      `From: BIAP <${from}>`,
      `To: <${to}>`,
      `Subject: ${encodeSubject(subject)}`,
      'MIME-Version: 1.0',
      'Content-Type: text/plain; charset=UTF-8',
      'Content-Transfer-Encoding: 8bit',
      '',
      safeTextBody,
      '.',
      '',
    ].join('\r\n');
    socket.write(message);
    reply = await readReply(socket);
    if (reply.code !== 250) throw new Error(`SMTP DATA failed: ${reply.code}`);
    await smtpCommand(socket, 'QUIT', 221).catch(() => {});
  } finally {
    socket.destroy();
  }
}

async function sendPasswordResetEmail(email, token) {
  if (!smtpConfigured()) return { configured: false, sent: false };
  try {
    await sendSmtpMail({
      to: email,
      subject: 'کد بازیابی رمز عبور BIAP',
      text: `کد یک‌بارمصرف بازیابی رمز عبور BIAP:\n\n${token}\n\nاین کد تا ۳۰ دقیقه معتبر است. اگر شما این درخواست را نداده‌اید، این پیام را نادیده بگیرید.`,
    });
    return { configured: true, sent: true };
  } catch (err) {
    logger.error('Password reset email delivery failed', { message: err.message });
    return { configured: true, sent: false };
  }
}

module.exports = {
  SAFE_EVENTS,
  ensureAccountOpsSchema,
  normalizeClientContext,
  safeMetadata,
  recordActivity,
  issuePasswordResetToken,
  consumePasswordResetToken,
  sendPasswordResetEmail,
  smtpConfigured,
};
