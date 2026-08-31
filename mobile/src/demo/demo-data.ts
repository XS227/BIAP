export type DemoMetric = {
  label: string;
  value: string;
  delta?: string;
  tone?: 'positive' | 'negative' | 'neutral';
};

export type DemoModule = {
  key: string;
  title: string;
  icon: string;
  summary: string;
  metrics: DemoMetric[];
  bullets: string[];
};

export const DEMO_MODULES: Record<string, DemoModule> = {
  eda: {
    key: 'eda', title: 'EDA Explorer', icon: '🔬',
    summary: 'تحلیل اکتشافی نمونه برای یک کسب‌وکار خدماتی؛ داده‌ها صرفاً نمایشی هستند.',
    metrics: [
      { label: 'رکوردها', value: '1,248', tone: 'neutral' },
      { label: 'میانگین فروش', value: '۳۸.۴M', delta: '+8.7٪', tone: 'positive' },
      { label: 'Outlier', value: '17', tone: 'negative' },
    ],
    bullets: ['رشد فروش در ۳ ماه اخیر', 'همبستگی مثبت بازدید سایت و فروش', '۱۷ رکورد خارج از الگوی معمول'],
  },
  sql: {
    key: 'sql', title: 'SQL Query', icon: '🗄️',
    summary: 'نمونه خروجی یک Query تحلیلی روی داده فروش و مشتری.',
    metrics: [
      { label: 'ردیف نتیجه', value: '42' },
      { label: 'زمان اجرا', value: '84ms' },
      { label: 'منابع', value: '3 جدول' },
    ],
    bullets: ['Top 10 مشتری بر اساس LTV', 'فروش ماهانه به تفکیک کانال', 'مقایسه نرخ تبدیل با ماه قبل'],
  },
  anomaly: {
    key: 'anomaly', title: 'تشخیص ناهنجاری', icon: '🚨',
    summary: 'نمونه پایش خودکار رفتار غیرعادی در شاخص‌های عملیاتی.',
    metrics: [
      { label: 'هشدار باز', value: '3', tone: 'negative' },
      { label: 'شدت بالا', value: '1', tone: 'negative' },
      { label: 'پوشش', value: '96٪', tone: 'positive' },
    ],
    bullets: ['افت غیرعادی Conversion در یک کانال', 'جهش هزینه جذب مشتری', 'افزایش زمان پاسخ پشتیبانی'],
  },
  forecast: {
    key: 'forecast', title: 'پیش‌بینی آماری', icon: '📉',
    summary: 'پیش‌بینی نمونه ۹۰ روزه بر اساس روند تاریخی.',
    metrics: [
      { label: 'رشد پیش‌بینی', value: '+11.8٪', tone: 'positive' },
      { label: 'بازه اطمینان', value: '±4.2٪' },
      { label: 'افق', value: '90 روز' },
    ],
    bullets: ['سناریوی پایه: رشد ملایم', 'ریسک اصلی: افزایش CAC', 'بهترین فرصت: مشتری بازگشتی'],
  },
  'kpi-extract': {
    key: 'kpi-extract', title: 'استخراج KPI', icon: '🎯',
    summary: 'شاخص‌های کلیدی نمونه استخراج‌شده برای مرور سریع مدیریت.',
    metrics: [
      { label: 'Conversion', value: '4.8٪', delta: '+0.6٪', tone: 'positive' },
      { label: 'Churn', value: '2.1٪', delta: '-0.4٪', tone: 'positive' },
      { label: 'NPS', value: '61', delta: '+7', tone: 'positive' },
    ],
    bullets: ['Conversion بالاتر از هدف', 'Churn در محدوده سبز', 'NPS روند صعودی دارد'],
  },
  dashboard: {
    key: 'dashboard', title: 'BI Dashboard', icon: '📊',
    summary: 'نمای مدیریتی نمونه از عملکرد مالی، فروش و مشتری.',
    metrics: [
      { label: 'Revenue', value: '12.45B', delta: '+12.4٪', tone: 'positive' },
      { label: 'Gross Margin', value: '34.2٪', delta: '+2.1٪', tone: 'positive' },
      { label: 'Active Customers', value: '8,420', delta: '+9.3٪', tone: 'positive' },
    ],
    bullets: ['فروش بالاتر از بودجه', 'حاشیه سود بهبود یافته', 'رشد مشتری فعال ادامه دارد'],
  },
  governance: {
    key: 'governance', title: 'KPI Governance', icon: '📏',
    summary: 'نمونه کنترل مالکیت، هدف و وضعیت شاخص‌ها.',
    metrics: [
      { label: 'KPI فعال', value: '18' },
      { label: 'سبز', value: '13', tone: 'positive' },
      { label: 'نیاز به اقدام', value: '2', tone: 'negative' },
    ],
    bullets: ['مالک هر KPI مشخص است', 'هدف و دوره بازبینی ثبت شده', 'دو شاخص نیازمند اقدام مدیریتی'],
  },
  report: {
    key: 'report', title: 'گزارش تحلیلی', icon: '📋',
    summary: 'خلاصه نمونه قابل ارائه به مدیریت از وضعیت دوره.',
    metrics: [
      { label: 'بخش‌ها', value: '6' },
      { label: 'Insight', value: '14' },
      { label: 'Action', value: '5' },
    ],
    bullets: ['رشد فروش پایدار است', 'CAC نیازمند کنترل است', 'تمرکز بعدی روی retention پیشنهاد می‌شود'],
  },
  swot: {
    key: 'swot', title: 'SWOT + رقبا', icon: '⚔️',
    summary: 'تحلیل نمونه جایگاه رقابتی برای یک کسب‌وکار دیجیتال.',
    metrics: [
      { label: 'قوت', value: '5', tone: 'positive' },
      { label: 'ضعف', value: '3', tone: 'negative' },
      { label: 'رقیب کلیدی', value: '4' },
    ],
    bullets: ['قوت: تجربه کاربری و سرعت اجرا', 'ضعف: آگاهی برند', 'فرصت: رشد بازار آنلاین'],
  },
  journey: {
    key: 'journey', title: 'Journey Map', icon: '🗺️',
    summary: 'نقشه سفر نمونه مشتری از آگاهی تا خرید و وفاداری.',
    metrics: [
      { label: 'Touchpoint', value: '12' },
      { label: 'Pain Point', value: '4', tone: 'negative' },
      { label: 'Moment of Truth', value: '3', tone: 'positive' },
    ],
    bullets: ['اصطکاک در مرحله پرداخت', 'نیاز به onboarding کوتاه‌تر', 'پیگیری پس از خرید اثر مثبت دارد'],
  },
  crm: {
    key: 'crm', title: 'CRM + Pipeline', icon: '👥',
    summary: 'قیف فروش نمونه با فرصت‌ها و پیش‌بینی ارزش قرارداد.',
    metrics: [
      { label: 'Pipeline', value: '8.7B' },
      { label: 'Win Rate', value: '31٪', tone: 'positive' },
      { label: 'Opportunity', value: '27' },
    ],
    bullets: ['۶ فرصت در مرحله مذاکره', '۳ قرارداد نزدیک به بسته‌شدن', 'میانگین چرخه فروش ۲۶ روز'],
  },
  campaign: {
    key: 'campaign', title: 'کمپین بازاریابی', icon: '📣',
    summary: 'نمونه برنامه کمپین ۹۰ روزه با کانال، پیام و KPI.',
    metrics: [
      { label: 'Budget', value: '420M' },
      { label: 'ROAS', value: '3.4x', tone: 'positive' },
      { label: 'Lead', value: '1,960' },
    ],
    bullets: ['تمرکز روی Search + Retargeting', 'پیام اصلی: صرفه‌جویی در زمان', 'هدف: ۲۰٪ رشد Qualified Lead'],
  },
  pricing: {
    key: 'pricing', title: 'قیمت‌گذاری هوشمند', icon: '💰',
    summary: 'سناریوهای نمونه قیمت و اثر احتمالی روی درآمد و تبدیل.',
    metrics: [
      { label: 'قیمت پایه', value: '1.2M' },
      { label: 'بهینه پیشنهادی', value: '1.35M', tone: 'positive' },
      { label: 'اثر درآمد', value: '+7.6٪', tone: 'positive' },
    ],
    bullets: ['افزایش محدود قیمت در پلن Pro', 'حفظ پلن ورودی برای کاهش اصطکاک', 'A/B Test قبل از rollout کامل'],
  },
  plan: {
    key: 'plan', title: 'Business Plan', icon: '📄',
    summary: 'خلاصه نمونه طرح کسب‌وکار با بازار، مدل درآمد و milestones.',
    metrics: [
      { label: 'TAM', value: '1.8T' },
      { label: 'SOM هدف', value: '2.4٪' },
      { label: 'Runway', value: '18 ماه' },
    ],
    bullets: ['مدل درآمد اشتراکی + خدمات سازمانی', 'تمرکز ۱۲ ماهه روی بازار داخلی', 'Milestone بعدی: ۱۰ هزار کاربر فعال'],
  },
  'business-kpi': {
    key: 'business-kpi', title: 'داشبورد KPI کسب‌وکار', icon: '🎯',
    summary: 'نمونه داشبورد KPI فروش، هزینه، رشد و مشتری برای مدیریت.',
    metrics: [{ label: 'رشد ماهانه', value: '+9.4٪', tone: 'positive' },{ label: 'حاشیه', value: '28٪', tone: 'positive' },{ label: 'Conversion', value: '23٪' }],
    bullets: ['فروش بالاتر از دوره قبل', 'هزینه نیازمند کنترل', 'تمرکز بعدی روی مشتری بازگشتی'],
  },
  'market-entry': {
    key: 'market-entry', title: 'ورود به بازار جدید', icon: '🌍',
    summary: 'نمونه تحلیل ورود به یک بازار جدید با بخش‌بندی، کانال و اولویت.',
    metrics: [{ label: 'Segment', value: '4' },{ label: 'Channel', value: '3' },{ label: 'ریسک کلیدی', value: '2', tone: 'negative' }],
    bullets: ['اولویت با مشتری سازمانی متوسط', 'کانال شریک فروش + دیجیتال', 'اعتبارسنجی بازار قبل از توسعه بودجه'],
  },
  'executive-report': {
    key: 'executive-report', title: 'گزارش مدیریتی', icon: '🧾',
    summary: 'نمونه گزارش مدیریتی آماده مرور مدیر ارشد یا هیئت‌مدیره.',
    metrics: [{ label: 'KPI', value: '8' },{ label: 'انحراف', value: '3' },{ label: 'Action', value: '5' }],
    bullets: ['عملکرد فروش مثبت', 'یک انحراف هزینه‌ای مهم', 'اقدامات ماه بعد اولویت‌بندی شده‌اند'],
  },
  voc: {
    key: 'voc', title: 'VOC + Friction Points', icon: '💬',
    summary: 'نمونه تحلیل صدای مشتری و نقاط اصطکاک تجربه.',
    metrics: [{ label: 'NPS', value: '54', tone: 'positive' },{ label: 'Friction', value: '4', tone: 'negative' },{ label: 'Feedback', value: '318' }],
    bullets: ['کندی تحویل پرتکرارترین موضوع', 'اصطکاک پرداخت در رتبه دوم', 'پیگیری پس از خرید رضایت را بالا می‌برد'],
  },
  behavior: {
    key: 'behavior', title: 'رفتار کاربر', icon: '🧭',
    summary: 'نمونه Funnel رفتاری از بازدید تا خرید و بازگشت.',
    metrics: [{ label: 'Conversion', value: '4.7٪' },{ label: 'Churn', value: '2.6٪', tone: 'negative' },{ label: 'Stage', value: '5' }],
    bullets: ['بیشترین ریزش قبل از پرداخت', 'کاربران بازگشتی تبدیل بالاتری دارند', 'کاهش مراحل onboarding پیشنهاد می‌شود'],
  },
  'financial-model': {
    key: 'financial-model', title: 'Financial Modeling', icon: '📈',
    summary: 'مدل مالی نمونه سه‌ساله با درآمد، هزینه و سود عملیاتی.',
    metrics: [
      { label: 'Revenue Y3', value: '96B', tone: 'positive' },
      { label: 'EBITDA Margin', value: '22٪', tone: 'positive' },
      { label: 'Break-even', value: 'ماه 16' },
    ],
    bullets: ['رشد درآمد مرکب ۴۱٪', 'حاشیه سود از سال دوم مثبت', 'نیاز سرمایه در گردش در سناریوی رشد سریع'],
  },
  scenario: {
    key: 'scenario', title: 'Scenario Analysis', icon: '🔮',
    summary: 'مقایسه نمونه سناریوی بدبینانه، پایه و خوش‌بینانه.',
    metrics: [
      { label: 'بدبینانه', value: '-6٪', tone: 'negative' },
      { label: 'پایه', value: '+12٪', tone: 'positive' },
      { label: 'خوش‌بینانه', value: '+29٪', tone: 'positive' },
    ],
    bullets: ['عامل حساس: نرخ تبدیل', 'عامل دوم: CAC', 'سناریوی پایه با بودجه فعلی قابل تحقق است'],
  },
  unit: {
    key: 'unit', title: 'Unit Economics', icon: '⚙️',
    summary: 'اقتصاد واحد نمونه برای ارزیابی کیفیت رشد.',
    metrics: [
      { label: 'CAC', value: '640K' },
      { label: 'LTV', value: '3.8M', tone: 'positive' },
      { label: 'LTV/CAC', value: '5.9x', tone: 'positive' },
    ],
    bullets: ['LTV/CAC در محدوده سالم', 'Payback حدود ۴.۳ ماه', 'افزایش retention بیشترین اثر را دارد'],
  },
  mbr: {
    key: 'mbr', title: 'گزارش MBR', icon: '🧾',
    summary: 'نمونه گزارش ماهانه مدیریت با KPI، ریسک و اقدام بعدی.',
    metrics: [
      { label: 'KPI سبز', value: '11', tone: 'positive' },
      { label: 'ریسک', value: '3', tone: 'negative' },
      { label: 'Action', value: '7' },
    ],
    bullets: ['فروش و retention بالاتر از هدف', 'هزینه جذب نیازمند پایش', 'سه اقدام اولویت‌دار برای ماه بعد'],
  },
};

export const DEMO_PORTFOLIO = {
  totalValue: 4_287_650_000,
  totalPnl: 91_340_000,
  totalPnlPct: 2.18,
  positions: [
    { symbol: 'فولاد', weight: 35.2, pnlPct: 3.4 },
    { symbol: 'فملی', weight: 24.8, pnlPct: 1.7 },
    { symbol: 'شپنا', weight: 15.6, pnlPct: -0.8 },
    { symbol: 'وبملت', weight: 12.6, pnlPct: 2.1 },
  ],
};