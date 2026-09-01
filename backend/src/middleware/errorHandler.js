const logger = require('../config/logger');

function errorHandler(err, req, res, next) {
  logger.error(`خطا در ${req.method} ${req.path}: ${err.message}`, { stack: err.stack });

  const status = err.statusCode || 500;
  const message = status === 500
    ? 'خطای داخلی سرور رخ داد. لطفاً دوباره تلاش کنید.'
    : err.message;

  res.status(status).json({ error: message });
}

module.exports = { errorHandler };
