/**
 * مدیریت پروژه‌ها — رفع نیاز «ذخیره پروژه‌ها و تاریخچه» از برنامه تکمیل MVP
 */
const express = require('express');
const { requireAuth } = require('../middleware/auth.middleware');
const { query } = require('../config/db');

const router = express.Router();

// ── لیست پروژه‌های کاربر ──
router.get('/', requireAuth, async (req, res, next) => {
  try {
    const { rows } = await query(
      'SELECT id, name, tab, created_at, updated_at FROM projects WHERE user_id = $1 ORDER BY updated_at DESC',
      [req.user.id]
    );
    res.json({ projects: rows });
  } catch (err) {
    next(err);
  }
});

// ── ایجاد پروژه جدید ──
router.post('/', requireAuth, async (req, res, next) => {
  try {
    const { name, tab } = req.body;
    if (!name || !['stock', 'bizdev', 'data'].includes(tab)) {
      return res.status(400).json({ error: 'نام و نوع تب (stock/bizdev/data) الزامی است' });
    }
    const { rows } = await query(
      'INSERT INTO projects (user_id, name, tab) VALUES ($1, $2, $3) RETURNING *',
      [req.user.id, name, tab]
    );
    res.status(201).json({ project: rows[0] });
  } catch (err) {
    next(err);
  }
});

// ── ذخیره داده ورودی برای یک پروژه (CSV/دستی) ──
router.post('/:projectId/datasets', requireAuth, async (req, res, next) => {
  try {
    const { sourceType, sourceLabel, rawData } = req.body;
    const proj = await query('SELECT id FROM projects WHERE id = $1 AND user_id = $2', [req.params.projectId, req.user.id]);
    if (!proj.rows.length) return res.status(403).json({ error: 'دسترسی ندارید' });

    const rowCount = rawData.split('\n').filter(Boolean).length - 1;
    const { rows } = await query(
      `INSERT INTO project_datasets (project_id, source_type, source_label, raw_data, row_count)
       VALUES ($1, $2, $3, $4, $5) RETURNING id, created_at`,
      [req.params.projectId, sourceType, sourceLabel, rawData, rowCount]
    );

    await query('UPDATE projects SET updated_at = now() WHERE id = $1', [req.params.projectId]);
    res.status(201).json({ dataset: rows[0] });
  } catch (err) {
    next(err);
  }
});

// ── آخرین داده ذخیره‌شده یک پروژه ──
router.get('/:projectId/datasets/latest', requireAuth, async (req, res, next) => {
  try {
    const proj = await query('SELECT id FROM projects WHERE id = $1 AND user_id = $2', [req.params.projectId, req.user.id]);
    if (!proj.rows.length) return res.status(403).json({ error: 'دسترسی ندارید' });

    const { rows } = await query(
      'SELECT * FROM project_datasets WHERE project_id = $1 ORDER BY created_at DESC LIMIT 1',
      [req.params.projectId]
    );
    res.json({ dataset: rows[0] || null });
  } catch (err) {
    next(err);
  }
});

// ── حذف پروژه ──
router.delete('/:projectId', requireAuth, async (req, res, next) => {
  try {
    await query('DELETE FROM projects WHERE id = $1 AND user_id = $2', [req.params.projectId, req.user.id]);
    res.json({ message: 'پروژه حذف شد' });
  } catch (err) {
    next(err);
  }
});

module.exports = router;
