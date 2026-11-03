/** Persian rendering of the English reasoning strings the agents store (clauses separated by "; "). Unknown clauses are hidden, never shown raw. */
const RULES: Array<[RegExp, (m: RegExpMatchArray) => string]> = [
  [/^no CODAL fundamentals connected yet$/i, () => 'صورت مالی کدال متصل نشده است'],
  [/^CODAL financials connected; audit opinion unavailable$/i, () => 'صورت مالی کدال موجود است؛ نظر حسابرس موجود نیست'],
  [/^revenue \+?(-?[\d.]+)% YoY$/i, (m) => `رشد درآمد نسبت به سال قبل ${m[1]}٪`],
  [/^net margin negative \((-?[\d.]+)%\)$/i, (m) => `حاشیه‌ی سود خالص منفی (${m[1]}٪)`],
  [/^(loss )?margin (improving|worsening|declining) \(([+-]?[\d.]+)pp\)$/i, (m) => `حاشیه‌ی سود ${/improving/i.test(m[2]) ? 'در حال بهبود' : 'در حال بدتر شدن'} (${m[3]} واحد درصد)`],
  [/^net margin unchanged$/i, () => 'حاشیه‌ی سود خالص تغییری نکرده'],
  [/^audit opinion unqualified$/i, () => 'نظر حسابرس: مقبول'],
  [/^audit opinion: (.+)$/i, (m) => `نظر حسابرس: ${m[1]}`],
  [/^(\d+) related-party flag\(s\)$/i, (m) => `${m[1]} مورد هشدار معاملات با اشخاص وابسته`],
  [/^related-party parser not yet connected$/i, () => 'بررسی معاملات با اشخاص وابسته هنوز متصل نیست'],
  [/^management flagged cost pressure$/i, () => 'مدیریت به فشار هزینه‌ها اشاره کرده است'],
  [/^(\d+)% off 52w high$/i, (m) => `${m[1]}٪ پایین‌تر از سقف ۵۲ هفته`],
  [/^only (\d+)% off 52w high$/i, (m) => `تنها ${m[1]}٪ پایین‌تر از سقف ۵۲ هفته`],
  [/^52-week range unavailable$/i, () => 'بازه‌ی ۵۲ هفته موجود نیست'],
  [/^max drawdown (-?[\d.]+)%$/i, (m) => `بیشترین افت از قله ${m[1]}٪`],
  // an annualised volatility above 300% is a data artefact, not a market fact
  [/^high annualized volatility ([\d.]+)%$/i, (m) => (Number(m[1]) > 300 ? 'نوسان سالانه: داده کافی نیست' : `نوسان سالانه‌ی بالا (${m[1]}٪)`)],
  [/^volume ([\d.]+)x 30d avg$/i, (m) => `حجم ${m[1]} برابر میانگین ۳۰ روز`],
  [/^(positive|negative) 1m\/3m momentum \(([^)]*)\)$/i, (m) => `مومنتوم ۱ و ۳ ماهه ${/positive/i.test(m[1]) ? 'مثبت' : 'منفی'} (${m[2]})`],
  [/^6m return ([+-]?[\d.]+)%$/i, (m) => `بازده ۶ ماهه ${m[1]}٪`],
  [/^(lower|upper) (\d+)% of 52w range$/i, (m) => `${/lower/i.test(m[1]) ? 'ناحیه‌ی پایین' : 'ناحیه‌ی بالا'} بازه‌ی ۵۲ هفته (${m[2]}٪)`],
  [/^(\d+)% through 52w range$/i, (m) => `${m[1]}٪ از بازه‌ی ۵۲ هفته طی شده`],
  [/^no strong momentum signal$/i, () => 'سیگنال مومنتوم قوی وجود ندارد'],
  [/^net retail inflow$/i, () => 'ورود خالص پول حقیقی'],
  [/^net retail outflow$/i, () => 'خروج خالص پول حقیقی'],
  [/^buy\/sell per-capita ([\d.]+)x$/i, (m) => `سرانه‌ی خرید به فروش ${m[1]} برابر`],
  [/^1w ([+-]?[\d.]+)%$/i, (m) => `هفته ${m[1]}٪`],
  [/^1m ([+-]?[\d.]+)%$/i, (m) => `ماه ${m[1]}٪`],
  [/^3m ([+-]?[\d.]+)%$/i, (m) => `سه‌ماهه ${m[1]}٪`],
];
const PE = /^P\/E ([\d.]+) vs sector ([\d.]+) \(([+-]?\d+)% (discount|premium)\)$/i;

export function reasoningFa(text?: string | null): string {
  const out: string[] = [];
  for (const raw of String(text ?? '').split(/;\s*/)) {
    const clause = raw.trim();
    if (!clause) continue;
    if (!/[A-Za-z]/.test(clause)) { out.push(clause); continue; } // already Persian (e.g. the scenario text)
    const pe = clause.match(PE);
    if (pe) { out.push(`P/E ${pe[1]} در برابر میانگین صنعت ${pe[2]} (${Math.abs(Number(pe[3]))}٪ ${/discount/i.test(pe[4]) ? 'تخفیف' : 'صرف'})`); continue; }
    const rule = RULES.find(([re]) => re.test(clause));
    if (rule) out.push(rule[1](clause.match(rule[0]) as RegExpMatchArray));
  }
  return out.length ? out.join('؛ ') : 'جزئیات فنی این عامل نمایش داده نمی‌شود';
}
