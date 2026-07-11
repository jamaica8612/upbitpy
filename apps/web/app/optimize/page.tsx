"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, OptimizationRun } from "@/lib/api";
import { downloadCsv, fmtNum } from "@/lib/format";
import { Button, Card, ErrorBox, Field, inputCls, Warning } from "@/components/ui";

function isoDaysAgo(days: number): string {
  return new Date(Date.now() - days * 86400_000).toISOString().slice(0, 10);
}

function parseList(s: string): number[] {
  return s.split(",").map((x) => Number(x.trim())).filter((x) => !Number.isNaN(x));
}

export default function OptimizePage() {
  const templates = useQuery({ queryKey: ["templates"], queryFn: api.templates });
  const [market, setMarket] = useState("KRW-BTC");
  const [timeframe, setTimeframe] = useState("5m");
  const [startDate, setStartDate] = useState(isoDaysAgo(90));
  const [endDate, setEndDate] = useState(isoDaysAgo(0));
  const [template, setTemplate] = useState("ema_pullback");
  const [objective, setObjective] = useState("return_over_mdd");
  const [trainRatio, setTrainRatio] = useState(70);
  const [gridText, setGridText] = useState<Record<string, string>>({
    emaFast: "10, 15, 20", emaSlow: "40, 50, 60", atrStopMult: "1.0, 1.5",
  });
  const [runId, setRunId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const numericParams = useMemo(() => {
    const t = templates.data?.find((x) => x.template === template);
    return Object.entries(t?.defaults ?? {}).filter(([, v]) => typeof v === "number") as [string, number][];
  }, [templates.data, template]);

  const combos = useMemo(
    () => Object.values(gridText).map((v) => parseList(v).length || 1).reduce((a, b) => a * b, 1),
    [gridText],
  );

  const run = useQuery({
    queryKey: ["optimization", runId],
    queryFn: () => api.optimization(runId!),
    enabled: !!runId,
    refetchInterval: (q) => {
      const s = (q.state.data as OptimizationRun | undefined)?.status;
      return s && ["completed", "failed", "cancelled"].includes(s) ? false : 1000;
    },
  });

  const start = useMutation({
    mutationFn: () => {
      const grid: Record<string, number[]> = {};
      for (const [k, v] of Object.entries(gridText)) {
        const list = parseList(v);
        if (list.length > 0) grid[k] = list;
      }
      return api.runOptimization({
        market, timeframe,
        start: `${startDate}T00:00:00+00:00`, end: `${endDate}T23:59:59+00:00`,
        template, grid, objective, trainRatio: trainRatio / 100,
      });
    },
    onSuccess: (d) => { setRunId(d.id); setError(null); },
    onError: (e: Error) => setError(e.message),
  });

  const result = run.data?.status === "completed" ? run.data.result : null;
  const running = !!runId && !["completed", "failed", "cancelled"].includes(run.data?.status ?? "");

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold">파라미터 최적화 (그리드 서치)</h1>
      <Warning>
        전체 기간 최고 수익 조합 찾기는 과최적화로 이어집니다. 훈련/검증 분리(기본 70/30)로 훈련 구간에서만
        탐색하고 검증 구간 성과를 반드시 함께 확인하세요.
      </Warning>
      <div className="grid grid-cols-1 xl:grid-cols-[320px_1fr] gap-4">
        <div className="space-y-3">
          <Card title="대상 설정">
            <div className="grid grid-cols-2 gap-2">
              <Field label="마켓">
                <input className={inputCls} value={market} onChange={(e) => setMarket(e.target.value)} />
              </Field>
              <Field label="타임프레임">
                <select className={inputCls} value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
                  {["1m", "3m", "5m", "10m", "15m", "30m", "60m", "240m", "1d"].map((tf) => (
                    <option key={tf}>{tf}</option>
                  ))}
                </select>
              </Field>
              <Field label="시작일">
                <input type="date" className={inputCls} value={startDate} onChange={(e) => setStartDate(e.target.value)} />
              </Field>
              <Field label="종료일">
                <input type="date" className={inputCls} value={endDate} onChange={(e) => setEndDate(e.target.value)} />
              </Field>
              <Field label="전략">
                <select
                  className={inputCls} value={template}
                  onChange={(e) => { setTemplate(e.target.value); setGridText({}); }}
                >
                  {templates.data?.map((t) => <option key={t.template} value={t.template}>{t.name}</option>)}
                </select>
              </Field>
              <Field label="목적함수">
                <select className={inputCls} value={objective} onChange={(e) => setObjective(e.target.value)}>
                  <option value="return_over_mdd">수익률 ÷ MDD (기본)</option>
                  <option value="total_return">총수익률</option>
                  <option value="sharpe">Sharpe</option>
                  <option value="sortino">Sortino</option>
                  <option value="calmar">Calmar</option>
                  <option value="profit_factor">Profit Factor</option>
                </select>
              </Field>
              <Field label="훈련 구간 비율 (%)" hint="탐색은 훈련 구간에서만, 평가는 검증 구간에서 별도로">
                <input type="number" min={50} max={90} className={inputCls} value={trainRatio}
                       onChange={(e) => setTrainRatio(Number(e.target.value))} />
              </Field>
            </div>
          </Card>

          <Card title="파라미터 그리드 (쉼표로 구분, 빈칸은 기본값)">
            <div className="space-y-2">
              {numericParams.map(([k, def]) => (
                <Field key={k} label={`${k} (기본 ${def})`}>
                  <input
                    className={inputCls} placeholder="예: 10, 20, 30"
                    value={gridText[k] ?? ""}
                    onChange={(e) => setGridText({ ...gridText, [k]: e.target.value })}
                  />
                </Field>
              ))}
            </div>
          </Card>

          <div className="text-xs text-muted">전체 조합 수: <b className="text-fg">{combos}</b>개 (최대 500)</div>
          <div className="flex gap-2">
            <Button onClick={() => start.mutate()} disabled={running || combos > 500} className="flex-1">
              {running ? "실행 중..." : "▶ 최적화 실행"}
            </Button>
            {running && (
              <Button variant="danger" onClick={() => runId && api.cancelOptimization(runId)}>취소</Button>
            )}
          </div>
          {running && run.data?.progress && (
            <div className="space-y-1">
              <div className="h-2 bg-panel-2 rounded overflow-hidden">
                <div className="h-full bg-accent transition-all"
                     style={{ width: `${((run.data.progress.done ?? 0) / (run.data.progress.total ?? 1)) * 100}%` }} />
              </div>
              <div className="text-xs text-muted">
                {run.data.progress.done ?? 0} / {run.data.progress.total ?? "?"} 조합
              </div>
            </div>
          )}
          {error && <ErrorBox>{error}</ErrorBox>}
          {run.data?.status === "failed" && <ErrorBox>{run.data.error}</ErrorBox>}
        </div>

        <div className="min-w-0">
          {result ? (
            <Card
              title={`결과 (${result.combinations}개 조합, 훈련 ${(result.train_ratio * 100).toFixed(0)}%)`}
              right={
                <Button variant="ghost" onClick={() =>
                  downloadCsv("optimization.csv", result.results.map((r) => ({
                    ...r.params,
                    훈련_수익률: r.train.total_return_pct, 훈련_MDD: r.train.max_drawdown_pct,
                    훈련_거래수: r.train.trade_count,
                    검증_수익률: r.valid?.total_return_pct ?? "", 검증_MDD: r.valid?.max_drawdown_pct ?? "",
                    검증_거래수: r.valid?.trade_count ?? "",
                    점수: r.score, 검증_점수: r.valid_score ?? "",
                  })))}>
                  CSV
                </Button>
              }
            >
              {result.warnings.map((w, i) => <Warning key={i}>{w}</Warning>)}
              <div className="overflow-x-auto mt-2">
                <table className="w-full text-xs">
                  <thead className="text-muted">
                    <tr>
                      {result.keys.map((k) => <th key={k} className="text-left px-2 py-1.5">{k}</th>)}
                      <th className="text-right px-2">훈련 수익률</th>
                      <th className="text-right px-2">훈련 MDD</th>
                      <th className="text-right px-2">훈련 거래</th>
                      <th className="text-right px-2">검증 수익률</th>
                      <th className="text-right px-2">검증 MDD</th>
                      <th className="text-right px-2">점수</th>
                      <th className="text-right px-2">검증 점수</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.results.map((r, i) => (
                      <tr key={i} className={`border-t border-line ${i === 0 ? "bg-accent/5" : ""}`}>
                        {result.keys.map((k) => <td key={k} className="px-2 py-1">{r.params[k]}</td>)}
                        <td className={`text-right px-2 ${(r.train.total_return_pct ?? 0) > 0 ? "text-up" : "text-down"}`}>
                          {fmtNum(r.train.total_return_pct)}%
                        </td>
                        <td className="text-right px-2 text-down">{fmtNum(r.train.max_drawdown_pct)}%</td>
                        <td className="text-right px-2">{r.train.trade_count}</td>
                        <td className={`text-right px-2 ${(r.valid?.total_return_pct ?? 0) > 0 ? "text-up" : "text-down"}`}>
                          {r.valid ? `${fmtNum(r.valid.total_return_pct)}%` : "-"}
                        </td>
                        <td className="text-right px-2 text-down">{r.valid ? `${fmtNum(r.valid.max_drawdown_pct)}%` : "-"}</td>
                        <td className="text-right px-2 font-semibold">{fmtNum(r.score, 3)}</td>
                        <td className="text-right px-2">{r.valid_score !== undefined ? fmtNum(r.valid_score, 3) : "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          ) : (
            <Card>
              <p className="text-center text-muted py-16 text-sm">
                파라미터 그리드를 설정하고 최적화를 실행하세요.
              </p>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
