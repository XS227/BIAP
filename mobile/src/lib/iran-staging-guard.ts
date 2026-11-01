/** New Iran company endpoints must never fall back to the production Kiasha API. */
export function assertIranCheckpointStagingBase(raw: string | undefined): string {
  if (!raw || !raw.trim()) throw new Error('Iran checkpoint staging API is not configured.');
  let url: URL;
  try { url = new URL(raw.trim()); }
  catch { throw new Error('Iran checkpoint staging API URL is invalid.'); }
  const host = url.hostname.toLowerCase();
  const isStaging = /(^|[.-])(staging|sandbox|dev)([.-]|$)/.test(host);
  const isIp = /^[\d.]+$/.test(host) || host.includes(':');
  if (url.protocol !== 'https:' || !isStaging || isIp || !host.includes('.') ||
      url.username || url.password || url.search || url.hash) {
    throw new Error('Iran checkpoint requires an explicit isolated HTTPS staging hostname.');
  }
  return url.origin + url.pathname.replace(/\/$/, '');
}
