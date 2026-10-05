import { useMemo, useState } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Text, View, useColorScheme } from 'react-native';
import { useGlobalSearchParams, usePathname } from 'expo-router';

import { BottomTabInset, Brand, Colors, Fonts, Radius, Spacing } from '@/constants/theme';

type GlossaryEntry = {
  label: string;
  description: string;
  reading?: string;
};

type ModuleGuide = {
  title: string;
  purpose: string;
  inputs: string[];
  terms: string[];
  output: string;
  caution: string;
};

const GLOSSARY: Record<string, GlossaryEntry> = {
  'last-price': { label: 'آخرین قیمت', description: 'قیمت آخرین معامله ثبت‌شده برای نماد.', reading: 'برای تصمیم‌گیری آن را همراه قیمت پایانی و حجم بخوانید؛ یک معامله منفرد می‌تواند گمراه‌کننده باشد.' },
  'closing-price': { label: 'قیمت پایانی', description: 'قیمت مبنای رسمی پایان روز که وزن معاملات روز را منعکس می‌کند.', reading: 'فاصله زیاد آخرین قیمت و پایانی می‌تواند نشان دهد حرکت انتهای بازار هنوز در کل معاملات روز تثبیت نشده است.' },
  change: { label: 'تغییر / درصد تغییر', description: 'فاصله قیمت نسبت به مبنای مقایسه، معمولاً قیمت روز قبل.', reading: 'مثبت یا منفی بودن به‌تنهایی کافی نیست؛ دامنه نوسان، حجم و سابقه نماد را هم ببینید.' },
  volume: { label: 'حجم معامله', description: 'تعداد سهام معامله‌شده در بازه نمایش‌داده‌شده.', reading: 'حرکت قیمت با حجم بالاتر معمولاً اعتبار بیشتری از حرکت کم‌حجم دارد، اما تضمین ادامه روند نیست.' },
  pe: { label: 'P/E', description: 'نسبت قیمت سهم به سود هر سهم؛ یک سنجه ساده برای ارزش‌گذاری نسبی.', reading: 'P/E را با صنعت، کیفیت سود و چرخه کسب‌وکار مقایسه کنید؛ P/E پایین الزاماً به معنی ارزندگی نیست.' },
  eps: { label: 'EPS', description: 'سود منتسب به هر سهم بر اساس داده در دسترس.', reading: 'به منبع و دوره EPS توجه کنید و آن را با سود تاریخی و کیفیت سود بررسی کنید.' },
  'market-cap': { label: 'ارزش بازار', description: 'ارزش تقریبی کل سهام شرکت در بازار.', reading: 'برای مقایسه اندازه شرکت‌ها مفید است، اما جایگزین ارزش‌گذاری بنیادی نیست.' },
  'data-source': { label: 'منبع داده', description: 'سامانه‌ای که مقدار از آن آمده؛ مانند TSETMC، Tindex، CODAL یا داده داخلی.', reading: 'LIVE یعنی داده واقعی متصل؛ نبود داده باید خالی بماند و با عدد ساختگی پر نشود.' },

  'kiasha-call': { label: 'BUY / HOLD / SELL', description: 'جمع‌بندی جهت‌دار کیاشا از رأی عامل‌ها و داده موجود.', reading: 'این خروجی پیشنهاد تحلیلی است، نه تضمین بازده یا دستور قطعی معامله.' },
  score: { label: 'Score', description: 'امتیاز تجمیعی سیگنال‌ها پس از وزن‌دهی عامل‌های تحلیلی.', reading: 'هرچه فاصله از حالت خنثی بیشتر باشد، جهت رأی قوی‌تر است؛ منبع داده و ریسک را هم بررسی کنید.' },
  confidence: { label: 'Confidence', description: 'میزان اطمینان مدل به خروجی بر اساس شواهد و سازگاری عامل‌ها.', reading: 'اعتماد بالا به معنی قطعیت بازار نیست؛ فقط نشان می‌دهد شواهد مدل هم‌جهت‌تر بوده‌اند.' },
  agents: { label: 'عامل‌های AI', description: 'عامل‌های مستقل مثل بنیادی، ریسک، پیش‌بینی و مقایسه که جداگانه رأی می‌دهند.', reading: 'اختلاف رأی عامل‌ها مهم است؛ توافق کامل و اختلاف شدید را یکسان تفسیر نکنید.' },
  risk: { label: 'کنترل ریسک', description: 'محدودیت‌هایی برای اندازه سفارش، زیان روزانه، مالکیت و وضعیت حساب.', reading: 'رد شدن توسط ریسک یعنی سفارش از سیاست حساب عبور نکرده، حتی اگر سیگنال تحلیلی مثبت باشد.' },
  paper: { label: 'Paper', description: 'معامله شبیه‌سازی‌شده با حساب مجازی و بدون اتصال به کارگزاری واقعی.', reading: 'نتیجه Paper را با معامله واقعی یکی ندانید؛ لغزش قیمت، نقدشوندگی و کارمزد واقعی می‌تواند متفاوت باشد.' },

  equity: { label: 'ارزش کل حساب', description: 'جمع موجودی نقد و ارزش روز موقعیت‌های ثبت‌شده.', reading: 'برای روند عملکرد مفید است؛ افت‌وخیز روزانه را از بازده بلندمدت جدا کنید.' },
  cash: { label: 'وجه نقد', description: 'بخش استفاده‌نشده سرمایه که در موقعیت باز قرار ندارد.', reading: 'نقد بالا ریسک بازار را کم می‌کند اما می‌تواند بازده بالقوه را نیز کاهش دهد.' },
  'position-value': { label: 'ارزش موقعیت‌ها', description: 'ارزش فعلی دارایی‌های باز بر اساس قیمت در دسترس.', reading: 'اگر قیمت تازه در دسترس نباشد، ارزش‌گذاری ممکن است با تأخیر یا محدودیت نمایش داده شود.' },
  pnl: { label: 'سود/زیان (PnL)', description: 'تفاوت ارزش فعلی یا فروش با بهای تمام‌شده.', reading: 'Realized مربوط به معامله بسته‌شده و Unrealized مربوط به موقعیت باز است.' },
  allocation: { label: 'تخصیص', description: 'سهم هر دارایی یا بخش از کل پرتفوی.', reading: 'تمرکز زیاد روی یک نماد یا صنعت ریسک غیرسیستماتیک را بالا می‌برد.' },

  records: { label: 'رکوردها', description: 'تعداد ردیف‌های داده‌ای که وارد تحلیل شده‌اند.', reading: 'نمونه کوچک می‌تواند نتیجه ناپایدار بدهد؛ کیفیت و پوشش رکوردها از تعداد صرف مهم‌تر است.' },
  mean: { label: 'میانگین', description: 'متوسط مقدار یک متغیر در داده انتخاب‌شده.', reading: 'اگر داده Outlier زیاد دارد، میانگین را همراه میانه و پراکندگی بخوانید.' },
  outlier: { label: 'Outlier', description: 'رکوردی که نسبت به الگوی غالب فاصله غیرعادی دارد.', reading: 'Outlier الزاماً خطا نیست؛ ممکن است رخداد واقعی و مهم کسب‌وکار باشد.' },
  correlation: { label: 'همبستگی', description: 'میزان حرکت مشترک دو متغیر.', reading: 'همبستگی علت و معلول را ثابت نمی‌کند؛ فقط رابطه آماری را نشان می‌دهد.' },

  'query-rows': { label: 'ردیف نتیجه', description: 'تعداد ردیف‌هایی که Query برگردانده است.', reading: 'تعداد زیاد یا کم به‌خودی‌خود خوب یا بد نیست؛ باید با سؤال تحلیلی تطبیق داشته باشد.' },
  'query-time': { label: 'زمان اجرا', description: 'مدت زمان لازم برای اجرای Query و آماده‌شدن نتیجه.', reading: 'برای تجربه کاربری و بهینه‌سازی مفید است و معنی تجاری داده را تغییر نمی‌دهد.' },
  'query-sources': { label: 'منابع / جدول‌ها', description: 'تعداد یا نوع مجموعه‌داده‌هایی که Query از آن‌ها استفاده کرده.', reading: 'هرچه منابع بیشتر شوند، کنترل تعریف فیلدها و هم‌ترازی دوره‌ها مهم‌تر می‌شود.' },

  'open-alerts': { label: 'هشدار باز', description: 'ناهنجاری‌هایی که شناسایی شده‌اند و هنوز بررسی یا بسته نشده‌اند.', reading: 'هشدار را ابتدا بر اساس شدت و اثر کسب‌وکاری اولویت‌بندی کنید.' },
  severity: { label: 'شدت', description: 'درجه فاصله رفتار مشاهده‌شده از الگوی عادی یا آستانه تعیین‌شده.', reading: 'شدت بالا نیازمند بررسی سریع‌تر است، اما علت را به‌تنهایی مشخص نمی‌کند.' },
  coverage: { label: 'پوشش', description: 'درصد داده یا شاخص‌هایی که پایش ناهنجاری روی آن‌ها انجام شده است.', reading: 'پوشش پایین یعنی نبود هشدار ممکن است صرفاً ناشی از نبود داده باشد.' },

  'forecast-growth': { label: 'رشد پیش‌بینی', description: 'تغییر مورد انتظار متغیر هدف در افق آینده بر اساس تاریخچه موجود.', reading: 'این مقدار سناریوی آماری است و با ورود اطلاعات جدید می‌تواند تغییر کند.' },
  'confidence-band': { label: 'بازه اطمینان', description: 'دامنه‌ای برای نشان‌دادن عدم‌قطعیت اطراف پیش‌بینی مرکزی.', reading: 'بازه بزرگ‌تر یعنی عدم‌قطعیت بیشتر؛ فقط عدد مرکزی را بدون بازه نخوانید.' },
  horizon: { label: 'افق پیش‌بینی', description: 'فاصله زمانی آینده که مدل برای آن برآورد ارائه می‌کند.', reading: 'معمولاً هرچه افق دورتر باشد عدم‌قطعیت بیشتر می‌شود.' },

  touchpoint: { label: 'Touchpoint', description: 'نقطه تماس مشتری با محصول، برند یا تیم.', reading: 'نقاط تماس پرتکرار و حساس را برای بهبود تجربه در اولویت قرار دهید.' },
  painpoint: { label: 'Pain Point', description: 'بخشی از مسیر مشتری که اصطکاک، نارضایتی یا ریزش ایجاد می‌کند.', reading: 'Pain Point را با حجم کاربران و اثر مالی اولویت‌بندی کنید.' },
  'moment-of-truth': { label: 'Moment of Truth', description: 'لحظه‌ای که تجربه آن می‌تواند تصمیم مشتری را به‌طور جدی تغییر دهد.', reading: 'این نقاط معمولاً ارزش بالایی برای آزمایش و بهبود دارند.' },
  nps: { label: 'NPS', description: 'شاخص تمایل مشتری به توصیه محصول/خدمت، معمولاً در بازه -100 تا +100.', reading: 'روند NPS و متن بازخوردها از یک عدد منفرد مهم‌تر است.' },
  friction: { label: 'Friction', description: 'مرحله یا مانعی که انجام کار را برای کاربر سخت‌تر می‌کند.', reading: 'اصطکاک را با شواهد رفتاری و صدای مشتری تأیید کنید.' },
  theme: { label: 'Theme / موضوع پرتکرار', description: 'الگوی مشترک استخراج‌شده از بازخوردها یا تعاملات.', reading: 'تکرار زیاد موضوع نشانه اهمیت است، اما شدت و نوع مشتری را هم در نظر بگیرید.' },

  funnel: { label: 'Funnel', description: 'تعداد یا نرخ عبور کاربران از مراحل متوالی یک مسیر.', reading: 'بزرگ‌ترین افت بین دو مرحله معمولاً نقطه مناسب برای بررسی است.' },
  churn: { label: 'Churn', description: 'نرخ از دست رفتن مشتری یا کاربر در یک دوره.', reading: 'کاهش Churn معمولاً مثبت است؛ تعریف مشتری فعال و طول دوره را ثابت نگه دارید.' },
  retention: { label: 'Retention', description: 'درصد کاربران یا مشتریانی که پس از یک بازه همچنان فعال می‌مانند.', reading: 'Retention را به تفکیک cohort و کانال جذب مقایسه کنید.' },
  conversion: { label: 'Conversion', description: 'درصد افرادی که از یک مرحله به اقدام هدف می‌رسند.', reading: 'تعریف مخرج و صورت باید روشن باشد؛ تغییر تعریف می‌تواند نرخ را ظاهراً تغییر دهد.' },

  kpi: { label: 'KPI', description: 'شاخص کلیدی عملکردی که مستقیماً به یک هدف مدیریتی وصل است.', reading: 'KPI خوب باید تعریف، مالک، منبع داده، دوره و هدف مشخص داشته باشد.' },
  target: { label: 'هدف', description: 'مقدار مورد انتظار یا آستانه مطلوب برای یک شاخص.', reading: 'فاصله مقدار واقعی با هدف مبنای تحلیل انحراف است.' },
  owner: { label: 'مالک KPI', description: 'شخص یا تیم مسئول پیگیری و اقدام روی شاخص.', reading: 'بدون مالک مشخص، KPI بیشتر گزارش است تا ابزار مدیریت.' },
  revenue: { label: 'Revenue / درآمد', description: 'فروش یا درآمد شناسایی‌شده در دوره بر اساس منبع داده.', reading: 'دوره، واحد پول و تلفیقی/جداگانه بودن صورت مالی را ثابت نگه دارید.' },
  cost: { label: 'هزینه', description: 'هزینه مرتبط با عملیات، فروش یا متغیر تعریف‌شده در داده.', reading: 'برای مقایسه دوره‌ای مطمئن شوید طبقه‌بندی هزینه تغییر نکرده است.' },
  'gross-margin': { label: 'حاشیه سود ناخالص', description: 'سود ناخالص نسبت به درآمد؛ نشان‌دهنده اقتصاد اصلی محصول/خدمت قبل از هزینه‌های بعدی.', reading: 'روند حاشیه در کنار رشد درآمد برای تشخیص کیفیت رشد مهم است.' },
  'active-customers': { label: 'مشتری فعال', description: 'تعداد مشتریانی که طبق تعریف کسب‌وکار در دوره فعال محسوب می‌شوند.', reading: 'تعریف «فعال» باید بین دوره‌ها ثابت باشد تا مقایسه معتبر بماند.' },
  insight: { label: 'Insight', description: 'برداشت تحلیلی که از داده و شواهد استخراج شده است.', reading: 'Insight باید به داده قابل ردیابی متصل باشد، نه صرفاً یک متن عمومی.' },
  action: { label: 'Action', description: 'اقدام پیشنهادی یا تصمیم بعدی که از تحلیل نتیجه می‌شود.', reading: 'Action خوب مالک، زمان و معیار موفقیت دارد.' },
  variance: { label: 'انحراف', description: 'فاصله عملکرد واقعی از هدف، بودجه یا دوره مقایسه.', reading: 'انحراف را به مقدار مطلق و درصدی و علت احتمالی تفکیک کنید.' },

  strength: { label: 'Strength / قوت', description: 'توانمندی داخلی که به مزیت یا عملکرد بهتر کمک می‌کند.', reading: 'قوت باید با شواهد داخلی یا بازار پشتیبانی شود.' },
  weakness: { label: 'Weakness / ضعف', description: 'محدودیت داخلی که عملکرد یا رقابت‌پذیری را کاهش می‌دهد.', reading: 'ضعف را از تهدید بیرونی جدا کنید تا اقدام اصلاحی روشن باشد.' },
  competitor: { label: 'رقیب کلیدی', description: 'شرکت یا راه‌حل جایگزینی که برای مشتری و بازار مشابه رقابت می‌کند.', reading: 'مقایسه را بر اساس معیار یکسان مثل قیمت، سهم بازار یا تجربه مشتری انجام دهید.' },
  segment: { label: 'Segment', description: 'بخش مشخصی از بازار با ویژگی‌ها یا نیازهای مشترک.', reading: 'جذابیت Segment را با اندازه، رشد، دسترسی و تناسب با توان شرکت بسنجید.' },
  channel: { label: 'Channel', description: 'مسیر دسترسی، فروش یا بازاریابی به مشتری.', reading: 'کانال را با CAC، نرخ تبدیل و ظرفیت مقیاس مقایسه کنید.' },
  'market-risk': { label: 'ریسک بازار', description: 'مانع بیرونی مانند رقابت، مقررات، تقاضا یا هزینه ورود.', reading: 'ریسک را با احتمال و اثر جداگانه امتیازدهی کنید.' },

  pipeline: { label: 'Pipeline', description: 'ارزش یا تعداد فرصت‌های فروش در مراحل مختلف.', reading: 'Pipeline خام را با احتمال بستن و کیفیت فرصت‌ها تعدیل کنید.' },
  'win-rate': { label: 'Win Rate', description: 'درصد فرصت‌هایی که به قرارداد موفق تبدیل می‌شوند.', reading: 'Win Rate را به تفکیک کانال، فروشنده و Segment بررسی کنید.' },
  opportunity: { label: 'Opportunity', description: 'فرصت فروش واجد شرایط که در قیف پیگیری می‌شود.', reading: 'تعداد فرصت بدون ارزش، احتمال و سن فرصت تصویر کاملی نمی‌دهد.' },
  budget: { label: 'Budget', description: 'بودجه تخصیص‌یافته به کمپین یا فعالیت.', reading: 'بودجه را در کنار نتیجه نهایی و هزینه جذب بخوانید.' },
  roas: { label: 'ROAS', description: 'درآمد منتسب به تبلیغات تقسیم بر هزینه تبلیغات.', reading: 'ROAS بالا همیشه به معنی سودآوری نیست؛ حاشیه سود و هزینه‌های دیگر را نیز لحاظ کنید.' },
  lead: { label: 'Lead', description: 'سرنخ بالقوه‌ای که امکان تبدیل به مشتری دارد.', reading: 'کیفیت Lead و نرخ تبدیل آن مهم‌تر از تعداد خام است.' },

  'base-price': { label: 'قیمت پایه', description: 'قیمت فعلی یا مرجع برای مقایسه سناریوهای قیمت‌گذاری.', reading: 'باید با واحد محصول، مالیات و تخفیف‌ها سازگار باشد.' },
  'recommended-price': { label: 'قیمت پیشنهادی', description: 'قیمت سناریویی حاصل از داده هزینه، تقاضا و قیود موجود.', reading: 'قبل از rollout کامل با A/B Test یا بازار محدود اعتبارسنجی شود.' },
  'revenue-impact': { label: 'اثر درآمد', description: 'تغییر برآوردی درآمد در صورت اجرای سناریوی قیمت.', reading: 'وابسته به فرض کشش تقاضا و حجم فروش است و تضمین نیست.' },

  tam: { label: 'TAM', description: 'کل اندازه نظری بازار در صورت دستیابی به همه تقاضای مرتبط.', reading: 'TAM سقف نظری است و با بازار قابل خدمت یا سهم واقع‌بینانه یکی نیست.' },
  som: { label: 'SOM', description: 'سهم واقع‌بینانه‌ای از بازار که شرکت در افق مشخص می‌تواند هدف بگیرد.', reading: 'SOM باید با ظرفیت فروش، رقابت و بودجه سازگار باشد.' },
  runway: { label: 'Runway', description: 'مدت زمانی که نقدینگی موجود با نرخ مصرف فعلی دوام می‌آورد.', reading: 'کاهش هزینه یا افزایش درآمد Runway را تغییر می‌دهد؛ نرخ مصرف را دوره‌ای بازبینی کنید.' },

  'scenario-base': { label: 'سناریوی پایه', description: 'سناریوی مرکزی با مفروضات محتمل‌تر.', reading: 'پایه مرجع مقایسه است، نه پیش‌بینی قطعی.' },
  upside: { label: 'سناریوی خوش‌بینانه', description: 'حالت با مفروضات بهتر مانند رشد بیشتر یا هزینه کمتر.', reading: 'فرض‌ها باید صریح باشند تا خوش‌بینی با آرزو اشتباه نشود.' },
  downside: { label: 'سناریوی بدبینانه', description: 'حالت فشار با رشد کمتر، هزینه بیشتر یا ریسک بالاتر.', reading: 'برای سنجش تاب‌آوری نقدینگی و تصمیم‌های محافظه‌کارانه مفید است.' },
  cac: { label: 'CAC', description: 'هزینه متوسط جذب یک مشتری جدید.', reading: 'هزینه‌های فروش و بازاریابی مرتبط را در تعریف CAC ثابت نگه دارید.' },
  ltv: { label: 'LTV', description: 'ارزش اقتصادی مورد انتظار یک مشتری در طول رابطه.', reading: 'LTV به حاشیه سود، Retention و رفتار تکرار خرید حساس است.' },
  'unit-margin': { label: 'حاشیه واحد', description: 'سود یا مشارکت اقتصادی هر واحد محصول، سفارش یا مشتری.', reading: 'اگر حاشیه واحد منفی باشد، رشد حجم ممکن است زیان را بزرگ‌تر کند.' },
  payback: { label: 'Payback', description: 'زمان لازم برای بازگشت هزینه جذب یا سرمایه‌گذاری اولیه.', reading: 'Payback کوتاه‌تر معمولاً فشار نقدینگی را کاهش می‌دهد.' },
  mbr: { label: 'MBR', description: 'Monthly Business Review؛ مرور منظم عملکرد، انحراف و اقدام‌های ماه.', reading: 'MBR باید روند، علت انحراف، مالک اقدام و موعد پیگیری داشته باشد.' },

  side: { label: 'خرید / فروش', description: 'جهت سفارش ثبت‌شده.', reading: 'جهت سفارش را از وضعیت اجرا جدا بخوانید؛ ثبت BUY لزوماً به معنی اجراشدن نیست.' },
  quantity: { label: 'تعداد', description: 'حجم سهم یا واحدی که سفارش برای آن ثبت شده است.', reading: 'اندازه سفارش باید با موجودی، نقدشوندگی و سیاست ریسک سازگار باشد.' },
  status: { label: 'وضعیت سفارش', description: 'مرحله فعلی سفارش مثل اجراشده، در انتظار، لغوشده یا ردشده.', reading: 'وضعیت منبع اصلی تشخیص نتیجه سفارش است؛ صرف وجود سفارش به معنی معامله نیست.' },

  'auto-source': { label: 'AUTO', description: 'فیلدی که BIAP می‌تواند از منبع عمومی متصل برای شرکت بورسی پر کند.', reading: 'AUTO به معنی موجودبودن قطعی مقدار نیست؛ اگر منبع آن فیلد را نداشته باشد مقدار خالی می‌ماند.' },
  'required-field': { label: 'فیلد لازم', description: 'ورودی‌ای که برای اجرای معتبر ماژول مورد نیاز است.', reading: 'نبود فیلد لازم باید باعث محدودشدن خروجی شود، نه ساختن داده.' },
  'optional-field': { label: 'فیلد اختیاری', description: 'داده‌ای که کیفیت یا عمق تحلیل را بهتر می‌کند اما همیشه الزامی نیست.', reading: 'افزودن داده اختیاری می‌تواند تحلیل را غنی‌تر کند بدون اینکه مسیر پایه را مسدود کند.' },
};

