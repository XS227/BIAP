/**
 * اتصال به PostgreSQL با connection pool
 */
const { Pool } = require('pg');
const logger = require('./logger');

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  max: 20,
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 5000,
});

pool.on('error', (err) => {
  logger.error('خطای غیرمنتظره در connection pool دیتابیس:', err);
});

async function query(text, params) {
  const start = Date.now();
  const res = await pool.query(text, params);
  const duration = Date.now() - start;
  if (duration > 200) {
    logger.warn(`Query کند (${duration}ms): ${text.slice(0, 80)}`);
  }
  return res;
}

module.exports = { pool, query };
