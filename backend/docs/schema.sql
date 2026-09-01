-- ════════════════════════════════════════════════════
-- BIAP Backend — PostgreSQL Schema
-- معماری پایه برای: حساب کاربری، اتصال‌های واقعی (Google
-- Analytics/Ads)، ذخیره پروژه‌ها، تاریخچه تحلیل‌ها
-- ════════════════════════════════════════════════════

-- ───────── کاربران ─────────
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           VARCHAR(255) UNIQUE NOT NULL,
    phone           VARCHAR(20) UNIQUE,
    password_hash   VARCHAR(255),              -- NULL اگر فقط OTP/OAuth استفاده می‌کند
    full_name       VARCHAR(255),
    company_name    VARCHAR(255),
    plan            VARCHAR(20) NOT NULL DEFAULT 'free',  -- free | pro | enterprise
    plan_expires_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login_at   TIMESTAMPTZ,
    is_active       BOOLEAN NOT NULL DEFAULT true
);

-- ───────── نشست‌های ورود (برای OTP/JWT refresh) ─────────
CREATE TABLE auth_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    refresh_token   VARCHAR(512) NOT NULL,
    user_agent      VARCHAR(255),
    ip_address      VARCHAR(45),
    expires_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_auth_sessions_user ON auth_sessions(user_id);

-- ───────── کدهای OTP (ورود با موبایل) ─────────
CREATE TABLE otp_codes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone           VARCHAR(20) NOT NULL,
    code_hash       VARCHAR(255) NOT NULL,
    purpose         VARCHAR(20) NOT NULL,       -- login | signup | reset
    expires_at      TIMESTAMPTZ NOT NULL,
    consumed_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_otp_phone ON otp_codes(phone, purpose);

-- ───────── پروژه‌ها (هر کاربر چند پروژه/شرکت دارد) ─────────
CREATE TABLE projects (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,
    tab             VARCHAR(20) NOT NULL,       -- stock | bizdev | data
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_projects_user ON projects(user_id);

-- ───────── داده ورودی هر پروژه (نسخه‌دار، برای تاریخچه) ─────────
CREATE TABLE project_datasets (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    source_type     VARCHAR(20) NOT NULL,       -- manual | csv_upload | live_api | ga_sync | gads_sync
    source_label    VARCHAR(255),               -- نام فایل یا شناسه اتصال
    raw_data        TEXT NOT NULL,              -- CSV یا JSON خام
    row_count       INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_datasets_project ON project_datasets(project_id);

-- ───────── تاریخچه تحلیل‌های AI (لاگ کامل) ─────────
CREATE TABLE analysis_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    dataset_id      UUID REFERENCES project_datasets(id),
    module_id       VARCHAR(50) NOT NULL,       -- kpi_dash | competitor_swot | ...
    tab             VARCHAR(20) NOT NULL,
    prompt_used     TEXT NOT NULL,
    ai_response     TEXT NOT NULL,
    tokens_used     INTEGER,
    latency_ms      INTEGER,
    status          VARCHAR(20) NOT NULL DEFAULT 'success',  -- success | error | timeout
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_analysis_project ON analysis_logs(project_id);
CREATE INDEX idx_analysis_created ON analysis_logs(created_at);

-- ───────── اتصال‌های خارجی (Google Analytics, Google Ads, ...) ─────────
-- هسته اصلی برای رفع نیاز «اتصال واقعی Analytics»
CREATE TABLE external_integrations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id          UUID REFERENCES projects(id) ON DELETE CASCADE,
    provider            VARCHAR(50) NOT NULL,   -- google_analytics | google_ads | tsetmc | crm_csv
    provider_account_id VARCHAR(255),           -- مثلاً GA Property ID یا Google Ads Customer ID
    access_token_enc    TEXT,                   -- رمزنگاری‌شده (AES-256) — هرگز خام ذخیره نمی‌شود
    refresh_token_enc   TEXT,                   -- رمزنگاری‌شده
    token_expires_at    TIMESTAMPTZ,
    scopes              TEXT,                   -- فضای دسترسی اعطاشده توسط کاربر
    status               VARCHAR(20) NOT NULL DEFAULT 'connected', -- connected | expired | revoked | error
    last_synced_at       TIMESTAMPTZ,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, provider, provider_account_id)
);
CREATE INDEX idx_integrations_user ON external_integrations(user_id);
CREATE INDEX idx_integrations_project ON external_integrations(project_id);

-- ───────── داده sync شده از اتصال‌های خارجی (نتیجه واقعی API) ─────────
CREATE TABLE integration_sync_data (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    integration_id  UUID NOT NULL REFERENCES external_integrations(id) ON DELETE CASCADE,
    metric_date     DATE NOT NULL,
    metrics_json    JSONB NOT NULL,             -- مثلاً {"sessions":1200,"conversion_rate":1.8,"bounce_rate":42}
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(integration_id, metric_date)
);
CREATE INDEX idx_sync_integration ON integration_sync_data(integration_id);
CREATE INDEX idx_sync_metrics_gin ON integration_sync_data USING GIN (metrics_json);

-- ───────── اشتراک/پرداخت (برای پلن‌های پولی) ─────────
CREATE TABLE subscriptions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan            VARCHAR(20) NOT NULL,
    amount_toman    BIGINT NOT NULL,
    payment_gateway VARCHAR(50),                -- zarinpal | idpay | ...
    gateway_ref_id  VARCHAR(255),
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending | paid | failed | refunded
    starts_at       TIMESTAMPTZ,
    ends_at         TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_subscriptions_user ON subscriptions(user_id);

-- ───────── شمارنده «۵ درخواست رایگان دائمی» برای فراخوانی AI ─────────
-- هر کاربر (بر اساس user_id یا IP) مجموعاً فقط ۵ درخواست رایگان دائمی دارد
-- که از کلاینت مشترک (پراکسی) استفاده می‌کند. درخواست‌هایی که با کلید API
-- شخصی خود کاربر انجام می‌شوند در این شمارنده محاسبه نمی‌شوند و محدودیتی ندارند.
CREATE TABLE ai_free_usage (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID UNIQUE REFERENCES users(id) ON DELETE CASCADE, -- NULL اگر کاربر لاگین نکرده باشد
    ip_address     VARCHAR(45) UNIQUE,                                 -- کلید جایگزین وقتی user_id نداریم
    request_count  INTEGER NOT NULL DEFAULT 0,                         -- تعداد درخواست‌های رایگان مصرف‌شده
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ai_free_usage_identity_chk CHECK (user_id IS NOT NULL OR ip_address IS NOT NULL)
);
CREATE INDEX idx_ai_free_usage_user ON ai_free_usage(user_id);
CREATE INDEX idx_ai_free_usage_ip   ON ai_free_usage(ip_address);

-- ───────── گزارش‌های تولیدشده (PDF/Excel) ─────────
CREATE TABLE generated_reports (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id     UUID NOT NULL REFERENCES analysis_logs(id) ON DELETE CASCADE,
    format          VARCHAR(10) NOT NULL,       -- pdf | xlsx | docx
    file_path       VARCHAR(500) NOT NULL,      -- مسیر در S3/MinIO
    file_size_bytes INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ                 -- لینک‌های دانلود موقت
);