const GUIDES: Record<string, ModuleGuide> = {
  market: {
    title: 'بازار و تحلیل نماد',
    purpose: 'نمایش وضعیت واقعی نماد، قیمت، تغییرات و شاخص‌های بازار برای اینکه قبل از تحلیل یا سفارش تصویر اولیه روشنی داشته باشید.',
    inputs: ['TSETMC / Tindex برای قیمت و بازار', 'CODAL برای داده‌های بنیادی در مسیر تحلیل', 'هیچ مقدار ناموجودی در Real Mode ساخته نمی‌شود'],
    terms: ['last-price', 'closing-price', 'change', 'volume', 'pe', 'eps', 'market-cap', 'data-source'],
    output: 'از این صفحه برای شناخت وضعیت نماد و ورود به تحلیل عمیق‌تر استفاده کنید؛ قیمت تنها یکی از اجزای تصمیم است.',
    caution: 'داده بازار می‌تواند با تأخیر یا محدودیت منبع روبه‌رو شود. این صفحه به‌تنهایی توصیه سرمایه‌گذاری نیست.',
  },
  kiasha: {
    title: 'کیاشا AI Agents',
    purpose: 'ترکیب چند عامل تحلیلی مستقل برای ساخت یک جمع‌بندی BUY / HOLD / SELL همراه با دلیل، اطمینان و کنترل ریسک.',
    inputs: ['داده بازار و بنیادی متصل', 'رأی عامل‌های Fundamental / Risk / Forecast / Comparison', 'سیاست ریسک حساب و وضعیت Paper'],
    terms: ['kiasha-call', 'score', 'confidence', 'agents', 'risk', 'paper'],
    output: 'ابتدا جهت رأی را ببینید، سپس اختلاف عامل‌ها، Confidence، منبع داده و محدودیت‌های ریسک را بررسی کنید.',
    caution: 'خروجی AI تضمین سود نیست. تصمیم نهایی باید با ریسک‌پذیری و بررسی مستقل کاربر سازگار باشد.',
  },
  portfolio: {
    title: 'پرتفوی',
    purpose: 'نمایش ارزش حساب، وجه نقد، موقعیت‌ها، سود/زیان و تمرکز دارایی‌ها در حساب مربوطه.',
    inputs: ['معاملات و موقعیت‌های ثبت‌شده همان حساب', 'قیمت‌های در دسترس برای ارزش‌گذاری', 'حالت Paper، Demo و Real از هم جدا نگه داشته می‌شوند'],
    terms: ['equity', 'cash', 'position-value', 'pnl', 'allocation', 'paper'],
    output: 'روند ارزش کل، سود/زیان و تمرکز هر موقعیت را با هم بخوانید تا فقط یک عدد روزانه مبنای قضاوت نباشد.',
    caution: 'ارزش‌گذاری موقعیت به تازگی قیمت وابسته است. نتایج Paper معادل اجرای واقعی بازار نیستند.',
  },
  eda: {
    title: 'EDA Explorer',
    purpose: 'شناخت اولیه کیفیت، توزیع، روند و روابط مهم در dataset پیش از مدل‌سازی یا تصمیم‌گیری.',
    inputs: ['رکوردهای ساختاریافته', 'ستون‌های عددی و دسته‌ای موجود', 'برای شرکت بورسی بخشی از داده می‌تواند خودکار بیاید'],
    terms: ['records', 'mean', 'outlier', 'correlation'],
    output: 'EDA برای کشف سؤال و الگو است؛ نتیجه آن را فرضیه‌ای برای بررسی بعدی در نظر بگیرید.',
    caution: 'همبستگی علت و معلول نیست و Outlier را نباید بدون بررسی حذف کرد.',
  },
  sql: {
    title: 'SQL / Data Query',
    purpose: 'تبدیل context واقعی شرکت یا dataset داخلی به جدول قابل پرس‌وجو برای پاسخ دقیق به سؤال‌های داده‌ای.',
    inputs: ['ستون‌ها و رکوردهای قابل تحلیل', 'TSETMC / Tindex / CODAL برای شرکت بورسی', 'SQL یا dataset خصوصی در صورت نیاز'],
    terms: ['query-rows', 'query-time', 'query-sources', 'data-source'],
    output: 'نتیجه Query باید مستقیماً به سؤال شما پاسخ دهد؛ تعداد ردیف و منبع‌ها برای کنترل کیفیت نتیجه نمایش داده می‌شوند.',
    caution: 'Query فقط داده موجود را می‌بیند. نبود ستون یا دوره لازم نباید با فرض ساختگی جبران شود.',
  },
  anomaly: {
    title: 'تشخیص ناهنجاری',
    purpose: 'پیدا کردن رفتارهای غیرعادی در سری زمانی یا شاخص‌ها تا موارد نیازمند بررسی سریع‌تر شوند.',
    inputs: ['تاریخ/دوره معتبر', 'حداقل یک شاخص عددی', 'تاریخچه کافی برای شناخت الگوی معمول'],
    terms: ['open-alerts', 'severity', 'coverage', 'outlier'],
    output: 'هشدارها را بر اساس شدت، اثر کسب‌وکاری و پوشش داده اولویت‌بندی کنید.',
    caution: 'ناهنجاری علت را مشخص نمی‌کند و می‌تواند رخداد واقعی، تغییر ساختاری یا خطای داده باشد.',
  },
  forecast: {
    title: 'پیش‌بینی آماری',
    purpose: 'برآورد روند آینده یک متغیر بر اساس تاریخچه واقعی و نمایش عدم‌قطعیت پیش‌بینی.',
    inputs: ['تاریخچه چند دوره', 'متغیر هدف روشن', 'دوره‌های هم‌تراز و بدون شکاف جدی'],
    terms: ['forecast-growth', 'confidence-band', 'horizon'],
    output: 'عدد مرکزی را همیشه همراه بازه اطمینان و افق زمانی بخوانید.',
    caution: 'پیش‌بینی با تغییر شرایط بازار یا کسب‌وکار می‌تواند سریعاً منقضی شود و تضمین آینده نیست.',
  },
  journey: {
    title: 'Journey Map',
    purpose: 'نمایش مسیر مشتری از اولین تماس تا خرید و وفاداری و مشخص‌کردن نقاط اصطکاک مهم.',
    inputs: ['مرحله‌های سفر', 'کاربر/تعداد در هر مرحله', 'Conversion، Drop-off یا رضایت در صورت وجود'],
    terms: ['touchpoint', 'painpoint', 'moment-of-truth', 'conversion', 'churn'],
    output: 'بزرگ‌ترین Pain Point و Moment of Truth را به اقدام مشخص برای تیم محصول یا فروش تبدیل کنید.',
    caution: 'این ماژول برای داده مشتری به داده داخلی نیاز دارد و داده بورسی عمومی به‌تنهایی کافی نیست.',
  },
  voc: {
    title: 'VOC + Friction Points',
    purpose: 'خلاصه‌کردن صدای مشتری و تبدیل بازخوردهای پراکنده به موضوع‌ها و نقاط اصطکاک قابل اقدام.',
    inputs: ['متن بازخورد، تیکت، نظرسنجی یا تماس', 'NPS/CSAT در صورت وجود', 'شناسه مرحله یا محصول برای بخش‌بندی بهتر'],
    terms: ['nps', 'friction', 'theme', 'action'],
    output: 'موضوع پرتکرار را با شدت، Segment مشتری و اثر روی رفتار ترکیب کنید تا اولویت روشن شود.',
    caution: 'نمونه بازخورد ممکن است نماینده همه مشتریان نباشد؛ سوگیری کانال جمع‌آوری را در نظر بگیرید.',
  },
  behavior: {
    title: 'رفتار کاربر',
    purpose: 'تحلیل Funnel، Retention و Churn برای فهم اینکه کاربران کجا پیش می‌روند یا ریزش می‌کنند.',
    inputs: ['رویدادهای کاربر یا CRM', 'تعریف مرحله‌ها و کاربر فعال', 'زمان یا cohort برای مقایسه'],
    terms: ['funnel', 'conversion', 'retention', 'churn'],
    output: 'بزرگ‌ترین افت Funnel و ضعیف‌ترین cohort را برای آزمایش و بهبود انتخاب کنید.',
    caution: 'تعریف رویداد و کاربر فعال باید ثابت بماند؛ تغییر tracking می‌تواند روند ظاهری بسازد.',
  },
  'kpi-extract': {
    title: 'استخراج KPI',
    purpose: 'استخراج شاخص‌های کلیدی از داده موجود برای مرور سریع عملکرد بدون ساختن مقدار ناموجود.',
    inputs: ['داده بازار/CODAL برای شرکت بورسی', 'درآمد، هزینه، مشتری یا نرخ‌های داخلی در صورت وجود', 'دوره مقایسه'],
    terms: ['kpi', 'revenue', 'cost', 'conversion', 'churn', 'nps'],
    output: 'KPI را با تعریف، دوره و مبنای مقایسه بخوانید؛ تغییر شاخص بدون context کافی نیست.',
    caution: 'اگر فیلد لازم وجود ندارد، KPI مربوطه باید ناقص/خالی بماند و از داده ساختگی پر نشود.',
  },
  dashboard: {
    title: 'BI Dashboard',
    purpose: 'ترکیب چند KPI مالی و عملیاتی در یک نمای مدیریتی برای دیدن روند، هدف و نقاط نیازمند اقدام.',
    inputs: ['حداقل یک KPI عددی', 'دوره و هدف در صورت وجود', 'منابع عمومی یا dataset داخلی'],
    terms: ['revenue', 'gross-margin', 'active-customers', 'variance', 'action'],
    output: 'داشبورد را از بالا به پایین بخوانید: وضعیت، روند، انحراف و سپس اقدام.',
    caution: 'Dashboard خلاصه است؛ برای علت‌یابی باید به داده و ماژول عمیق‌تر مراجعه کنید.',
  },
  governance: {
    title: 'KPI Governance',
    purpose: 'تعریف استاندارد KPIها همراه مالک، هدف، تناوب و آستانه تا گزارش‌گیری قابل اتکا و قابل پیگیری شود.',
    inputs: ['نام و تعریف KPI', 'مالک یا تیم مسئول', 'هدف/آستانه و تناوب بازبینی'],
    terms: ['kpi', 'owner', 'target', 'variance', 'action'],
    output: 'KPI بدون مالک یا تعریف پایدار را ناقص در نظر بگیرید و قبل از اتکا به آن Governance را کامل کنید.',
    caution: 'هدف این ماژول کنترل تعریف و مسئولیت است، نه تولید عدد عملکرد از هیچ.',
  },
  report: {
    title: 'گزارش تحلیلی',
    purpose: 'تبدیل داده و KPI واقعی به روایت مدیریتی کوتاه شامل Insight، ریسک و اقدام بعدی.',
    inputs: ['داده واقعی متصل', 'KPIها یا جدول تحلیلی', 'دوره و زمینه تصمیم'],
    terms: ['insight', 'variance', 'action', 'data-source'],
    output: 'هر Insight را به شاهد داده‌ای و هر Action را به مالک/زمان پیگیری متصل کنید.',
    caution: 'متن گزارش نباید جای منبع داده را بگیرد؛ اگر داده ناقص است باید صریحاً ذکر شود.',
  },
  'business-kpi': {
    title: 'داشبورد KPI کسب‌وکار',
    purpose: 'مقایسه فروش، هزینه، مشتری و نرخ‌های کلیدی کسب‌وکار در چند دوره برای مدیریت عملکرد.',
    inputs: ['دوره', 'درآمد و هزینه', 'مشتری، Conversion و Churn در صورت وجود'],
    terms: ['revenue', 'cost', 'active-customers', 'conversion', 'churn', 'variance'],
    output: 'رشد را همراه حاشیه و کیفیت مشتری بخوانید تا رشد پرهزینه با رشد سالم اشتباه نشود.',
    caution: 'برای شاخص‌های مشتری معمولاً داده داخلی لازم است؛ داده بورسی عمومی همه اجزا را پوشش نمی‌دهد.',
  },
  swot: {
    title: 'SWOT + رقبا',
    purpose: 'تفکیک قوت/ضعف داخلی از فرصت/تهدید بیرونی و مقایسه شواهد شرکت با رقبا.',
    inputs: ['شاخص‌های داخلی یا بنیادی شرکت', 'اطلاعات رقبا و بازار در صورت وجود', 'شواهد قابل ردیابی'],
    terms: ['strength', 'weakness', 'competitor', 'market-risk', 'action'],
    output: 'هر مورد SWOT را به شاهد و یک اقدام وصل کنید؛ فهرست عمومی بدون شاهد ارزش تصمیم‌گیری کمی دارد.',
    caution: 'داده عمومی برای شناخت همه رقبا و نقاط داخلی کافی نیست و ممکن است نیاز به تکمیل دستی داشته باشد.',
  },
  'market-entry': {
    title: 'فرصت و ورود به بازار',
    purpose: 'ارزیابی بخش‌های بازار، کانال ورود و ریسک‌ها برای انتخاب مسیر آزمایش اولیه.',
    inputs: ['وضعیت فعلی شرکت', 'بازار هدف و اندازه آن', 'رقبا، کانال‌ها و قیود ورود'],
    terms: ['segment', 'channel', 'tam', 'market-risk', 'action'],
    output: 'یک Segment و کانال اولویت‌دار را با فرض‌های قابل آزمایش و معیار موفقیت مشخص کنید.',
    caution: 'اندازه بازار و رقبا اگر از داده داخلی/تحقیق بازار نیایند ممکن است ناقص باشند؛ فرض‌ها را شفاف نگه دارید.',
  },
  crm: {
    title: 'CRM + Pipeline',
    purpose: 'اولویت‌بندی Leadها و فرصت‌ها بر اساس مرحله، ارزش، احتمال بستن و زمان پیگیری.',
    inputs: ['مشتری/Lead', 'مرحله Pipeline', 'ارزش قرارداد، احتمال و آخرین تماس'],
    terms: ['pipeline', 'win-rate', 'opportunity', 'conversion', 'action'],
    output: 'فرصت‌های با ارزش × احتمال بالا و تماس عقب‌افتاده را برای اقدام بعدی مرتب کنید.',
    caution: 'بدون داده CRM داخلی این ماژول نمی‌تواند Pipeline واقعی شرکت را از داده بازار حدس بزند.',
  },
  campaign: {
    title: 'کمپین بازاریابی',
    purpose: 'برنامه‌ریزی و ارزیابی کانال، بودجه، Lead و بازده کمپین بر اساس داده واقعی.',
    inputs: ['کانال و بودجه', 'Lead/Conversion', 'درآمد منتسب یا داده فروش'],
    terms: ['budget', 'roas', 'lead', 'conversion', 'channel'],
    output: 'کانال‌ها را با ROAS، کیفیت Lead و Conversion کنار هم مقایسه کنید؛ یک KPI را تنها نخوانید.',
    caution: 'انتساب درآمد به کمپین می‌تواند ناقص باشد و ROAS معادل سود خالص نیست.',
  },
  pricing: {
    title: 'قیمت‌گذاری هوشمند',
    purpose: 'مقایسه سناریوهای قیمت با هزینه، حجم فروش و واکنش احتمالی تقاضا.',
    inputs: ['قیمت فعلی', 'هزینه تمام‌شده', 'حجم فروش و در صورت وجود قیمت رقیب/Conversion'],
    terms: ['base-price', 'recommended-price', 'revenue-impact', 'cost', 'conversion'],
    output: 'قیمت پیشنهادی را به‌عنوان سناریوی قابل آزمایش ببینید و اثر آن بر درآمد و تبدیل را پایش کنید.',
    caution: 'داده بورسی به‌تنهایی معمولاً قیمت محصول و کشش تقاضا را نمی‌دهد؛ داده داخلی لازم است.',
  },
  plan: {
    title: 'Business Plan',
    purpose: 'ساخت تصویر منسجم از بازار، مدل درآمد، هزینه، مشتری و milestones برای برنامه‌ریزی.',
    inputs: ['درآمد/هزینه', 'بازار هدف و مشتری', 'فرض‌های رشد و منابع'],
    terms: ['tam', 'som', 'runway', 'revenue', 'cost'],
    output: 'طرح را به فرض‌های قابل اندازه‌گیری، milestone و سناریوی نقدینگی تبدیل کنید.',
    caution: 'Business Plan پیش‌بینی قطعی نیست؛ فرض‌های بازار و مالی باید دوره‌ای با داده واقعی بازبینی شوند.',
  },
  'executive-report': {
    title: 'گزارش مدیریتی',
    purpose: 'خلاصه عملکرد دوره برای مدیر ارشد یا هیئت‌مدیره با تمرکز بر KPI، انحراف و اقدام.',
    inputs: ['عملکرد دوره جاری', 'دوره قبل/هدف', 'KPIها و نکات مهم'],
    terms: ['kpi', 'variance', 'insight', 'action', 'owner'],
    output: 'گزارش خوب باید بگوید چه اتفاقی افتاد، چرا مهم است، و چه کسی تا چه زمانی چه کاری انجام می‌دهد.',
    caution: 'اختصار مدیریتی نباید محدودیت داده یا عدم‌قطعیت را پنهان کند.',
  },
  'financial-model': {
    title: 'Financial Modeling',
    purpose: 'ساخت نمای مالی ساختاریافته از درآمد، هزینه، حاشیه و روند بر پایه داده تاریخی شرکت.',
    inputs: ['درآمد و هزینه چند دوره', 'CODAL برای شرکت بورسی در صورت دسترس', 'داده داخلی برای جزئیاتی که عمومی نیست'],
    terms: ['revenue', 'cost', 'gross-margin', 'variance', 'data-source'],
    output: 'مدل پایه را برای فهم محرک‌های مالی و آماده‌سازی سناریوها استفاده کنید، نه به‌عنوان ارزش‌گذاری قطعی.',
    caution: 'هم‌ترازی دوره‌ها، واحد پول و تلفیقی/جداگانه بودن صورت‌ها برای مقایسه معتبر ضروری است.',
  },
  scenario: {
    title: 'Scenario Analysis',
    purpose: 'دیدن اثر تغییر فرض‌های کلیدی روی نتایج مالی در سناریوی پایه، خوش‌بینانه و بدبینانه.',
    inputs: ['مدل پایه', 'فرض‌های رشد/هزینه', 'دامنه تغییر قابل دفاع'],
    terms: ['scenario-base', 'upside', 'downside', 'revenue', 'cost'],
    output: 'به‌جای انتخاب یک عدد، دامنه نتایج و حساس‌ترین فرض‌ها را برای تصمیم‌گیری ببینید.',
    caution: 'سناریوها به کیفیت فرض‌ها وابسته‌اند؛ خوش‌بینانه و بدبینانه نباید بدون منطق داده‌ای تعیین شوند.',
  },
  unit: {
    title: 'Unit Economics',
    purpose: 'سنجش اقتصاد هر مشتری/سفارش/واحد تا مشخص شود رشد در سطح واحد ارزش ایجاد می‌کند یا نه.',
    inputs: ['CAC یا هزینه جذب', 'درآمد/حاشیه هر مشتری یا واحد', 'Retention یا تکرار خرید در صورت وجود'],
    terms: ['cac', 'ltv', 'unit-margin', 'payback'],
    output: 'LTV/CAC، حاشیه واحد و Payback را کنار هم بخوانید تا رشد زیان‌ده پنهان نشود.',
    caution: 'تعریف واحد و تخصیص هزینه‌ها باید ثابت باشد؛ تخمین LTV با تاریخچه کوتاه عدم‌قطعیت زیادی دارد.',
  },
  mbr: {
    title: 'گزارش MBR',
    purpose: 'مرور ماهانه عملکرد برای پیگیری روند، انحراف، علت و اقدام‌های باز.',
    inputs: ['KPIهای ماه جاری', 'هدف/ماه قبل', 'اقدام‌های ماه قبل و وضعیت آن‌ها'],
    terms: ['mbr', 'kpi', 'variance', 'action', 'owner'],
    output: 'MBR را به چرخه مدیریت تبدیل کنید: مشاهده → علت → تصمیم → مالک → پیگیری ماه بعد.',
    caution: 'اگر تعریف KPI بین ماه‌ها تغییر کند، روند MBR قابل اتکا نخواهد بود.',
  },

  orders: {
    title: 'سفارش‌ها',
    purpose: 'نمایش تاریخچه سفارش‌های همین حساب با جهت، تعداد، وضعیت و منبع اجرا.',
    inputs: ['سفارش‌های per-user از سرور', 'Paper/Demo/Manual به‌صورت تفکیک‌شده'],
    terms: ['side', 'quantity', 'status', 'paper', 'risk'],
    output: 'برای نتیجه هر سفارش، وضعیت را ببینید؛ ثبت سفارش با اجراشدن آن یکی نیست.',
    caution: 'Demo فقط روی دستگاه است و با تاریخچه Paper سرور یکی نمی‌شود.',
  },
  'data-connect': {
    title: 'اتصال داده',
    purpose: 'مشخص‌کردن اینکه هر ماژول چه داده‌ای لازم دارد و کدام بخش خودکار یا نیازمند داده داخلی است.',
    inputs: ['شرکت بورسی انتخاب‌شده', 'CSV/Excel/SQL/API در صورت نیاز', 'تعریف فیلدهای هر ماژول'],
    terms: ['auto-source', 'required-field', 'optional-field', 'data-source'],
    output: 'قبل از اجرای ماژول مطمئن شوید فیلدهای لازم پوشش داده شده‌اند و منبع هر مقدار روشن است.',
    caution: 'داده خصوصی اختیاری است مگر ماژول به اطلاعاتی نیاز داشته باشد که از منابع عمومی قابل استخراج نیست.',
  },
  data: {
    title: 'داده و تحلیل',
    purpose: 'مرور داده متصل، شاخص‌های پایه و مسیر ورود به ماژول‌های تحلیلی.',
    inputs: ['داده بازار/شرکت یا dataset متصل', 'منبع و زمان به‌روزرسانی'],
    terms: ['data-source', 'records', 'mean', 'outlier'],
    output: 'ابتدا کیفیت و منبع را بررسی کنید و سپس ماژول مناسب سؤال خود را انتخاب کنید.',
    caution: 'نمودار یا آمار پایه بدون بررسی پوشش و تازگی داده می‌تواند برداشت ناقص ایجاد کند.',
  },
  bizdev: {
    title: 'تحلیل کسب‌وکار',
    purpose: 'ورودی سریع به تحلیل KPI، بازار، SWOT و تصمیم‌های توسعه کسب‌وکار با تفکیک داده عمومی و داخلی.',
    inputs: ['داده شرکت انتخاب‌شده', 'داده داخلی در صورت نیاز ماژول', 'هدف تصمیم کسب‌وکار'],
    terms: ['kpi', 'revenue', 'variance', 'insight', 'action'],
    output: 'از KPI برای تشخیص وضعیت و از ماژول تخصصی برای علت و اقدام استفاده کنید.',
    caution: 'شاخص‌های مشتری/CRM معمولاً از منابع بورسی عمومی قابل استخراج نیستند و نیاز به داده داخلی دارند.',
  },
};

