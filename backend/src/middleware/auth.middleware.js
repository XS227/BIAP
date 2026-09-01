/**
 * Middleware احراز هویت — بررسی JWT و اتصال کاربر به req.user
 */
const jwt = require('jsonwebtoken');
const { query } = require('../config/db');

async function requireAuth(req, res, next) {
  try {
    const authHeader = req.headers.authorization;
    const token = authHeader?.startsWith('Bearer ') ? authHeader.slice(7) : req.cookies?.access_token;

    if (!token) {
      return res.status(401).json({ error: 'برای استفاده از این بخش باید وارد حساب کاربری شوید' });
    }

    const payload = jwt.verify(token, process.env.JWT_SECRET);

    const { rows } = await query('SELECT id, email, plan, is_active FROM users WHERE id = $1', [payload.userId]);
    if (!rows.length || !rows[0].is_active) {
      return res.status(401).json({ error: 'حساب کاربری یافت نشد یا غیرفعال است' });
    }

    req.user = rows[0];
    next();
  } catch (err) {
    if (err.name === 'TokenExpiredError') {
      return res.status(401).json({ error: 'نشست شما منقضی شده. دوباره وارد شوید', code: 'TOKEN_EXPIRED' });
    }
    return res.status(401).json({ error: 'توکن نامعتبر است' });
  }
}

/** بررسی محدودیت پلن — مثلاً داده زنده فقط برای پلن حرفه‌ای/سازمانی */
function requirePlan(...allowedPlans) {
  return (req, res, next) => {
    if (!allowedPlans.includes(req.user.plan)) {
      return res.status(403).json({
        error: `این قابلیت فقط برای پلن‌های ${allowedPlans.join('، ')} در دسترس است`,
        code: 'PLAN_UPGRADE_REQUIRED',
      });
    }
    next();
  };
}

module.exports = { requireAuth, requirePlan };
