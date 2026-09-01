# فرانت‌اند — فیلد اختیاری «کلید API آنتروپیک شما»

فرانت‌اند BIAP یک artifact React جداست و در این ریپو نگهداری نمی‌شود. این snippet
آماده‌ی paste در آن artifact است. کاری که می‌کند:

1. یک فیلد اختیاری «کلید API آنتروپیک شما (اختیاری)» نمایش می‌دهد.
2. مقدار را در `localStorage` ذخیره می‌کند (بین جلسات باقی می‌ماند).
3. هنگام فراخوانی `/api/analysis/run`، اگر کلیدی وارد شده باشد آن را در بدنه‌ی
   درخواست به‌صورت `userApiKey` می‌فرستد.
4. اگر بک‌اند خطای `FREE_LIMIT_EXCEEDED` (۴۲۹) برگرداند، پیام فارسی را نشان می‌دهد.

> امنیت: کلید فقط در مرورگر خود کاربر (localStorage) و در بدنه‌ی درخواست به سرور
> شماست. بک‌اند این کلید را **هرگز لاگ یا ذخیره نمی‌کند**.

---

## کامپوننت فیلد کلید

```jsx
import { useState } from 'react';

const API_KEY_STORAGE = 'biap_anthropic_api_key';

// خواندن کلید ذخیره‌شده (در هر جای اپ قابل استفاده)
export function getUserApiKey() {
  return localStorage.getItem(API_KEY_STORAGE) || '';
}

export function ApiKeyField() {
  const [apiKey, setApiKey] = useState(getUserApiKey());

  const handleChange = (e) => {
    const value = e.target.value;
    setApiKey(value);
    if (value.trim()) {
      localStorage.setItem(API_KEY_STORAGE, value.trim());
    } else {
      localStorage.removeItem(API_KEY_STORAGE);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, direction: 'rtl' }}>
      <label htmlFor="anthropic-key" style={{ fontWeight: 600 }}>
        کلید API آنتروپیک شما (اختیاری)
      </label>
      <input
        id="anthropic-key"
        type="password"
        autoComplete="off"
        placeholder="sk-ant-..."
        value={apiKey}
        onChange={handleChange}
        style={{ padding: 8, borderRadius: 8, border: '1px solid #ccc' }}
      />
      <small style={{ color: '#666' }}>
        این کلید فقط در مرورگر شما ذخیره می‌شود و روی سرور ما لاگ یا ذخیره نمی‌شود.
        با وارد کردن کلید شخصی، محدودیت ۵ درخواست رایگان برداشته می‌شود.
      </small>
    </div>
  );
}
```

---

## ارسال کلید هنگام فراخوانی تحلیل

```jsx
import { getUserApiKey } from './ApiKeyField';

async function runAnalysis({ accessToken, projectId, moduleId, tab, prompt, data }) {
  const userApiKey = getUserApiKey(); // '' اگر کاربر کلیدی وارد نکرده باشد

  const res = await fetch('/api/analysis/run', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({
      projectId,
      moduleId,
      tab,
      prompt,
      data,
      ...(userApiKey ? { userApiKey } : {}), // فقط در صورت وجود ارسال می‌شود
    }),
  });

  const payload = await res.json();

  if (res.status === 429 && payload.code === 'FREE_LIMIT_EXCEEDED') {
    // نمایش پیام فارسی و هدایت کاربر به وارد کردن کلید شخصی در تنظیمات
    alert(payload.error);
    return null;
  }

  if (!res.ok) {
    throw new Error(payload.error || 'خطا در تحلیل');
  }

  // payload.usage.ownKey === true  یعنی از کلید شخصی استفاده شد (بدون محدودیت)
  // payload.usage = { used, limit }  برای درخواست‌های رایگان
  return payload;
}
```
