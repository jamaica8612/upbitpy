export function fmtKrw(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "-";
  return `${v.toLocaleString("ko-KR", { maximumFractionDigits: digits })}원`;
}

export function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "-";
  return v.toLocaleString("ko-KR", { maximumFractionDigits: digits });
}

export function fmtPct(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "-";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(digits)}%`;
}

/** UTC ISO string -> KST display */
export function fmtKst(iso: string | null | undefined, withSeconds = false): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return d.toLocaleString("ko-KR", {
    timeZone: "Asia/Seoul",
    year: "2-digit",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    ...(withSeconds ? { second: "2-digit" } : {}),
    hour12: false,
  });
}

export function holdDuration(bars: number, timeframe: string): string {
  const minutes: Record<string, number> = {
    "1m": 1, "3m": 3, "5m": 5, "10m": 10, "15m": 15, "30m": 30, "60m": 60, "240m": 240, "1d": 1440,
  };
  const total = bars * (minutes[timeframe] ?? 5);
  if (total < 60) return `${total}분`;
  if (total < 1440) return `${Math.floor(total / 60)}시간 ${total % 60}분`;
  return `${Math.floor(total / 1440)}일 ${Math.floor((total % 1440) / 60)}시간`;
}

export function downloadCsv(filename: string, rows: Record<string, unknown>[]): void {
  if (!rows.length) return;
  const headers = Object.keys(rows[0]);
  const escape = (v: unknown) => {
    const s = v === null || v === undefined ? "" : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const csv = [headers.join(","), ...rows.map((r) => headers.map((h) => escape(r[h])).join(","))].join("\n");
  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function downloadJson(filename: string, data: unknown): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