function resolveGuideKey(pathname: string, paramKey?: string | string[]) {
  if (pathname === '/module') return typeof paramKey === 'string' ? paramKey : '';
  if (pathname.startsWith('/stock/')) return 'market';
  const routes: Record<string, string> = {
    '/market': 'market',
    '/kiasha': 'kiasha',
    '/portfolio': 'portfolio',
    '/orders': 'orders',
    '/data-connect': 'data-connect',
    '/data': 'data',
    '/bizdev': 'bizdev',
  };
  return routes[pathname] ?? '';
}

export function ModuleHelpOverlay() {
  const pathname = usePathname();
  const params = useGlobalSearchParams<{ key?: string }>();
  const scheme = useColorScheme() === 'dark' ? 'dark' : 'light';
  const colors = Colors[scheme];
  const [visible, setVisible] = useState(false);
  const guideKey = resolveGuideKey(pathname, params.key);
  const guide = GUIDES[guideKey];
  const terms = useMemo(() => guide?.terms.map((key) => GLOSSARY[key]).filter(Boolean) ?? [], [guide]);

  if (!guide) return null;

  return (
    <>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`راهنمای ${guide.title}`}
        onPress={() => setVisible(true)}
        style={({ pressed }) => [styles.helpButton, { opacity: pressed ? 0.78 : 1 }]}
      >
        <Text style={styles.helpButtonText}>؟ راهنما</Text>
      </Pressable>

      <Modal visible={visible} transparent animationType="slide" onRequestClose={() => setVisible(false)}>
        <View style={styles.modalRoot}>
          <Pressable style={StyleSheet.absoluteFill} onPress={() => setVisible(false)} />
          <View style={[styles.sheet, { backgroundColor: colors.background }]}>
            <View style={styles.sheetHandle} />
            <View style={styles.sheetHeader}>
              <Pressable onPress={() => setVisible(false)} style={[styles.closeButton, { backgroundColor: colors.backgroundElement }]}>
                <Text style={[styles.closeText, { color: colors.text }]}>×</Text>
              </Pressable>
              <View style={styles.headerCopy}>
                <Text style={[styles.eyebrow, { color: Brand.primary }]}>راهنمای داخل ماژول</Text>
                <Text style={[styles.title, { color: colors.text }]}>{guide.title}</Text>
              </View>
            </View>

            <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
              <View style={[styles.section, { backgroundColor: colors.backgroundElement }]}>
                <Text style={[styles.sectionTitle, { color: colors.text }]}>این ماژول چه کاری می‌کند؟</Text>
                <Text style={[styles.body, { color: colors.textSecondary }]}>{guide.purpose}</Text>
              </View>

              <View style={[styles.section, { backgroundColor: colors.backgroundElement }]}>
                <Text style={[styles.sectionTitle, { color: colors.text }]}>ورودی و منبع داده</Text>
                {guide.inputs.map((item) => (
                  <View key={item} style={styles.bulletRow}>
                    <Text style={[styles.body, styles.bulletText, { color: colors.textSecondary }]}>{item}</Text>
                    <View style={[styles.dot, { backgroundColor: Brand.primary }]} />
                  </View>
                ))}
              </View>

              <Text style={[styles.blockTitle, { color: colors.text }]}>معنی مولفه‌ها و شاخص‌ها</Text>
              {terms.map((term) => (
                <View key={term.label} style={[styles.termCard, { backgroundColor: colors.backgroundElement }]}>
                  <Text style={[styles.termLabel, { color: colors.text }]}>{term.label}</Text>
                  <Text style={[styles.body, { color: colors.textSecondary }]}>{term.description}</Text>
                  {term.reading ? (
                    <View style={[styles.readBox, { borderColor: Brand.primary + '55' }]}>
                      <Text style={[styles.readTitle, { color: Brand.primary }]}>چطور بخوانیم؟</Text>
                      <Text style={[styles.readText, { color: colors.textSecondary }]}>{term.reading}</Text>
                    </View>
                  ) : null}
                </View>
              ))}

              <View style={[styles.section, { backgroundColor: colors.backgroundElement }]}>
                <Text style={[styles.sectionTitle, { color: colors.text }]}>خروجی را چطور استفاده کنیم؟</Text>
                <Text style={[styles.body, { color: colors.textSecondary }]}>{guide.output}</Text>
              </View>

              <View style={[styles.caution, { borderColor: Brand.warning + '66' }]}>
                <Text style={[styles.cautionTitle, { color: Brand.warning }]}>محدودیت مهم</Text>
                <Text style={[styles.body, { color: colors.textSecondary }]}>{guide.caution}</Text>
                <Text style={[styles.realNote, { color: Brand.positive }]}>Real Mode: فقط داده واقعی متصل؛ مقدار ناموجود ساخته نمی‌شود.</Text>
              </View>
            </ScrollView>
          </View>
        </View>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  helpButton: {
    position: 'absolute',
    left: 14,
    bottom: BottomTabInset + 12,
    zIndex: 999,
    elevation: 12,
    backgroundColor: Brand.primary,
    borderRadius: 18,
    paddingHorizontal: 12,
    paddingVertical: 8,
    shadowColor: '#000',
    shadowOpacity: 0.18,
    shadowRadius: 7,
    shadowOffset: { width: 0, height: 3 },
  },
  helpButtonText: { color: '#fff', fontFamily: Fonts.sans, fontSize: 11.5, fontWeight: '900' },
  modalRoot: { flex: 1, justifyContent: 'flex-end', backgroundColor: '#0008' },
  sheet: { maxHeight: '88%', borderTopLeftRadius: 24, borderTopRightRadius: 24, paddingTop: 8, overflow: 'hidden' },
  sheetHandle: { alignSelf: 'center', width: 44, height: 4, borderRadius: 2, backgroundColor: '#94a3b8', opacity: 0.5, marginBottom: 8 },
  sheetHeader: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: Spacing.three, paddingBottom: Spacing.three },
  headerCopy: { flex: 1, alignItems: 'flex-end' },
  eyebrow: { fontFamily: Fonts.sans, fontSize: 10, fontWeight: '900' },
  title: { fontFamily: Fonts.sans, fontSize: 20, fontWeight: '900', textAlign: 'right', marginTop: 2 },
  closeButton: { width: 38, height: 38, borderRadius: 19, alignItems: 'center', justifyContent: 'center', marginRight: Spacing.two },
  closeText: { fontSize: 25, lineHeight: 27 },
  scrollContent: { paddingHorizontal: Spacing.three, paddingBottom: 34 },
  section: { borderRadius: Radius.md, padding: Spacing.three, marginBottom: Spacing.three },
  sectionTitle: { fontFamily: Fonts.sans, fontSize: 14, fontWeight: '900', textAlign: 'right', marginBottom: 7 },
  blockTitle: { fontFamily: Fonts.sans, fontSize: 15, fontWeight: '900', textAlign: 'right', marginBottom: Spacing.two },
  body: { fontFamily: Fonts.sans, fontSize: 12, lineHeight: 21, textAlign: 'right' },
  bulletRow: { flexDirection: 'row-reverse', alignItems: 'flex-start', gap: 8, marginTop: 5 },
  bulletText: { flex: 1 },
  dot: { width: 6, height: 6, borderRadius: 3, marginTop: 8 },
  termCard: { borderRadius: Radius.md, padding: Spacing.three, marginBottom: Spacing.two },
  termLabel: { fontFamily: Fonts.sans, fontSize: 13.5, fontWeight: '900', textAlign: 'right', marginBottom: 5 },
  readBox: { borderRightWidth: 2, paddingRight: 9, marginTop: 9 },
  readTitle: { fontFamily: Fonts.sans, fontSize: 10.5, fontWeight: '900', textAlign: 'right' },
  readText: { fontFamily: Fonts.sans, fontSize: 11, lineHeight: 19, textAlign: 'right', marginTop: 2 },
  caution: { borderWidth: 1, borderRadius: Radius.md, padding: Spacing.three, marginBottom: Spacing.three },
  cautionTitle: { fontFamily: Fonts.sans, fontSize: 12.5, fontWeight: '900', textAlign: 'right', marginBottom: 5 },
  realNote: { fontFamily: Fonts.sans, fontSize: 10.5, fontWeight: '800', textAlign: 'right', marginTop: 8, lineHeight: 18 },
});
