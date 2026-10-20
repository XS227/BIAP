// Country picker policy. The country list itself comes from the server (/global/countries);
// this only orders it and hides entries. To bring JP/AU back, set HIDE_JP_AU to false.
export const HIDE_JP_AU = true;

export const PICKER_ORDER = ['US', 'GB', 'IT', 'SE', 'NO', 'DE', 'FR', 'NL', 'FI', 'ES'];
const HIDDEN_WHEN_SWITCHED = ['JP', 'AU'];

/** Server rows may carry `hidden: true` or `enabled: false`; honoured when present. */
type PickerRow = { country: string; hidden?: boolean; enabled?: boolean };

export function pickerCountries<T extends PickerRow>(countries: T[]): T[] {
  const rank = new Map(PICKER_ORDER.map((code, index) => [code, index]));
  return countries
    .filter((c) => rank.has(c.country) || (!HIDE_JP_AU && HIDDEN_WHEN_SWITCHED.includes(c.country)))
    .filter((c) => c.hidden !== true && c.enabled !== false)
    .sort((a, b) => (rank.get(a.country) ?? 99) - (rank.get(b.country) ?? 99));
}
