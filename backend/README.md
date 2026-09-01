# BIAP Backend

این پروژه **معماری Backend واقعی** برای سامانه BIAP است که سه نیاز اصلی را رفع می‌کند:

1. **کلید API امن** — در نسخه فعلی artifact (مرورگری)، کلید API هوش مصنوعی مستقیماً در کد فرانت‌اند است و هر کاربر می‌تواند آن را در DevTools مرورگر ببیند. این Backend کلید را فقط روی سرور نگه می‌دارد.
2. **اتصال واقعی به Google Analytics / Google Ads** — با OAuth 2.0 واقعی (نه شبیه‌سازی).
3. **حساب کاربری و ذخیره داده** — پروژه‌ها، تاریخچه تحلیل‌ها و داده‌ها بین جلسات مختلف باقی می‌مانند.

---

## ⚠️ این یک پروژه جداست، نه بخشی از artifact چت

این کدها **داخل Claude.ai اجرا نمی‌شوند**. باید آن‌ها را روی یک سرور واقعی (مثل یک VPS ایرانی، Arvan Cloud، یا مشابه) دیپلوی کنید. فرانت‌اند فعلی (artifact React) باید برای استفاده از این Backend ویرایش شود تا به‌جای فراخوانی مستقیم API هوش مصنوعی، به آدرس این سرور (`/api/analysis/run`) درخواست بزند.

---

## ساختار پروژه

```
biap-backend/
├── src/
│   ├── server.js              ← نقطه ورود اصلی
│   ├── config/
│   │   ├── db.js              ← اتصال PostgreSQL
│   │   └── logger.js          ← لاگ مرکزی
│   ├── middleware/
│   │   ├── auth.middleware.js ← بررسی JWT و پلن کاربر
│   │   └── errorHandler.js
│   ├── routes/
│   │   ├── auth.routes.js          ← ثبت‌نام، ورود، OTP
│   │   ├── projects.routes.js      ← مدیریت پروژه‌ها
│   │   ├── analysis.routes.js      ← فراخوانی امن AI (رفع نشت کلید)
│   │   ├── google-oauth.routes.js  ← اتصال واقعی Google Analytics/Ads
│   │   ├── integrations.routes.js  ← لیست اتصال‌ها
│   │   └── reports.routes.js       ← تولید PDF/Excel
│   └── services/
│       ├── crypto.service.js  ← رمزنگاری توکن‌های OAuth
│       ├── sms.service.js     ← ارسال OTP
│       └── storage.service.js ← ذخیره فایل گزارش‌ها
└── docs/
    └── schema.sql             ← ساختار کامل دیتابیس
```

---

## راه‌اندازی محلی (برای تست)

### پیش‌نیازها
- Node.js نسخه ۱۸ یا بالاتر
- PostgreSQL نسخه ۱۴ یا بالاتر
- یک حساب Google Cloud Console (برای OAuth)

### مراحل

```bash
# ۱. نصب وابستگی‌ها
cd biap-backend
npm install

# ۲. ساخت دیتابیس
createdb biap_db

# ۳. اجرای schema
npm run migrate

# ۴. تنظیم متغیرهای محیطی
cp .env.example .env
# سپس .env را با مقادیر واقعی خود پر کنید (راهنما در بخش بعد)

# ۵. اجرای سرور در حالت توسعه
npm run dev
```

سرور روی `http://localhost:4000` بالا می‌آید. تست سلامت:
```bash
curl http://localhost:4000/health
```

---

## تنظیم Google OAuth (برای اتصال Analytics/Ads)

این بخش دقیقاً نیازی که در چت مطرح شد را رفع می‌کند.

1. به [Google Cloud Console](https://console.cloud.google.com/) بروید
2. یک پروژه جدید بسازید
3. در «APIs & Services» → «Library»، این API‌ها را فعال کنید:
   - Google Analytics Data API
   - Google Analytics Admin API
   - Google Ads API (در صورت نیاز)
4. در «Credentials» → «Create Credentials» → «OAuth client ID»:
   - Application type: **Web application**
   - Authorized redirect URI: `http://localhost:4000/api/oauth/google/callback` (برای تست) یا آدرس واقعی سرور شما
5. `Client ID` و `Client Secret` را در `.env` قرار دهید

### جریان اتصال از فرانت‌اند

```javascript
// ۱. کاربر دکمه «اتصال Google Analytics» را می‌زند
const res = await fetch('/api/oauth/google/connect/analytics?projectId=xxx', {
  headers: { Authorization: `Bearer ${accessToken}` }
});
const { authUrl } = await res.json();
window.location.href = authUrl; // کاربر به صفحه گوگل می‌رود

// ۲. بعد از تایید، گوگل کاربر را به callback ما برمی‌گرداند
// ۳. سرور خودکار توکن را ذخیره می‌کند و کاربر را به صفحه integrations برمی‌گرداند

// ۴. همگام‌سازی داده واقعی
await fetch(`/api/oauth/google/sync/analytics/${integrationId}`, {
  method: 'POST',
  headers: { Authorization: `Bearer ${accessToken}` }
});
```

---

## این Backend دقیقاً کدام مراحل MVP را رفع می‌کند؟

| مرحله از برنامه قبلی | وضعیت در این پکیج |
|---|---|
| ۱. Backend | ✅ کامل — سرور Express با همه مسیرهای لازم |
| ۲. حساب کاربری | ✅ کامل — ثبت‌نام، ورود، OTP، JWT |
| ۳. گزارش حرفه‌ای (PDF/Excel) | ✅ پایه پیاده‌سازی شده — نیاز به افزودن فونت فارسی برای PDF |
| ۴. داده واقعی (Analytics/Ads) | ✅ کامل — OAuth واقعی + همگام‌سازی |
| ۵. نسخه تجاری (قیمت‌گذاری) | ⚠️ ساختار دیتابیس آمده (`subscriptions`) اما درگاه پرداخت متصل نیست |
| ۶. پایلوت | ❌ این بخش اجرایی است، نه کدنویسی — نیاز به تست با کاربر واقعی |

---

## نکات امنیتی مهم پیش از Production

1. **هرگز `.env` را در Git commit نکنید** — به `.gitignore` اضافه کنید
2. کلیدهای `JWT_SECRET` و `TOKEN_ENCRYPTION_KEY` را با دستور زیر بسازید:
   ```bash
   node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
   ```
3. حتماً HTTPS فعال کنید (Let's Encrypt رایگان است) — کوکی‌های `secure: true` بدون HTTPS کار نمی‌کنند
4. قبل از انتشار، یک امنیت‌سنج (Security Audit) ساده با `npm audit` اجرا کنید
5. برای ذخیره فایل (گزارش‌ها)، از یک سرویس داخل ایران (مثل Arvan Cloud Object Storage) استفاده کنید تا با تحریم مشکل نداشته باشید

---

## مرحله بعدی پیشنهادی

این Backend به‌تنهایی کاربردی نیست — باید:
1. فرانت‌اند artifact فعلی را ویرایش کنید تا به‌جای فراخوانی مستقیم AI، به `/api/analysis/run` درخواست بزند
2. صفحه ورود/ثبت‌نام به رابط کاربری اضافه شود
3. این سرور روی یک هاست واقعی (پیشنهاد: Arvan Cloud یا Liara برای میزبانی داخل ایران) دیپلوی شود

اگر می‌خواهید، در گام بعدی می‌توانم فرانت‌اند artifact را ویرایش کنم تا با این API‌ها صحبت کند.
