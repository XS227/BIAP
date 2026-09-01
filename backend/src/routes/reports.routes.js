/**
 * تولید گزارش PDF/Excel — رفع نیاز «مرحله ۳: گزارش حرفه‌ای» از برنامه تکمیل MVP
 */
const express = require('express');
const ExcelJS = require('exceljs');
const PDFDocument = require('pdfkit');
const { requireAuth } = require('../middleware/auth.middleware');
const { query } = require('../config/db');
const { uploadToStorage } = require('../services/storage.service');

const router = express.Router();

// ── تولید گزارش PDF از یک تحلیل ──
router.post('/pdf/:analysisId', requireAuth, async (req, res, next) => {
  try {
    const { rows } = await query(
      `SELECT al.*, p.name as project_name FROM analysis_logs al
       JOIN projects p ON p.id = al.project_id
       WHERE al.id = $1 AND p.user_id = $2`,
      [req.params.analysisId, req.user.id]
    );
    if (!rows.length) return res.status(404).json({ error: 'تحلیل یافت نشد' });

    const analysis = rows[0];
    const doc = new PDFDocument({ margin: 50 });
    const buffers = [];
    doc.on('data', buffers.push.bind(buffers));

    doc.on('end', async () => {
      const pdfBuffer = Buffer.concat(buffers);
      const filePath = `reports/${req.user.id}/${analysis.id}.pdf`;
      await uploadToStorage(filePath, pdfBuffer, 'application/pdf');

      await query(
        `INSERT INTO generated_reports (analysis_id, format, file_path, file_size_bytes, expires_at)
         VALUES ($1, 'pdf', $2, $3, now() + interval '7 days') RETURNING id`,
        [analysis.id, filePath, pdfBuffer.length]
      );

      res.setHeader('Content-Type', 'application/pdf');
      res.setHeader('Content-Disposition', `attachment; filename="biap-report-${analysis.id}.pdf"`);
      res.send(pdfBuffer);
    });

    // محتوای PDF — توجه: برای فارسی نیاز به فونت Vazirmatn یا مشابه دارد
    doc.font('Helvetica-Bold').fontSize(16).text(`گزارش تحلیل: ${analysis.project_name}`, { align: 'right' });
    doc.moveDown();
    doc.font('Helvetica').fontSize(11).text(analysis.ai_response, { align: 'right' });
    doc.end();
  } catch (err) {
    next(err);
  }
});

// ── تولید خروجی Excel از یک تحلیل ──
router.post('/excel/:analysisId', requireAuth, async (req, res, next) => {
  try {
    const { rows } = await query(
      `SELECT al.*, p.name as project_name FROM analysis_logs al
       JOIN projects p ON p.id = al.project_id
       WHERE al.id = $1 AND p.user_id = $2`,
      [req.params.analysisId, req.user.id]
    );
    if (!rows.length) return res.status(404).json({ error: 'تحلیل یافت نشد' });

    const analysis = rows[0];
    const workbook = new ExcelJS.Workbook();
    const sheet = workbook.addWorksheet('تحلیل', { views: [{ rightToLeft: true }] });

    sheet.columns = [{ header: 'بخش تحلیل', key: 'content', width: 100 }];
    analysis.ai_response.split('\n').forEach((line) => {
      sheet.addRow({ content: line });
    });

    sheet.getRow(1).font = { bold: true };

    const buffer = await workbook.xlsx.writeBuffer();
    const filePath = `reports/${req.user.id}/${analysis.id}.xlsx`;
    await uploadToStorage(filePath, buffer, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');

    await query(
      `INSERT INTO generated_reports (analysis_id, format, file_path, file_size_bytes, expires_at)
       VALUES ($1, 'xlsx', $2, $3, now() + interval '7 days')`,
      [analysis.id, filePath, buffer.length]
    );

    res.setHeader('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
    res.setHeader('Content-Disposition', `attachment; filename="biap-report-${analysis.id}.xlsx"`);
    res.send(buffer);
  } catch (err) {
    next(err);
  }
});

module.exports = router;
