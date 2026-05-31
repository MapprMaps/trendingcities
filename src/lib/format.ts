/** Full precision for tables: $540,250 */
export function usd(n: number): string {
  return '$' + n.toLocaleString('en-US');
}

/** Abbreviated for tight UI: $540k, $1.57M */
export function usdShort(n: number): string {
  if (n >= 1_000_000) {
    const m = n / 1_000_000;
    return '$' + (m >= 10 ? m.toFixed(1) : m.toFixed(2)).replace(/\.0+$/, '') + 'M';
  }
  if (n >= 1_000) return '$' + Math.round(n / 1000) + 'k';
  return '$' + n;
}

/** Signed percentage with one decimal: +4.1%, −3.2% (uses a real minus glyph). */
export function pct(n: number): string {
  const sign = n > 0 ? '+' : n < 0 ? '−' : '';
  return sign + Math.abs(n).toFixed(1) + '%';
}
