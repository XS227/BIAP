/**
 * مسیر تحلیل AI — رفع آسیب‌پذیری کلید API افشاشده در نسخه مرورگری
 *
 * در نسخه فعلی artifact، فراخوانی مستقیم از مرورگر به API انجام می‌شود
 * که یعنی کلید API در DevTools مرورگر هر کاربر قابل مشاهده است.
 * این فایل آن فراخوانی را به سرور منتقل می‌کند — کلید فقط روی سرور می‌ماند.
 */
const express = require('express');
const Anthropic = require('@anthropic-ai/sdk');
const { requireAuth } = require('../middleware/auth.middleware');
const { query } = require('../config/db');
const logger = require('../config/logger');

const router = express.Router();

// کلاینت مشترک — از پراکسی داخلی استفاده می‌کند و مشمول محدودیت رایگان است.
// فقط روی سرور ساخته می‌شود؛ کلید آن هرگز به کلاینت ارسال نمی‌شود.
const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY, baseURL: 'http://5.249.252.221:4433' });

// محدودیت مصرف روزانه بر اساس پلن (جلوگیری از هزینه کنترل‌نشده API روی کلاینت مشترک)
const DAILY_LIMITS = { free: 10, pro: 200, enterprise: 2000 };

// سقف «درخواست‌های رایگان دائمی» برای هر کاربر/IP روی کلاینت مشترک
const FREE_REQUEST_LIMIT = 5;

// ایمیل‌هایی که برای همیشه از سقف «۵ درخواست رایگان» معاف‌اند.
// بررسی ai_free_usage برای این‌ها همیشه رد می‌شود — بدون تغییر دستی رکورد دیتابیس.
const FREE_LIMIT_EXEMPT_EMAILS = new Set(['nasrin@biap.ir', 'dadashi.nasrin07@gmail.com']);

// پیام هنگام اتمام سهمیه رایگان دائمی
const FREE_LIMIT_MESSAGE =
  'شما از ۵ درخواست رایگان خود استفاده کرده‌اید. برای ادامه، کلید API شخصی خودتون رو در تنظیمات وارد کنید.';

/**
 * هویت شمارنده رایگان را برمی‌گرداند: در صورت وجود کاربر، user_id؛
 * در غیر این صورت IP. کلید API کاربر هرگز اینجا دخیل نیست.
 */
function usageIdentity(req) {
  if (req.user?.id) return { column: 'user_id', value: req.user.id };
  return { column: 'ip_address', value: req.ip };
}

/** تعداد درخواست‌های رایگان مصرف‌شده تا این لحظه را می‌خواند (۰ اگر رکوردی نباشد). */
async function getFreeUsage(identity) {
  const { rows } = await query(
    `SELECT request_count FROM ai_free_usage WHERE ${identity.column} = $1`,
    [identity.value]
  );
  return rows.length ? rows[0].request_count : 0;
}

/** شمارنده رایگان را یک واحد افزایش می‌دهد (upsert بر اساس user_id یا ip_address). */
async function incrementFreeUsage(identity) {
  await query(
    `INSERT INTO ai_free_usage (${identity.column}, request_count)
       VALUES ($1, 1)
     ON CONFLICT (${identity.column})
       DO UPDATE SET request_count = ai_free_usage.request_count + 1,
                     updated_at = now()`,
    [identity.value]
  );
}

