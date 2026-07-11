"use client";

import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  createChart,
  createSeriesMarkers,
  IChartApi,
  Time,
} from "lightweight-charts";
import type { Candle, Trade } from "@/lib/api";
import { fmtKst, fmtKrw, fmtPct } from "@/lib/format";

export function CandleChart({ candles, trades, timeframe }: {
  candles: Candle[];
  trades: Trade[];
  timeframe: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [selected, setSelected] = useState<Trade | null>(null);

  useEffect(() => {
    if (!ref.current || !candles.length) return;
    const chart = createChart(ref.current, {
      layout: { background: { color: "#12161f" }, textColor: "#8b94a7" },
      grid: { vertLines: { color: "#1a1f2b" }, horzLines: { color: "#1a1f2b" } },
      timeScale: { timeVisible: true, borderColor: "#232a3a" },
      rightPriceScale: { borderColor: "#232a3a" },
      autoSize: true,
      localization: {
        timeFormatter: (t: Time) =>
          new Date((t as number) * 1000).toLocaleString("ko-KR", {
            timeZone: "Asia/Seoul", month: "2-digit", day: "2-digit",
            hour: "2-digit", minute: "2-digit", hour12: false,
          }),
      },
    });
    chartRef.current = chart;

    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#f04452", downColor: "#3182f6",
      borderUpColor: "#f04452", borderDownColor: "#3182f6",
      wickUpColor: "#f04452", wickDownColor: "#3182f6",
    });
    series.setData(
      candles.map((c) => ({
        time: c.time as Time, open: c.open, high: c.high, low: c.low, close: c.close,
      })),
    );

    // entry/exit markers; clicking near a marker opens the trade detail
    const byEntryTime = new Map<number, Trade>();
    const markers = trades.flatMap((t) => {
      const entryTime = candles[t.entry_index]?.time;
      const out = [];
      if (entryTime !== undefined) {
        byEntryTime.set(entryTime, t);
        out.push({
          time: entryTime as Time, position: "belowBar" as const,
          color: "#f04452", shape: "arrowUp" as const, text: "매수",
        });
      }
      if (t.exit_index !== null && candles[t.exit_index]) {
        out.push({
          time: candles[t.exit_index].time as Time, position: "aboveBar" as const,
          color: "#3182f6", shape: "arrowDown" as const,
          text: t.exit_reason === "stop_loss" ? "손절" : t.exit_reason === "take_profit" ? "익절" : "매도",
        });
      }
      return out;
    });
    createSeriesMarkers(series, markers);

    chart.subscribeClick((param) => {
      if (param.time === undefined) return;
      const t = byEntryTime.get(param.time as number);
      if (t) setSelected(t);
      else {
        // also match exits and nearby entries
        const clicked = param.time as number;
        const near = trades.find(
          (tr) =>
            (tr.exit_index !== null && candles[tr.exit_index]?.time === clicked) ||
            candles[tr.entry_index]?.time === clicked,
        );
        if (near) setSelected(near);
      }
    });

    chart.timeScale().fitContent();
    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [candles, trades]);

  return (
    <div className="relative">
      <div ref={ref} className="w-full h-[420px]" />
      {selected && (
        <div className="absolute top-2 left-2 z-10 bg-panel-2 border border-line rounded-lg p-3 text-xs space-y-1 w-64 shadow-xl">
          <div className="flex justify-between items-center">
            <span className="font-semibold text-sm">거래 상세</span>
            <button className="text-muted hover:text-fg" onClick={() => setSelected(null)}>✕</button>
          </div>
          <Row k="진입 시각" v={fmtKst(selected.entry_ts)} />
          <Row k="진입가" v={fmtKrw(selected.entry_price, 2)} />
          <Row k="청산 시각" v={fmtKst(selected.exit_ts)} />
          <Row k="청산가" v={selected.exit_price ? fmtKrw(selected.exit_price, 2) : "-"} />
          <Row k="보유" v={`${selected.hold_bars}봉 (${timeframe})`} />
          <Row k="수익률" v={fmtPct(selected.return_pct)}
               tone={(selected.return_pct ?? 0) > 0 ? "up" : "down"} />
          <Row k="손익" v={fmtKrw(selected.pnl_krw)} />
          <Row k="수수료" v={fmtKrw(selected.entry_fee + selected.exit_fee)} />
          <Row k="청산 사유" v={exitReasonKo(selected.exit_reason)} />
          {Object.keys(selected.entry_snapshot ?? {}).length > 0 && (
            <details className="pt-1">
              <summary className="text-muted cursor-pointer">진입 당시 지표값</summary>
              <div className="mt-1 max-h-32 overflow-auto space-y-0.5">
                {Object.entries(selected.entry_snapshot).map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-2">
                    <span className="text-muted truncate">{k}</span>
                    <span>{v.toLocaleString("ko-KR", { maximumFractionDigits: 4 })}</span>
                  </div>
                ))}
              </div>
            </details>
          )}
        </div>
      )}
    </div>
  );
}

function Row({ k, v, tone }: { k: string; v: string; tone?: "up" | "down" }) {
  return (
    <div className="flex justify-between">
      <span className="text-muted">{k}</span>
      <span className={tone === "up" ? "text-up" : tone === "down" ? "text-down" : ""}>{v}</span>
    </div>
  );
}

export function exitReasonKo(reason: string | null): string {
  const map: Record<string, string> = {
    signal: "지표 신호", stop_loss: "손절", take_profit: "익절",
    max_hold: "최대 보유기간", end_of_data: "기간 종료 강제청산",
  };
  return reason ? (map[reason] ?? reason) : "-";
}
