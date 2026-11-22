/** Global indicative paper ticket — never transmits or executes an order. */
export type GlobalBrokerId = 'ibkr' | 'saxo' | 'alpaca';
export type PaperSide = 'BUY' | 'SELL';
export type PaperTicketInput = {
  brokerId: GlobalBrokerId;
  side: PaperSide;
  country: string;
  exchange: string;
  micCode?: string | null;
  currency: string;
  ticker: string;
  quantity: string;
  limitPrice: string;
  lotSize?: number | null;
};
export type PaperDraftFields = {
  brokerId: GlobalBrokerId;
  side: PaperSide;
  country: string;
  exchange: string;
  micCode: string | null;
  currency: string;
  ticker: string;
  quantity: number;
  indicativeLimitPrice: number;
  indicativeNotional: number;
};
export type PaperDraft = PaperDraftFields & {
  id: string;
  createdAt: string;
  status: 'DRAFT_ONLY';
  note: 'NOT_SUBMITTED';
};
export type TicketValidation =
  | { ok: true; value: PaperDraftFields }
  | { ok: false; error: string };

/** No live quotes, OAuth tokens, broker APIs or order endpoints. */
export function validatePaperTicket(input: PaperTicketInput): TicketValidation {
  const country = input.country.trim().toUpperCase();
  const exchange = input.exchange.trim().toUpperCase();
  const currency = input.currency.trim().toUpperCase();
  const ticker = input.ticker.trim().toUpperCase();
  const micCode = input.micCode?.trim().toUpperCase() || null;
  if (!/^[A-Z]{2}$/.test(country) || !exchange || !/^[A-Z]{3}$/.test(currency)) {
    return { ok: false, error: 'Select a valid country, exchange and currency.' };
  }
  if (!['ibkr', 'saxo', 'alpaca'].includes(input.brokerId)) {
    return { ok: false, error: 'Select a prospective broker.' };
  }
  if (input.brokerId === 'alpaca' && country !== 'US') {
    return { ok: false, error: 'Alpaca is scoped to US equities in this pilot.' };
  }
  if (input.side !== 'BUY' && input.side !== 'SELL') {
    return { ok: false, error: 'Select BUY or SELL.' };
  }
  if (!/^[A-Z0-9][A-Z0-9.^-]{0,15}$/.test(ticker)) {
    return { ok: false, error: 'Enter a valid listed equity symbol.' };
  }
  if (!/^[0-9]{1,6}$/.test(input.quantity.trim())) {
    return { ok: false, error: 'Quantity must be a whole number between 1 and 100,000.' };
  }
  const quantity = Number(input.quantity);
  if (!Number.isSafeInteger(quantity) || quantity <= 0 || quantity > 100000) {
    return { ok: false, error: 'Quantity must be a whole number between 1 and 100,000.' };
  }
  if (input.lotSize != null && input.lotSize > 1 && quantity % input.lotSize !== 0) {
    return { ok: false, error: 'Quantity must be divisible by the known lot size.' };
  }
  if (!/^[0-9]{1,7}(?:\.[0-9]{1,6})?$/.test(input.limitPrice.trim())) {
    return { ok: false, error: 'Enter a positive indicative limit price (up to 6 decimal places).' };
  }
  const indicativeLimitPrice = Number(input.limitPrice);
  const indicativeNotional = quantity * indicativeLimitPrice;
  if (!Number.isFinite(indicativeNotional) || indicativeLimitPrice <= 0 ||
      indicativeLimitPrice > 1000000 || indicativeNotional > 10000000000) {
    return { ok: false, error: 'Indicative price or notional outside research limits.' };
  }
  return { ok: true, value: {
    brokerId: input.brokerId, side: input.side, country, exchange,
    micCode, currency, ticker, quantity, indicativeLimitPrice, indicativeNotional,
  } };
}

export function paperTicketLabel(value: PaperDraftFields): string {
  return value.side + ' ' + value.quantity + ' × ' + value.ticker + ' on ' +
    value.exchange + ' · ' + value.currency + ' ' +
    value.indicativeNotional.toLocaleString('en-US', { maximumFractionDigits: 2 }) +
    ' indicative (fees, taxes, FX and spread excluded)';
}

/** An unsent draft must never masquerade as a fill, holding or live order. */
export function isPaperDraft(value: unknown): value is PaperDraft {
  if (!value || typeof value !== 'object') return false;
  const v = value as Partial<PaperDraft>;
  return v.status === 'DRAFT_ONLY' && v.note === 'NOT_SUBMITTED' &&
    typeof v.id === 'string' && typeof v.createdAt === 'string' &&
    typeof v.ticker === 'string' && typeof v.country === 'string' &&
    typeof v.currency === 'string' && (v.side === 'BUY' || v.side === 'SELL') &&
    (v.brokerId === 'ibkr' || v.brokerId === 'saxo' || v.brokerId === 'alpaca') &&
    Number.isSafeInteger(Number(v.quantity)) && Number(v.quantity) > 0 &&
    Number.isFinite(Number(v.indicativeLimitPrice)) && Number(v.indicativeLimitPrice) > 0 &&
    Number.isFinite(Number(v.indicativeNotional)) && Number(v.indicativeNotional) > 0;
}
