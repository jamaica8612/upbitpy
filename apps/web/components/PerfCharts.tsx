"use client";

import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import type { BacktestResult } from "@/lib/api";
import { fmtKrw, fmtPct } from "@/lib/format";

const AXIS = { stroke: "#8b94a7", fontSize: 11 };
const GRID = { stroke: "#1a1f2b" };
const TOOLTIP_STYLE = {
  contentStyle: { background: "#1a1f2b", border: "1px solid #232a3a", borderRadius: 8, fontSize: 12 },
  labelStyle: { color: "#8b94a7" },
};

function sample<T>(arr: T[], max = 1500): T[] {
  if (arr.length <= max) return arr;
  const step = Math.ceil(arr.length / max);
  return arr.filter((_, i) => i % step === 0);
}

export function EquityChart({ result }: { result: BacktestResult }) {
  const data = sample(
    result.timestamps.map((ts, i) => ({
      ts: ts.slice(5, 16).replace("T", " "),
      전략: result.equity_curve[i],
      "매수 후 보유": result.buy_hold_curve[i],
    })),
  );
  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="ts" {...AXIS} minTickGap={60} />
        <YAxis {...AXIS} tickFormatter={(v) => `${(v / 10_000).toFixed(0)}만`} width={52} />
        <Tooltip {...TOOLTIP_STYLE} formatter={(v) => fmtKrw(Number(v))} />
        <Line type="monotone" dataKey="전략" stroke="#ffb800" dot={false} strokeWidth={1.5} />
        <Line type="monotone" dataKey="매수 후 보유" stroke="#8b94a7" dot={false} strokeWidth={1} strokeDasharray="4 3" />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function DrawdownChart({ result }: { result: BacktestResult }) {
  const dd = result.metrics.drawdown_curve;
  const data = sample(
    result.timestamps.map((ts, i) => ({ ts: ts.slice(5, 16).replace("T", " "), dd: dd[i] })),
  );
  return (
    <ResponsiveContainer width="100%" height={140}>
      <AreaChart data={data}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="ts" {...AXIS} minTickGap={60} />
        <YAxis {...AXIS} tickFormatter={(v) => `${v}%`} width={44} />
        <Tooltip {...TOOLTIP_STYLE} formatter={(v) => fmtPct(Number(v))} />
        <Area type="monotone" dataKey="dd" stroke="#3182f6" fill="#3182f622" name="낙폭" />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function PnlDistribution({ result }: { result: BacktestResult }) {
  const rets = result.trades.filter((t) => t.return_pct !== null).map((t) => t.return_pct as number);
  if (!rets.length) return <div className="text-muted text-sm">거래 없음</div>;
  const min = Math.min(...rets), max = Math.max(...rets);
  const bins = 21;
  const width = (max - min) / bins || 1;
  const hist = Array.from({ length: bins }, (_, i) => ({
    range: `${(min + i * width).toFixed(1)}`,
    count: rets.filter((r) => r >= min + i * width && r < min + (i + 1) * width + (i === bins - 1 ? 1e-9 : 0)).length,
    positive: min + (i + 0.5) * width > 0,
  }));
  return (
    <ResponsiveContainer width="100%" height={160}>
      <BarChart data={hist}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="range" {...AXIS} minTickGap={30} />
        <YAxis {...AXIS} allowDecimals={false} width={30} />
        <Tooltip {...TOOLTIP_STYLE} />
        <Bar dataKey="count" name="거래 수">
          {hist.map((h, i) => (
            <Cell key={i} fill={h.positive ? "#f04452" : "#3182f6"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function MonthlyPnl({ monthly }: { monthly: Record<string, number> }) {
  const data = Object.entries(monthly).sort(([a], [b]) => a.localeCompare(b))
    .map(([m, v]) => ({ month: m, pnl: v }));
  if (!data.length) return <div className="text-muted text-sm">데이터 없음</div>;
  return (
    <ResponsiveContainer width="100%" height={160}>
      <BarChart data={data}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey="month" {...AXIS} />
        <YAxis {...AXIS} tickFormatter={(v) => `${(v / 10_000).toFixed(0)}만`} width={48} />
        <Tooltip {...TOOLTIP_STYLE} formatter={(v) => fmtKrw(Number(v))} />
        <Bar dataKey="pnl" name="월 손익">
          {data.map((d, i) => (
            <Cell key={i} fill={d.pnl >= 0 ? "#f04452" : "#3182f6"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