router.post('/run', requireAuth, async (req, res, next) => {
  const start = Date.now();
  try {
    // userApiKey جداگانه استخراج می‌شود تا هرگز وارد لاگ/DB نشود.
    const { projectId, datasetId, moduleId, tab, prompt, data, userApiKey } = req.body;
    if (!prompt || !data) {
      return res.status(400).json({ error: 'prompt و data الزامی هستند' });
    }

    // آیا کاربر کلید API شخصی خودش را داده است؟ (فقط رشته غیرخالی معتبر است)
    const trimmedUserKey = typeof userApiKey === 'string' ? userApiKey.trim() : '';
    const usingOwnKey = trimmedUserKey.length > 0;

    // انتخاب کلاینت:
    //  - کلید شخصی کاربر  → کلاینت مستقیم، بدون baseURL، بدون هیچ محدودیت.
    //  - بدون کلید        → کلاینت مشترک (پراکسی) + اعمال محدودیت‌ها.
    const client = usingOwnKey ? new Anthropic({ apiKey: trimmedUserKey }) : anthropic;

    let freeUsed = null;
    const identity = usageIdentity(req);

    if (!usingOwnKey) {
      // ── سقف «۵ درخواست رایگان دائمی» (فقط برای کلاینت مشترک) ──
      // کاربران معاف: بررسی محدودیت برایشان همیشه رد می‌شود، هر تعداد استفاده‌شان باشد.
      const exemptFromFreeLimit = FREE_LIMIT_EXEMPT_EMAILS.has((req.user?.email || '').toLowerCase());
      freeUsed = await getFreeUsage(identity);
      if (!exemptFromFreeLimit && freeUsed >= FREE_REQUEST_LIMIT) {
        return res.status(429).json({
          error: FREE_LIMIT_MESSAGE,
          code: 'FREE_LIMIT_EXCEEDED',
          usage: { used: freeUsed, limit: FREE_REQUEST_LIMIT },
        });
      }

      // ── محدودیت مصرف روزانه بر اساس پلن (لایه دوم، فقط کلاینت مشترک) ──
      const usageToday = await query(
        `SELECT COUNT(*) FROM analysis_logs al
         JOIN projects p ON p.id = al.project_id
         WHERE p.user_id = $1 AND al.created_at > now() - interval '24 hours'`,
        [req.user.id]
      );
      const used = parseInt(usageToday.rows[0].count, 10);
      const limit = DAILY_LIMITS[req.user.plan] || DAILY_LIMITS.free;
      if (used >= limit) {
        return res.status(429).json({
          error: `سهمیه روزانه شما (${limit} تحلیل) به پایان رسیده. فردا دوباره تلاش کنید یا پلن خود را ارتقا دهید`,
          code: 'DAILY_LIMIT_EXCEEDED',
        });
      }
    }

    // ── اعتبارسنجی مالکیت پروژه ──
    if (projectId) {
      const proj = await query('SELECT id FROM projects WHERE id = $1 AND user_id = $2', [projectId, req.user.id]);
      if (!proj.rows.length) return res.status(403).json({ error: 'دسترسی به این پروژه ندارید' });
    }

    const fullPrompt = `${prompt}\n\nداده‌ها:\n${data}\n\nپاسخ را به فارسی، ساختارمند و کاربردی بنویس. از عناوین و emoji برای خوانایی استفاده کن.`;

    const message = await client.messages.create({
      model: 'claude-haiku-4-5-20251001',
      max_tokens: 1000,
      messages: [{ role: 'user', content: fullPrompt }],
    });

    const responseText = message.content.map((c) => c.text || '').join('');
    const latency = Date.now() - start;

    // ── ثبت لاگ کامل برای رفع نیاز «مرحله ۷: ثبت لاگ تحلیل‌ها» ──
    const logResult = await query(
      `INSERT INTO analysis_logs
        (project_id, dataset_id, module_id, tab, prompt_used, ai_response, tokens_used, latency_ms, status)
       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'success')
       RETURNING id`,
      [projectId, datasetId, moduleId, tab, fullPrompt, responseText, message.usage?.output_tokens, latency]
    );

    // شمارنده رایگان فقط وقتی کلاینت مشترک استفاده شده باشد افزایش می‌یابد.
    let usage = { ownKey: true };
    if (!usingOwnKey) {
      await incrementFreeUsage(identity);
      usage = { used: freeUsed + 1, limit: FREE_REQUEST_LIMIT, ownKey: false };
    }

    res.json({
      analysisId: logResult.rows[0].id,
      result: responseText,
      usage,
    });
  } catch (err) {
    const latency = Date.now() - start;
    logger.error('خطا در فراخوانی AI:', err);

    await query(
      `INSERT INTO analysis_logs (project_id, module_id, tab, prompt_used, ai_response, latency_ms, status, error_message)
       VALUES ($1, $2, $3, $4, '', $5, 'error', $6)`,
      [req.body.projectId, req.body.moduleId, req.body.tab, req.body.prompt || '', latency, err.message]
    ).catch(() => {}); // لاگ خطا نباید خودش خطای دیگری بسازد

    res.status(502).json({ error: 'خطا در ارتباط با سرویس هوش مصنوعی. لطفاً دوباره تلاش کنید' });
  }
});

// ── تاریخچه تحلیل‌های یک پروژه ──
router.get('/history/:projectId', requireAuth, async (req, res, next) => {
  try {
    const proj = await query('SELECT id FROM projects WHERE id = $1 AND user_id = $2', [req.params.projectId, req.user.id]);
    if (!proj.rows.length) return res.status(403).json({ error: 'دسترسی ندارید' });

    const { rows } = await query(
      `SELECT id, module_id, tab, ai_response, status, created_at
       FROM analysis_logs WHERE project_id = $1 ORDER BY created_at DESC LIMIT 50`,
      [req.params.projectId]
    );
    res.json({ history: rows });
  } catch (err) {
    next(err);
  }
});

module.exports = router;
