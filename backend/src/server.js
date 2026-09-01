/**
 * BIAP Backend — نقطه ورود اصلی سرور
 *
 * این فایل سرور Express را راه‌اندازی می‌کند که:
 *  - کلید API هوش مصنوعی را امن نگه می‌دارد (هرگز به کلاینت ارسال نمی‌شود)
 *  - OAuth برای Google Analytics / Google Ads را مدیریت می‌کند
 *  - داده کاربران، پروژه‌ها و تاریخچه تحلیل را در PostgreSQL ذخیره می‌کند
 */

require('dotenv').config();
const express = require('express');
const helmet = require('helmet');
const cors = require('cors');
const rateLimit = require('express-rate-limit');
const cookieParser = require('cookie-parser');

const authRoutes = require('./routes/auth.routes');
const projectRoutes = require('./routes/projects.routes');
const analysisRoutes = require('./routes/analysis.routes');
const integrationRoutes = require('./routes/integrations.routes');
const googleOAuthRoutes = require('./routes/google-oauth.routes');
const reportRoutes = require('./routes/reports.routes');
const stockRoutes = require('./routes/stock.routes');
const { errorHandler } = require('./middleware/errorHandler');
const logger = require('./config/logger');

const app = express();
const PORT = process.env.PORT || 4000;

// ── امنیت پایه ──
app.use(helmet());
app.use(cors({
  origin: process.env.ALLOWED_ORIGINS?.split(',') || ['http://localhost:3000'],
  credentials: true,
}));
app.use(express.json({ limit: '2mb' }));
app.use(cookieParser());

// ── محدودیت نرخ درخواست (جلوگیری از سوءاستفاده از API هوش مصنوعی) ──
const aiLimiter = rateLimit({
  windowMs: 60 * 1000,        // ۱ دقیقه
  max: 15,                    // حداکثر ۱۵ درخواست تحلیل در دقیقه برای هر کاربر
  message: { error: 'تعداد درخواست‌های شما بیش از حد مجاز است. کمی صبر کنید.' },
  keyGenerator: (req) => req.user?.id || req.ip,
});

const generalLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,   // ۱۵ دقیقه
  max: 300,
});
app.use(generalLimiter);

// ── مسیرهای API ──
app.use('/api/auth', authRoutes);
app.use('/api/projects', projectRoutes);
app.use('/api/analysis', aiLimiter, analysisRoutes);
app.use('/api/integrations', integrationRoutes);
app.use('/api/oauth/google', googleOAuthRoutes);
app.use('/api/reports', reportRoutes);
app.use('/api/stock', stockRoutes);

app.get('/health', (req, res) => res.json({ status: 'ok', time: new Date().toISOString() }));

app.use(errorHandler);

app.listen(PORT, () => {
  logger.info(`BIAP Backend در پورت ${PORT} اجرا شد`);
});

module.exports = app;
