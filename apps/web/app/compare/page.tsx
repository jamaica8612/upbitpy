"use client";

import { useMemo, useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { api, BacktestRun } from "@/lib/api";
import { downloadCsv, fmtKst, fmtNum, fmtPct } from "@/lib/format";
import { Badge, Button, Card, Warning } from "@/components/ui";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const COLORS = ["#ffb800", "#2fbf71", "#f04452", "#3182f6", "#b07cff", "#ff8a3d"];

type SortKey = "return" | "mdd" | "sharpe" | "pf";

export default function ComparePage() {
  const runs = useQuery({ queryKey: ["backtests"], queryFn: () => api.backtests(50) });
  const [selected, setSelected] = useState<string[]>([]);
  const [sortKey, setSortKey] = useState<SortKey>("return");

  const detailQueries = useQueries({
    queries: selected.map((id) => ({
      queryKey: ["backtest", id],
      queryFn: () => api.backtest(id),
      staleTime: Infinity,
    })),
  });
  const details = detailQueries.map((q) => q.data).filter(Boolean) as BacktestRun[];

  const completed = (runs.data ?? []).filter((r) => r.status === "completed");

  const rows = useMemo(() => {
    const out = details
      .filter((d) => d.result?.metrics)
      .map((d) => ({
        id: d.id,
        name: `${d.strategy_snapshot?.name ?? d.config.template ?? "전략"} · ${d.config.market} ${d.config.timeframe}`,
        m: d.result!.metrics,
        d,
      }));
    const key = {
      return: (r: (typeof out)[0]) => -r.m.total_return_pct,
      mdd: (r: (typeof out)[0]) => -r.m.max_drawdown_pct,
      sharpe: (r: (typeof out)[0]) => -r.m.sharpe,
      pf: (r: (typeof out)[0]) => -(r.m.profit_factor ?? 0),
    }[sortKey];
    return [...out].sort((a, b) => key(a) - key(b));
  }, [details, sortKey]);

  const equityData = useMemo(() => {
    if (!details.length) return [];
    const longest = details.reduce((a, b) =>
      (a.result?.equity_curve.length ?? 0) >= (b.result?.equity_curve.length ?? 0) ? a : b);
    const n = longest.result?.equity_curve.length ?? 0;
    const step = Math.max(1, Math.floor(n / 800));
    const data = [];
    for (let i = 0; i < n; i += step) {
      const row: Record<string, number | string> = { ts: longest.result!.timestamps[i]?.slice(5, 16) ?? i };
      details.forEach((d, di) => {
        const eq = d.result?.equity_curve;
        const cap = Number((d.config.costs as { initialCapital?: number } | undefined)?.initialCapital ?? 10_000_000);
        if (eq && eq[i] !== undefined) row[`s${di}`] = ((eq[i] / cap) - 1) * 100;
      });
      data.push(row);
    }
    return data;
  }, [details]);

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold">전략 비교</h1>
      <div className="grid grid-cols-1 xl:grid-cols-[280px_1fr] gap-4">
        <Card title="완료된 백테스트 선택 (최대 6개)">
          {completed.length ? (
            <ul className="space-y-1.5 max-h-[70vh] overflow-auto">
              {completed.map((r) => {
                const checked = selected.includes(r.id);
                const metrics = (r.result as { metrics?: { total_return_pct?: number } } | null)?.metrics;
                return (
                  <li key={r.id}>
                    <label className="flex items-start gap-2 text-xs cursor-pointer hover:bg-panel-2 rounded p-1.5">
                      <input
                        type="checkbox" checked={checked}
                        onChange={() =>
                          setSelected(checked ? selected.filter((x) => x !== r.id) : [...selected, r.id].slice(0, 6))}
                      />
                      <span>
                        <span className="font-medium">{String(r.config.market)} {String(r.config.timeframe)}</span>
                        <span className="text-muted"> · {r.strategy_snapshot?.name ?? String(r.config.template ?? "")}</span>
                        <br />
                        <span className="text-muted">{fmtKst(r.created_at)}</span>
                        {metrics && (
                          <span className={`ml-1 ${(metrics.total_return_pct ?? 0) > 0 ? "text-up" : "text-down"}`}>
                            {fmtPct(metrics.total_return_pct)}
                          </span>
                        )}
                      </span>
                    </label>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="text-muted text-sm">완료된 백테스트가 없습니다. 연구소에서 먼저 실행하세요.</p>
          )}
        </Card>

        <div className="space-y-4 min-w-0">
          {rows.length > 0 && (
            <>
              <Warning>
                수익률이 가장 높은 전략이 항상 좋은 전략은 아닙니다. MDD·거래 수·초과수익·검증 구간 성과를
                함께 확인하세요.
              </Warning>
              <Card
                title="성과 비교표"
                right={
                  <div className="flex items-center gap-2">
                    <select
                      className="bg-panel-2 border border-line rounded px-2 py-1 text-xs"
                      value={sortKey} onChange={(e) => setSortKey(e.target.value as SortKey)}
                    >
                      <option value="return">수익률 높은 순</option>
                      <option value="mdd">MDD 낮은 순</option>
                      <option value="sharpe">Sharpe 높은 순</option>
                      <option value="pf">Profit Factor 높은 순</option>
                    </select>
                    <Button variant="ghost" onClick={() =>
                      downloadCsv("strategy_comparison.csv", rows.map((r) => ({
                        전략: r.name, 총수익률: r.m.total_return_pct, MDD: r.m.max_drawdown_pct,
                        Sharpe: r.m.sharpe, Sortino: r.m.sortino, ProfitFactor: r.m.profit_factor,
                        승률: r.m.win_rate_pct, 평균손익비: r.m.payoff_ratio, 거래수: r.m.trade_count,
                        수수료: r.m.total_fees_krw, 노출률: r.m.exposure_pct, 초과수익: r.m.excess_return_pct,
                      })))}>
                      CSV
                    </Button>
                  </div>
                }
              >
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead className="text-muted">
                      <tr>
                        <th className="text-left px-2 py-1.5">전략</th>
                        <th className="text-right px-2">총수익률</th>
                        <th className="text-right px-2">MDD</th>
                        <th className="text-right px-2">Sharpe</th>
                        <th className="text-right px-2">Sortino</th>
                        <th className="text-right px-2">PF</th>
                        <th className="text-right px-2">승률</th>
                        <th className="text-right px-2">손익비</th>
                        <th className="text-right px-2">거래</th>
                        <th className="text-right px-2">노출</th>
                        <th className="text-right px-2">초과수익</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((r, i) => (
                        <tr key={r.id} className="border-t border-line">
                          <td className="px-2 py-1.5">
                            <span className="inline-block w-2 h-2 rounded-full mr-1.5"
                                  style={{ background: COLORS[selected.indexOf(r.id) % COLORS.length] }} />
                            {r.name}
                            {i === 0 && <Badge tone="warn">정렬 1위</Badge>}
                          </td>
                          <td className={`text-right px-2 ${r.m.total_return_pct > 0 ? "text-up" : "text-down"}`}>
                            {fmtPct(r.m.total_return_pct)}
                          </td>
                          <td className="text-right px-2 text-down">{fmtPct(r.m.max_drawdown_pct)}</td>
                          <td className="text-right px-2">{fmtNum(r.m.sharpe)}</td>
                          <td className="text-right px-2">{fmtNum(r.m.sortino)}</td>
                          <td className="text-right px-2">{r.m.profit_factor === null ? "∞" : fmtNum(r.m.profit_factor)}</td>
                          <td className="text-right px-2">{r.m.win_rate_pct.toFixed(1)}%</td>
                          <td className="text-right px-2">{fmtNum(r.m.payoff_ratio)}</td>
                          <td className="text-right px-2">{r.m.trade_count}</td>
                          <td className="text-right px-2">{r.m.exposure_pct.toFixed(0)}%</td>
                          <td className={`text-right px-2 ${r.m.excess_return_pct > 0 ? "text-up" : "text-down"}`}>
                            {fmtPct(r.m.excess_return_pct)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>

              <Card title="수익률 곡선 비교 (%)">
                <ResponsiveContainer width="100%" height={280}>
                  <LineChart data={equityData}>
                    <CartesianGrid stroke="#1a1f2b" />
                    <XAxis dataKey="ts" stroke="#8b94a7" fontSize={11} minTickGap={60} />
                    <YAxis stroke="#8b94a7" fontSize={11} tickFormatter={(v) => `${v}%`} />
                    <Tooltip
                      contentStyle={{ background: "#1a1f2b", border: "1px solid #232a3a", borderRadius: 8, fontSize: 12 }}
                      formatter={(v, dataKey) => {
                        const idx = Number(String(dataKey).slice(1));
                        const d = details[idx];
                        return [fmtPct(Number(v)), d ? `${d.strategy_snapshot?.name ?? d.config.template}` : dataKey];
                      }}
                    />
                    {details.map((_, i) => (
                      <Line key={i} dataKey={`s${i}`} stroke={COLORS[i % COLORS.length]} dot={false} strokeWidth={1.5} />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </Card>
            </>
          )}
          {!rows.length && (
            <Card>
              <p className="text-center text-muted py-16 text-sm">좌측에서 비교할 백테스트를 2개 이상 선택하세요.</p>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
