"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { fmtKst } from "@/lib/format";
import { Badge, Button, Card } from "@/components/ui";

function fmtBytes(b: number): string {
  if (b > 1_048_576) return `${(b / 1_048_576).toFixed(1)} MB`;
  if (b > 1024) return `${(b / 1024).toFixed(0)} KB`;
  return `${b} B`;
}

export default function DataPage() {
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["dataStatus"], queryFn: api.dataStatus });

  const totalBytes = (status.data ?? []).reduce((a, d) => a + d.size_bytes, 0);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">데이터 관리</h1>
        <div className="text-xs text-muted">총 저장 용량: {fmtBytes(totalBytes)}</div>
      </div>
      <Card title="캐시된 캔들 데이터 (Parquet)">
        {status.data?.length ? (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="text-muted">
                <tr>
                  <th className="text-left px-2 py-1.5">종목</th>
                  <th className="text-left px-2">타임프레임</th>
                  <th className="text-left px-2">최초 데이터 (KST)</th>
                  <th className="text-left px-2">최근 데이터 (KST)</th>
                  <th className="text-right px-2">캔들 수</th>
                  <th className="text-right px-2">누락 구간</th>
                  <th className="text-right px-2">용량</th>
                  <th className="text-left px-2">마지막 업데이트</th>
                  <th className="px-2"></th>
                </tr>
              </thead>
              <tbody>
                {status.data.map((d) => (
                  <tr key={`${d.market}-${d.timeframe}`} className="border-t border-line">
                    <td className="px-2 py-1.5 font-medium">{d.market}</td>
                    <td className="px-2"><Badge>{d.timeframe}</Badge></td>
                    <td className="px-2">{fmtKst(d.first_ts)}</td>
                    <td className="px-2">{fmtKst(d.last_ts)}</td>
                    <td className="px-2 text-right">{d.candle_count.toLocaleString()}</td>
                    <td className="px-2 text-right">
                      {d.gap_count > 0 ? <Badge tone="warn">{d.gap_count}</Badge> : "0"}
                    </td>
                    <td className="px-2 text-right">{fmtBytes(d.size_bytes)}</td>
                    <td className="px-2">{fmtKst(new Date(d.last_updated * 1000).toISOString())}</td>
                    <td className="px-2 text-right">
                      <Button
                        variant="danger"
                        onClick={() => {
                          if (confirm(`${d.market} ${d.timeframe} 캐시를 삭제할까요?`)) {
                            api.deleteCache(d.market, d.timeframe).then(() =>
                              qc.invalidateQueries({ queryKey: ["dataStatus"] }));
                          }
                        }}
                      >
                        삭제
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-muted text-sm py-8 text-center">
            캐시된 데이터가 없습니다. 백테스트를 실행하면 업비트에서 자동으로 다운로드하여 저장합니다.
            <br />누락 구간(갭)은 해당 시간대에 체결이 없었다는 의미일 수 있으며 반드시 오류는 아닙니다.
          </p>
        )}
      </Card>
      <Card title="안내">
        <ul className="text-xs text-muted space-y-1 list-disc pl-4">
          <li>캔들 데이터는 <code>data/candles/market=.../timeframe=.../year=.../month=..parquet</code> 구조로 저장됩니다.</li>
          <li>같은 종목·타임프레임·기간을 다시 요청하면 캐시를 사용하고 부족한 앞/뒤 구간만 추가 수집합니다.</li>
          <li>타임스탬프는 내부적으로 UTC로 저장되며 화면에는 KST로 표시됩니다.</li>
          <li>업비트 Rate Limit(429/418)을 준수하며 자동 백오프 후 재시도합니다.</li>
        </ul>
      </Card>
    </div>
  );
}
