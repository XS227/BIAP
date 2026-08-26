// Tehran Stock Exchange hours: Sun–Thu 09:00–12:30 IRST (UTC+3:30)
export function isMarketOpen(): boolean {
  const now = new Date();
  // Convert to IRST
  const irst = new Date(now.getTime() + (3.5 * 60 * 60 * 1000));
  const day = irst.getUTCDay(); // 0=Sun 1=Mon … 4=Thu 5=Fri 6=Sat
  const h = irst.getUTCHours();
  const m = irst.getUTCMinutes();
  const minutes = h * 60 + m;

  const isWeekday = day >= 0 && day <= 4; // Sun–Thu
  const inSession = minutes >= 9 * 60 && minutes < 12 * 60 + 30;

  return isWeekday && inSession;
}

export function marketStatusLabel(): { open: boolean; label: string } {
  const open = isMarketOpen();
  return {
    open,
    label: open ? 'بازار باز است' : 'بازار بسته است',
  };
}
