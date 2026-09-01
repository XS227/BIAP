-- ════════════════════════════════════════════════════
-- Migration 001 — شمارنده «۵ درخواست رایگان دائمی» برای فراخوانی AI
--
-- هر کاربر (بر اساس user_id یا در نبود احراز هویت، IP) مجموعاً فقط
-- ۵ درخواست رایگان دائمی دارد که از کلاینت مشترک (پراکسی) استفاده می‌کند.
-- درخواست‌هایی که با «کلید API شخصی کاربر» انجام می‌شوند در این شمارنده
-- محاسبه نمی‌شوند و محدودیتی ندارند.
--
-- این شمارنده دائمی است (بازنشانی روزانه ندارد) و با هر پاسخ موفقِ
-- کلاینت مشترک یک واحد افزایش می‌یابد.
-- ════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS ai_free_usage (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        UUID UNIQUE REFERENCES users(id) ON DELETE CASCADE, -- NULL اگر کاربر لاگین نکرده باشد
    ip_address     VARCHAR(45) UNIQUE,                                 -- کلید جایگزین وقتی user_id نداریم
    request_count  INTEGER NOT NULL DEFAULT 0,                         -- تعداد درخواست‌های رایگان مصرف‌شده
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- یا user_id یا ip_address باید مقدار داشته باشد (هویت شمارنده)
    CONSTRAINT ai_free_usage_identity_chk CHECK (user_id IS NOT NULL OR ip_address IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_ai_free_usage_user ON ai_free_usage(user_id);
CREATE INDEX IF NOT EXISTS idx_ai_free_usage_ip   ON ai_free_usage(ip_address);
