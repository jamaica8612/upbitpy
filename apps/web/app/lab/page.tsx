"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, BacktestRun } from "@/lib/api";
import { downloadJson, fmtKrw, fmtNum, fmtPct } from "@/lib/format";
import { Badge, Button, Card, ErrorBox, Field, inputCls, Stat, Warning } from "@/components/ui";
import { CandleChart } from "@/components/CandleChart";
import { DrawdownChart, EquityChart, MonthlyPnl, PnlDistribution } from "@/components/PerfCharts";
import { TradesTable } from "@/components/TradesTable";

const TIMEFRAMES = ["1m", "3m", "5m", "10m", "15m", "30m", "60m", "240m", "1d"];

function isoDaysAgo(days: number): string {
  const d = new Date(Date.now() - days * 86400_000);
  return d.toISOString().slice(0, 10);
}

const STAGE_KO: Record<string, string> = {
  queued: "대기 중", fetching_data: "데이터 다운로드 중", preparing_data: "데이터 준비 중",
  calculating_indicators: "지표 계산 중", running_backtest: "백테스트 실행 중",
  calculating_metrics: "성과 계산 중", completed: "완료", failed: "실패", cancelled: "취소됨",
};

export default function LabPage() {
  const qc = useQueryClient();
  const [market, setMarket] = useState("KRW-BTC");
  const [timeframe, setTimeframe] = useState("5m");
  const [startDate, setStartDate] = useState(isoDaysAgo(90));
  const [endDate, setEndDate] = useState(isoDaysAgo(0));
  const [template, setTemplate] = useState("vwap_pullback");
  const [strategyId, setStrategyId] = useState<string>("");
  const [params, setParams] = useState<Record<string, unknown>>({});
  const [initialCapital, setInitialCapital] = useState(10_000_000);
  const [feeRate, setFeeRate] = useState(0.05);
  const [slippage, setSlippage] = useState(0.05);
  const [sizingType, setSizingType] = useState("percent_equity");
  const [sizingValue, setSizingValue] = useState(100);
  const [candlePolicy, setCandlePolicy] = useState("raw");
  const [ambiguity, setAmbiguity] = useState("conservative");
  const [runId, setRunId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const markets = useQuery({ queryKey: ["markets"], queryFn: api.markets, retry: 0 });
  const templates = useQuery({ queryKey: ["templates"], queryFn: api.templates });
  const strategies = useQuery({ queryKey: ["strategies"], queryFn: api.strategies });

  const currentTemplate = templates.data?.find((t) => t.template === template);
  // until the user edits params, follow the selected template's defaults
  const effectiveParams = Object.keys(params).length ? params : (currentTemplate?.defaults ?? {});

  const estimate = useQuery({
    queryKey: ["estimate", market, timeframe, startDate, endDate],
    queryFn: () => api.estimate(market, timeframe, `${startDate}T00:00:00+00:00`, `${endDate}T23:59:59+00:00`),
  });

  const run = useQuery({
    queryKey: ["backtest", runId],
    queryFn: () => api.backtest(runId!),
    enabled: !!runId,
    refetchInterval: (q) => {
      const s = (q.state.data as BacktestRun | undefined)?.status;
      return s && ["completed", "failed", "cancelled"].includes(s) ? false : 700;
    },
  });

  const start = useMutation({
    mutationFn: () => {
      const config: Record<string, unknown> = {
        market, timeframe,
        start: `${startDate}T00:00:00+00:00`, end: `${endDate}T23:59:59+00:00`,
        costs: {
          initialCapital: initialCapital,
          buyFeeRate: feeRate / 100, sellFeeRate: feeRate / 100,
          buySlippageRate: slippage / 100, sellSlippageRate: slippage / 100,
        },
        positionSizing: { type: sizingType, value: sizingValue },
        candlePolicy, ambiguityMode: ambiguity,
      };
      if (strategyId) config.strategyId = strategyId;
      else { config.template = template; config.params = effectiveParams; }
      return api.runBacktest(config);
    },
    onSuccess: (d) => { setRunId(d.id); setError(null); qc.invalidateQueries({ queryKey: ["backtests"] }); },
    onError: (e: Error) => setError(e.message),
  });

  const result = run.data?.status === "completed" ? run.data.result : null;
  const running = !!runId && !["completed", "failed", "cancelled"].includes(run.data?.status ?? "");
  const m = result?.metrics;

  const marketOptions = useMemo(() => {
    if (markets.data) return markets.data;
    return [
      { market: "KRW-BTC", korean_name: "비트코인", english_name: "Bitcoin", is_warning: false, is_caution: false },
      { market: "KRW-ETH", korean_name: "이더리움", english_name: "Ethereum", is_warning: false, is_caution: false },
    ];
  }, [markets.data]);

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold">백테스트 연구소</h1>
      <div className="grid grid-cols-1 xl:grid-cols-[300px_1fr] gap-4">
        {/* left: settings */}
        <div className="space-y-3">
          <Card title="종목 · 기간">
            <div className="space-y-3">
              <Field label="마켓 (KRW)">
                <select className={inputCls} value={market} onChange={(e) => setMarket(e.target.value)}>
                  {marketOptions.map((mk) => (
                    <option key={mk.market} value={mk.market}>
                      {mk.korean_name} ({mk.market}){mk.is_warning ? " ⚠유의" : ""}{mk.is_caution ? " ⚠주의" : ""}
                    </option>
                  ))}
                </select>
                {markets.isError && (
                  <p className="text-[10px] text-accent mt-1">업비트 마켓 목록 조회 실패 — 기본 종목만 표시 중</p>
                )}
              </Field>
              <Field label="타임프레임">
                <div className="grid grid-cols-5 gap-1">
                  {TIMEFRAMES.map((tf) => (
                    <button
                      key={tf}
                      onClick={() => setTimeframe(tf)}
                      className={`py-1 rounded text-xs ${timeframe === tf ? "bg-accent text-black font-semibold" : "bg-panel-2 text-muted"}`}
                    >
                      {tf === "1d" ? "일" : tf}
                    </button>
                  ))}
                </div>
              </Field>
              <div className="grid grid-cols-2 gap-2">
                <Field label="시작일">
                  <input type="date" className={inputCls} value={startDate} onChange={(e) => setStartDate(e.target.value)} />
                </Field>
                <Field label="종료일">
                  <input type="date" className={inputCls} value={endDate} onChange={(e) => setEndDate(e.target.value)} />
                </Field>
              </div>
              {estimate.data && (
                <p className="text-[11px] text-muted">
                  예상 캔들 {estimate.data.estimated_candles.toLocaleString()}개 · 캐시
                  {" "}{estimate.data.cached_candles.toLocaleString()}개 · 추가 요청 약 {estimate.data.estimated_requests}회
                </p>
              )}
            </div>
          </Card>

          <Card title="전략">
            <div className="space-y-3">
              <Field label="저장된 전략" hint="전략 빌더에서 저장한 전략을 사용합니다">
                <select className={inputCls} value={strategyId} onChange={(e) => setStrategyId(e.target.value)}>
                  <option value="">(기본 제공 전략 사용)</option>
                  {strategies.data?.map((s) => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
              </Field>
              {!strategyId && (
                <>
                  <Field label="기본 제공 전략">
                    <select
                      className={inputCls}
                      value={template}
                      onChange={(e) => {
                        setTemplate(e.target.value);
                        const t = templates.data?.find((x) => x.template === e.target.value);
                        if (t) setParams(t.defaults);
                      }}
                    >
                      {templates.data?.map((t) => (
                        <option key={t.template} value={t.template}>{t.name}</option>
                      ))}
                    </select>
                  </Field>
                  <details>
                    <summary className="text-xs text-muted cursor-pointer">파라미터 ({Object.keys(effectiveParams).length}개)</summary>
                    <div className="grid grid-cols-2 gap-2 mt-2">
                      {Object.entries(effectiveParams).map(([k, v]) => (
                        <Field key={k} label={k}>
                          {typeof v === "boolean" ? (
                            <input
                              type="checkbox" checked={v}
                              onChange={(e) => setParams({ ...effectiveParams, [k]: e.target.checked })}
                            />
                          ) : typeof v === "number" ? (
                            <input
                              type="number" step="any" className={inputCls} value={v}
                              onChange={(e) => setParams({ ...effectiveParams, [k]: Number(e.target.value) })}
                            />
                          ) : (
                            <input
                              className={inputCls} value={String(v ?? "")}
                              onChange={(e) => setParams({ ...effectiveParams, [k]: e.target.value })}
                            />
                          )}
                        </Field>
                      ))}
                    </div>
                  </details>
                </>
              )}
            </div>
          </Card>

          <Card title="자본 · 비용 · 체결">
            <div className="grid grid-cols-2 gap-2">
              <Field label="초기 자본 (원)">
                <input type="number" className={inputCls} value={initialCapital}
                       onChange={(e) => setInitialCapital(Number(e.target.value))} />
              </Field>
              <Field label="수수료 (%)" hint="매수·매도 각각 적용">
                <input type="number" step="0.01" className={inputCls} value={feeRate}
                       onChange={(e) => setFeeRate(Number(e.target.value))} />
              </Field>
              <Field label="슬리피지 (%)" hint="시장가 매수는 높게, 매도는 낮게 체결">
                <input type="number" step="0.01" className={inputCls} value={slippage}
                       onChange={(e) => setSlippage(Number(e.target.value))} />
              </Field>
              <Field label="투자 방식">
                <select className={inputCls} value={sizingType} onChange={(e) => setSizingType(e.target.value)}>
                  <option value="all_in">전액 투자</option>
                  <option value="percent_equity">자산 비율 (%)</option>
                  <option value="fixed_krw">고정 금액 (원)</option>
                  <option value="risk_percent">거래당 위험률 (%)</option>
                </select>
              </Field>
              {sizingType !== "all_in" && (
                <Field label="투자 값">
                  <input type="number" className={inputCls} value={sizingValue}
                         onChange={(e) => setSizingValue(Number(e.target.value))} />
                </Field>
              )}
              <Field label="빈 캔들 처리" hint="업비트는 체결 없는 구간에 캔들이 없을 수 있습니다">
                <select className={inputCls} value={candlePolicy} onChange={(e) => setCandlePolicy(e.target.value)}>
                  <option value="raw">원본 유지 (기본)</option>
                  <option value="continuous">연속 캔들 변환</option>
                </select>
              </Field>
              <Field label="손절·익절 동시 도달" hint="한 캔들에서 손절·익절 가격 모두 닿았을 때 처리">
                <select className={inputCls} value={ambiguity} onChange={(e) => setAmbiguity(e.target.value)}>
                  <option value="conservative">보수적 (손절 우선)</option>
                  <option value="optimistic">낙관적 (익절 우선)</option>
                  <option value="invalidate">거래 무효 처리</option>
                </select>
              </Field>
            </div>
          </Card>

          <div className="flex gap-2">
            <Button onClick={() => start.mutate()} disabled={running} className="flex-1">
              {running ? "실행 중..." : "▶ 백테스트 실행"}
            </Button>
            {running && (
              <Button variant="danger" onClick={() => runId && api.cancelBacktest(runId)}>취소</Button>
            )}
          </div>
          {running && (
            <div className="text-xs text-accent animate-pulse">
              {STAGE_KO[run.data?.status ?? "queued"]}
              {run.data?.progress?.count ? ` (${run.data.progress.count.toLocaleString()} 캔들)` : ""}
            </div>
          )}
          {error && <ErrorBox>{error} — API 서버(포트 8000) 실행 여부를 확인하세요.</ErrorBox>}
          {run.data?.status === "failed" && <ErrorBox>{run.data.error}</ErrorBox>}
        </div>

        {/* right: results */}
        <div className="space-y-4 min-w-0">
          {m && result && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                <Stat label="최종 자산" value={fmtKrw(m.final_equity)} />
                <Stat label="총수익률" value={fmtPct(m.total_return_pct)}
                      tone={m.total_return_pct > 0 ? "up" : "down"}
                      sub={`매수 후 보유 ${fmtPct(m.buy_hold_return_pct)}`} />
                <Stat label="초과수익률" value={fmtPct(m.excess_return_pct)}
                      tone={m.excess_return_pct > 0 ? "up" : "down"} hint="전략 수익률 - 매수 후 보유 수익률" />
                <Stat label="최대 낙폭 (MDD)" value={fmtPct(m.max_drawdown_pct)} tone="down" />
                <Stat label="총 거래 수" value={`${m.trade_count}회`} />
                <Stat label="승률" value={`${m.win_rate_pct.toFixed(1)}%`} />
                <Stat label="Profit Factor" value={m.profit_factor === null ? "∞" : fmtNum(m.profit_factor)}
                      hint="총이익 ÷ 총손실" />
                <Stat label="Sharpe" value={fmtNum(m.sharpe)} hint="연환산 샤프 비율" />
              </div>

              {m.warnings.map((w, i) => <Warning key={i}>{w}</Warning>)}

              <Card
                title={`${market} · ${timeframe} 캔들 차트 (매매 마커 클릭 시 상세)`}
                right={
                  <div className="flex gap-2">
                    {result.synthetic_ratio > 0 && (
                      <Badge tone="warn">합성 캔들 {(result.synthetic_ratio * 100).toFixed(1)}%</Badge>
                    )}
                    <Button variant="ghost" onClick={() => downloadJson(`backtest_${runId}.json`, run.data)}>
                      JSON 내보내기
                    </Button>
                  </div>
                }
              >
                <CandleChart candles={result.candles} trades={result.trades} timeframe={timeframe} />
              </Card>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <Card title="자산 곡선 (전략 vs 매수 후 보유)"><EquityChart result={result} /></Card>
                <Card title="낙폭 (Drawdown)"><DrawdownChart result={result} /></Card>
                <Card title="거래별 손익 분포 (%)"><PnlDistribution result={result} /></Card>
                <Card title="월별 손익"><MonthlyPnl monthly={m.monthly_pnl} /></Card>
              </div>

              <Card title="상세 통계">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-x-6 gap-y-2 text-sm">
                  <Detail k="연환산 수익률" v={fmtPct(m.cagr_pct)} />
                  <Detail k="Sortino" v={fmtNum(m.sortino)} />
                  <Detail k="Calmar" v={fmtNum(m.calmar)} />
                  <Detail k="Expectancy" v={fmtPct(m.expectancy_pct)} />
                  <Detail k="평균 수익" v={fmtPct(m.avg_win_pct)} />
                  <Detail k="평균 손실" v={fmtPct(m.avg_loss_pct)} />
                  <Detail k="평균 손익비" v={fmtNum(m.payoff_ratio)} />
                  <Detail k="시장 노출" v={`${m.exposure_pct.toFixed(1)}%`} />
                  <Detail k="최대 연속 승" v={`${m.max_win_streak}회`} />
                  <Detail k="최대 연속 패" v={`${m.max_loss_streak}회`} />
                  <Detail k="평균 보유" v={`${m.avg_hold_bars.toFixed(1)}봉`} />
                  <Detail k="총 수수료" v={fmtKrw(m.total_fees_krw)} />
                  <Detail k="최고 거래" v={fmtPct(m.best_trade_pct)} />
                  <Detail k="최악 거래" v={fmtPct(m.worst_trade_pct)} />
                </div>
              </Card>

              <Card title="거래 내역">
                <TradesTable trades={result.trades} market={market} timeframe={timeframe} />
              </Card>
            </>
          )}
          {!m && !running && (
            <Card>
              <div className="text-center text-muted py-16 text-sm">
                좌측에서 종목·기간·전략을 설정하고 백테스트를 실행하세요.
                <br />백테스트 결과는 과거 데이터 기반 시뮬레이션이며 미래 수익을 보장하지 않습니다.
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function Detail({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between border-b border-line/50 py-1">
      <span className="text-muted">{k}</span>
      <span>{v}</span>
    </div>
  );
}
