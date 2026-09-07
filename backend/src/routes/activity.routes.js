'use strict';

const express = require('express');
const jwt = require('jsonwebtoken');
const { SAFE_EVENTS, normalizeClientContext, recordActivity } = require('../services/account-ops.service');

const router = express.Router();

function optionalUserId(req) {
  const header = String(req.headers.authorization || '');
  if (!header.startsWith('Bearer ')) return null;
  const token = header.slice(7).trim();
  if (!token) return null;
  try {
    const payload = jwt.verify(token, process.env.JWT_SECRET);
    return payload.userId || null;
  } catch {
    return null;
  }
}

router.post('/event', async (req, res, next) => {
  try {
    const eventType = String(req.body?.eventType || '').trim();
    if (!SAFE_EVENTS.has(eventType)) {
      return res.status(400).json({ error: 'event type is not allowed' });
    }
    const context = normalizeClientContext(req.body || {});
    await recordActivity({
      eventType,
      userId: optionalUserId(req),
      ...context,
      metadata: req.body?.metadata,
    });
    return res.status(202).json({ ok: true });
  } catch (err) {
    next(err);
  }
});

module.exports = router;
