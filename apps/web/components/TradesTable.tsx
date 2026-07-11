"use client";

import { useMemo, useState } from "react";
import type { Trade } from "@/lib/api";
import { downloadCsv, fmtKrw, fmtKst, fmtPct, holdDuration } from "@/lib/format";
import { Badge, Button } from "@/components/ui";
import { exitReasonKo } from "@/components/CandleChart";

type Filter = "all" | "win" | "loss";

export function TradesTable({ trades, market, timeframe }: {
  trades: Trade[]; market: string; timeframe: string;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const [reason, setReason] = useState<string>("all");
  const [sortKey, setSortKey] = useState<keyof Trade>("entry_ts");
  const [sortDesc, setSortDesc] = useState(false);

  const reasons = useMemo(
    () => Array.from(new Set(trades.map((t) => t.exit_reason).filter(Boolean))) as string[],
    [trades],
  );

  const rows = useMemo(() => {
    let out = trades.filter((t) => t.exit_price !== null);
    if (filter === "win") out = out.filter((t) => (t.pnl_krw ?? 0) > 0);
    if (filter === "loss") out = out.filter((t) => (t.pnl_krw ?? 0) <= 0);
    if (reason !== "all") out = out.filter((t) => t.exit_reason === reason);
    out = [...out].sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey];
      const cmp = av === null ? -1 : bv === null ? 1 : av < bv ? -1 : av > bv ? 1 : 0;
      return sortDesc ? -cmp : cmp;
    });
    return out;
  }, [trades, filter, reason, sortKey, sortDesc]);

  const exportCsv = () =>
    downloadCsv(
      `trades_${market}_${timeframe}.csv`,
      rows.map((t, i) => ({
        번호: i + 1, 종목: market, 진입시각KST: fmtKst(t.entry_ts, true), 진입가: t.entry_price,
        매수금액: t.invested_krw, 수량: t.quantity, 청산시각KST: fmtKst(t.exit_ts, true),
        청산가: t.exit_price, 청산사유: exitReasonKo(t.exit_reason), 보유봉수: t.hold_bars,
        총수익률pct: t.gross_return_pct, 순수익률pct: t.return_pct, 순손익: t.pnl_krw,
        수수료: t.entry_fee + t.exit_fee, MFEpct: t.mfe_pct, MAEpct: t.mae_pct,
        강제청산: t.forced_exit, 판정불가: t.ambiguous,
      })),
    );

  const header = (label: string, key: keyof Trade) => (
    <th
      className="px-2 py-1.5 text-left cursor-pointer hover:text-fg whitespace-nowrap"
      onClick={() => {
        if (sortKey === key) setSortDesc(!sortDesc);
        else { setSortKey(key); setSortDesc(true); }
      }}
    >
      {label} {sortKey === key ? (sortDesc ? "▼" : "▲") : ""}
    </th>
  );

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 mb-2">
        {(["all", "win", "loss"] as Filter[]).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-2 py-1 rounded text-xs ${filter === f ? "bg-accent text-black" : "bg-panel-2 text-muted"}`}
          >
            {f === "all" ? "전체" : f === "win" ? "수익 거래" : "손실 거래"}
          </button>
        ))}
        <select
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          className="bg-panel-2 border border-line rounded px-2 py-1 text-xs"
        >
          <option value="all">청산 사유: 전체</option>
          {reasons.map((r) => (
            <option key={r} value={r}>{exitReasonKo(r)}</option>
          ))}
        </select>
        <span className="text-xs text-muted">{rows.length}건</span>
        <div className="ml-auto">
          <Button variant="ghost" onClick={exportCsv}>CSV 내보내기</Button>
        </div>
      </div>
      <div className="overflow-x-auto max-h-96 overflow-y-auto border border-line rounded-md">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-panel-2 text-muted">
            <tr>
              <th className="px-2 py-1.5 text-left">#</th>
              {header("진입 시각", "entry_ts")}
              {header("진입가", "entry_price")}
              {header("매수금액", "invested_krw")}
              {header("청산 시각", "exit_ts")}
              {header("청산가", "exit_price")}
              <th className="px-2 py-1.5 text-left">사유</th>
              {header("보유", "hold_bars")}
              {header("순수익률", "return_pct")}
              {header("순손익", "pnl_krw")}
              {header("MFE", "mfe_pct")}
              {header("MAE", "mae_pct")}
            </tr>
          </thead>
          <tbody>
            {rows.map((t, i) => (
              <tr key={i} className="border-t border-line hover:bg-panel-2">
                <td className="px-2 py-1">{i + 1}</td>
                <td className="px-2 py-1 whitespace-nowrap">{fmtKst(t.entry_ts)}</td>
                <td className="px-2 py-1">{fmtKrw(t.entry_price, 2)}</td>
                <td className="px-2 py-1">{fmtKrw(t.invested_krw)}</td>
                <td className="px-2 py-1 whitespace-nowrap">{fmtKst(t.exit_ts)}</td>
                <td className="px-2 py-1">{t.exit_price ? fmtKrw(t.exit_price, 2) : "-"}</td>
                <td className="px-2 py-1">
                  <Badge tone={t.exit_reason === "take_profit" ? "up" : t.exit_reason === "stop_loss" ? "down" : "neutral"}>
                    {exitReasonKo(t.exit_reason)}
                  </Badge>
                  {t.forced_exit && <Badge tone="warn">강제</Badge>}
                </td>
                <td className="px-2 py-1 whitespace-nowrap">{holdDuration(t.hold_bars, timeframe)}</td>
                <td className={`px-2 py-1 font-semibold ${(t.return_pct ?? 0) > 0 ? "text-up" : "text-down"}`}>
                  {fmtPct(t.return_pct)}
                </td>
                <td className={`px-2 py-1 ${(t.pnl_krw ?? 0) > 0 ? "text-up" : "text-down"}`}>{fmtKrw(t.pnl_krw)}</td>
                <td className="px-2 py-1 text-up">{fmtPct(t.mfe_pct, 1)}</td>
                <td className="px-2 py-1 text-down">{fmtPct(t.mae_pct, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
