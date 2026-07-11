"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { fmtKst, fmtPct } from "@/lib/format";
import { Badge, Card } from "@/components/ui";

export default function Dashboard() {
  const backtests = useQuery({ queryKey: ["backtests"], queryFn: () => api.backtests(10) });
  const strategies = useQuery({ queryKey: ["strategies"], queryFn: api.strategies });
  const dataStatus = useQuery({ queryKey: ["dataStatus"], queryFn: api.dataStatus });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-bold">대시보드</h1>
        <p className="text-xs text-muted mt-1">
          업비트 현물 전략 백테스트 연구 도구 — 결과는 시뮬레이션이며 투자 추천이 아닙니다.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="최근 백테스트" right={<Link href="/lab" className="text-xs text-accent">연구소 →</Link>}>
          {backtests.data?.length ? (
            <ul className="space-y-2">
              {backtests.data.map((b) => {
                const metrics = (b.result as { metrics?: { total_return_pct?: number; trade_count?: number } } | null)?.metrics;
                return (
                  <li key={b.id} className="flex items-center justify-between text-sm border-b border-line/50 pb-2">
                    <div>
                      <span className="font-medium">{String(b.config.market ?? "?")}</span>
                      <span className="text-muted text-xs ml-2">
                        {String(b.config.timeframe ?? "")} · {b.strategy_snapshot?.name ?? String(b.config.template ?? "커스텀")}
                      </span>
                      <div className="text-[10px] text-muted">{fmtKst(b.created_at)}</div>
                    </div>
                    <div className="text-right">
                      {b.status === "completed" && metrics ? (
                        <span className={(metrics.total_return_pct ?? 0) > 0 ? "text-up" : "text-down"}>
                          {fmtPct(metrics.total_return_pct)}
                        </span>
                      ) : (
                        <Badge tone={b.status === "failed" ? "down" : "neutral"}>{b.status}</Badge>
                      )}
                      {metrics && <div className="text-[10px] text-muted">{metrics.trade_count}건</div>}
                    </div>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="text-muted text-sm">아직 백테스트가 없습니다. 연구소에서 첫 백테스트를 실행해 보세요.</p>
          )}
        </Card>

        <Card title="저장한 전략" right={<Link href="/builder" className="text-xs text-accent">전략 빌더 →</Link>}>
          {strategies.data?.length ? (
            <ul className="space-y-2">
              {strategies.data.map((s) => (
                <li key={s.id} className="flex justify-between text-sm border-b border-line/50 pb-2">
                  <span>{s.name}</span>
                  <span className="text-xs text-muted">{fmtKst(s.updated_at)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted text-sm">저장된 전략이 없습니다.</p>
          )}
        </Card>

        <Card title="캐시된 데이터" right={<Link href="/data" className="text-xs text-accent">데이터 관리 →</Link>} className="lg:col-span-2">
          {dataStatus.data?.length ? (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
              {dataStatus.data.map((d) => (
                <div key={`${d.market}-${d.timeframe}`} className="bg-panel-2 rounded-md px-3 py-2 text-xs">
                  <div className="font-semibold text-sm">{d.market} <Badge>{d.timeframe}</Badge></div>
                  <div className="text-muted mt-1">
                    {d.candle_count.toLocaleString()}개 캔들 · 누락 {d.gap_count}구간
                  </div>
                  <div className="text-muted">{fmtKst(d.first_ts)} ~ {fmtKst(d.last_ts)}</div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-muted text-sm">캐시된 캔들 데이터가 없습니다. 백테스트를 실행하면 자동으로 다운로드됩니다.</p>
          )}
        </Card>
      </div>
    </div>
  );
}
