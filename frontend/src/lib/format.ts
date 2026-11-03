export const fmt = (value: number | null | undefined, digits = 2): string =>
  value === null || value === undefined || Number.isNaN(value) ? "—" : value.toFixed(digits);

/** "±0.43" with a precision that matches the uncertainty itself. */
export function pm(u: number | null | undefined): string {
  if (u === null || u === undefined || Number.isNaN(u)) return "";
  return `±${u < 0.1 ? u.toFixed(2) : u < 1 ? u.toFixed(2) : u.toFixed(1)}`;
}

export function seconds(s: number | null | undefined): string {
  if (s === null || s === undefined) return "";
  return s < 10 ? `${s.toFixed(1)} s` : `${Math.round(s)} s`;
}

export function when(iso: string | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function sentence(text: string): string {
  const t = text.trim();
  return t ? t[0].toUpperCase() + t.slice(1) : t;
}
