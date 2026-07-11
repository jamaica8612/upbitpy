"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { Button, Card, ErrorBox, Field, inputCls } from "@/components/ui";

export default function SettingsPage() {
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const [edits, setEdits] = useState<Record<string, unknown>>({});
  const [error, setError] = useState<string | null>(null);

  // server values overlaid with unsaved local edits
  const values: Record<string, unknown> = { ...(settings.data ?? {}), ...edits };
  const setValues = setEdits;

  const save = useMutation({
    mutationFn: () => api.saveSettings(values),
    onError: (e: Error) => setError(e.message),
    onSuccess: () => setError(null),
  });

  const num = (k: string, def = 0) => Number(values[k] ?? def);

  return (
    <div className="space-y-4 max-w-2xl">
      <h1 className="text-lg font-bold">설정</h1>
      <Card title="백테스트 기본값">
        <div className="grid grid-cols-2 gap-3">
          <Field label="기본 초기 자본 (원)">
            <input type="number" className={inputCls} value={num("initialCapital", 10_000_000)}
                   onChange={(e) => setValues({ ...values, initialCapital: Number(e.target.value) })} />
          </Field>
          <Field label="기본 수수료율" hint="0.0005 = 0.05% (매수·매도 각각)">
            <input type="number" step="0.0001" className={inputCls} value={num("feeRate", 0.0005)}
                   onChange={(e) => setValues({ ...values, feeRate: Number(e.target.value) })} />
          </Field>
          <Field label="기본 슬리피지율" hint="0.0005 = 0.05%">
            <input type="number" step="0.0001" className={inputCls} value={num("slippageRate", 0.0005)}
                   onChange={(e) => setValues({ ...values, slippageRate: Number(e.target.value) })} />
          </Field>
          <Field label="최소 주문 금액 (원)">
            <input type="number" className={inputCls} value={num("minOrderKrw", 5000)}
                   onChange={(e) => setValues({ ...values, minOrderKrw: Number(e.target.value) })} />
          </Field>
          <Field label="기본 VWAP 초기화 기준">
            <select className={inputCls} value={String(values.vwapAnchor ?? "utc_day")}
                    onChange={(e) => setValues({ ...values, vwapAnchor: e.target.value })}>
              <option value="utc_day">업비트 일봉 기준 (UTC 0시 = KST 09시)</option>
              <option value="kst_day">한국시간 자정 기준</option>
            </select>
          </Field>
          <Field label="손절·익절 동시 도달 기본 처리">
            <select className={inputCls} value={String(values.ambiguityMode ?? "conservative")}
                    onChange={(e) => setValues({ ...values, ambiguityMode: e.target.value })}>
              <option value="conservative">보수적 (손절 우선)</option>
              <option value="optimistic">낙관적 (익절 우선)</option>
              <option value="invalidate">거래 무효 처리</option>
            </select>
          </Field>
          <Field label="표시 시간대">
            <input className={inputCls} value={String(values.timezone ?? "Asia/Seoul")} disabled />
          </Field>
        </div>
        <div className="mt-4 flex items-center gap-3">
          <Button onClick={() => save.mutate()}>저장</Button>
          {save.isSuccess && <span className="text-good text-sm">저장되었습니다.</span>}
        </div>
        {error && <div className="mt-3"><ErrorBox>{error}</ErrorBox></div>}
      </Card>
      <Card title="정보">
        <ul className="text-xs text-muted space-y-1 list-disc pl-4">
          <li>이 앱은 업비트 공개 시세(Quotation) API만 사용하며 개인 API Key를 요구하지 않습니다.</li>
          <li>실시간 모의매매·실거래 기능은 아직 포함되어 있지 않습니다 (docs/live-trading.md의 설계 문서 참고).</li>
          <li>모든 백테스트 결과는 과거 데이터 기반 시뮬레이션이며 미래 수익을 보장하지 않습니다.</li>
        </ul>
      </Card>
    </div>
  );
}
