// "My repairs": the jobs started from this browser, kept in localStorage only. The server never lists jobs, so one
// visitor can't browse another's photos; a job id works like a private link.

export interface HistoryEntry {
  id: string;
  createdAt: string;
  title: string;
  sample?: string;
  state?: "running" | "done" | "failed";
  size?: string;
  rebuilt?: boolean;
}

const KEY = "reforge.history.v1";
const LIMIT = 30;

export function readHistory(): HistoryEntry[] {
  try {
    const raw = window.localStorage.getItem(KEY);
    const list = raw ? (JSON.parse(raw) as HistoryEntry[]) : [];
    return Array.isArray(list) ? list.filter((e) => typeof e?.id === "string" && /^[a-f0-9]{12}$/.test(e.id)) : [];
  } catch {
    return [];
  }
}

function write(list: HistoryEntry[]): void {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(list.slice(0, LIMIT)));
    window.dispatchEvent(new Event("reforge-history"));
  } catch {
    // storage blocked (private mode): history is a convenience, the app works without it
  }
}

export function remember(entry: HistoryEntry): void {
  const list = readHistory().filter((e) => e.id !== entry.id);
  write([entry, ...list]);
}

export function update(id: string, patch: Partial<HistoryEntry>): void {
  const list = readHistory();
  const i = list.findIndex((e) => e.id === id);
  if (i < 0) return;
  list[i] = { ...list[i], ...patch };
  write(list);
}

export function forget(id: string): void {
  write(readHistory().filter((e) => e.id !== id));
}
