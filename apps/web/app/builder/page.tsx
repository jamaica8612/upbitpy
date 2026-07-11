"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { downloadJson } from "@/lib/format";
import { Button, Card, ErrorBox, Field, inputCls } from "@/components/ui";

/* ---- condition model ------------------------------------------------- */

interface Operand {
  kind: "indicator" | "const";
  name?: string;
  field?: string;
  timeframe?: string;
  params?: Record<string, number | string>;
  multiply?: number;
  value?: number | number[];
}

interface Condition {
  left: Operand;
  op: string;
  right: Operand;
  params?: Record<string, number>;
}

const INDICATORS: { name: string; label: string; fields?: string[]; params: { key: string; def: number | string }[] }[] = [
  { name: "close", label: "종가", params: [] },
  { name: "open", label: "시가", params: [] },
  { name: "high", label: "고가", params: [] },
  { name: "low", label: "저가", params: [] },
  { name: "volume", label: "거래량", params: [] },
  { name: "value", label: "거래대금", params: [] },
  { name: "sma", label: "SMA", params: [{ key: "period", def: 20 }] },
  { name: "ema", label: "EMA", params: [{ key: "period", def: 20 }] },
  { name: "wma", label: "WMA", params: [{ key: "period", def: 20 }] },
  { name: "rsi", label: "RSI", params: [{ key: "period", def: 14 }] },
  { name: "macd", label: "MACD", fields: ["macd", "signal", "histogram"], params: [{ key: "fast", def: 12 }, { key: "slow", def: 26 }, { key: "signal", def: 9 }] },
  { name: "stochastic", label: "Stochastic", fields: ["k", "d"], params: [{ key: "k", def: 14 }, { key: "d", def: 3 }] },
  { name: "roc", label: "ROC", params: [{ key: "period", def: 12 }] },
  { name: "adx", label: "ADX", params: [{ key: "period", def: 14 }] },
  { name: "atr", label: "ATR", params: [{ key: "period", def: 14 }] },
  { name: "bollinger", label: "볼린저밴드", fields: ["mid", "upper", "lower", "width"], params: [{ key: "period", def: 20 }, { key: "mult", def: 2 }] },
  { name: "donchian", label: "돈치안 채널", fields: ["upper", "lower", "mid"], params: [{ key: "period", def: 20 }] },
  { name: "obv", label: "OBV", params: [] },
  { name: "mfi", label: "MFI", params: [{ key: "period", def: 14 }] },
  { name: "volume_sma", label: "거래량 SMA", params: [{ key: "period", def: 20 }] },
  { name: "relative_volume", label: "상대 거래량", params: [{ key: "period", def: 20 }] },
  { name: "supertrend", label: "Supertrend", fields: ["supertrend", "direction"], params: [{ key: "period", def: 10 }, { key: "mult", def: 3 }] },
  { name: "vwap", label: "VWAP (캔들 기반 근사)", params: [{ key: "anchor", def: "utc_day" }] },
  { name: "change_pct", label: "가격 변화율(%)", params: [{ key: "period", def: 1 }] },
  { name: "gap_pct", label: "갭(%)", params: [] },
  { name: "disparity", label: "이격도(%)", params: [{ key: "period", def: 20 }] },
];

const OPERATORS = [
  { op: ">", label: ">" }, { op: ">=", label: ">=" }, { op: "<", label: "<" }, { op: "<=", label: "<=" },
  { op: "==", label: "==" },
  { op: "crosses_above", label: "상향 돌파" }, { op: "crosses_below", label: "하향 돌파" },
  { op: "between", label: "범위 안 (between)" }, { op: "outside", label: "범위 밖 (outside)" },
  { op: "rising_for", label: "N봉 연속 상승" }, { op: "falling_for", label: "N봉 연속 하락" },
  { op: "percent_above", label: "x% 이상 위" }, { op: "percent_below", label: "x% 이상 아래" },
  { op: "distance_percent", label: "이격 x% 이내" }, { op: "touched_within", label: "최근 N봉 내 터치" },
  { op: "highest_of", label: "N봉 최고" }, { op: "lowest_of", label: "N봉 최저" },
];

const TIMEFRAMES = ["", "3m", "5m", "15m", "30m", "60m", "240m", "1d"];

function defaultCondition(): Condition {
  return {
    left: { kind: "indicator", name: "ema", params: { period: 20 } },
    op: ">",
    right: { kind: "indicator", name: "ema", params: { period: 50 } },
  };
}

/* ---- operand editor --------------------------------------------------- */

function OperandEditor({ operand, onChange, allowConst }: {
  operand: Operand; onChange: (o: Operand) => void; allowConst?: boolean;
}) {
  const meta = INDICATORS.find((i) => i.name === operand.name);
  return (
    <div className="flex flex-wrap items-center gap-1">
      <select
        className="bg-panel-2 border border-line rounded px-1.5 py-1 text-xs"
        value={operand.kind === "const" ? "__const" : operand.name}
        onChange={(e) => {
          if (e.target.value === "__const") onChange({ kind: "const", value: 0 });
          else {
            const m = INDICATORS.find((i) => i.name === e.target.value)!;
            onChange({
              kind: "indicator", name: m.name,
              field: m.fields?.[0],
              params: Object.fromEntries(m.params.map((pp) => [pp.key, pp.def])),
            });
          }
        }}
      >
        {allowConst !== false && <option value="__const">숫자 상수</option>}
        {INDICATORS.map((i) => (
          <option key={i.name} value={i.name}>{i.label}</option>
        ))}
      </select>
      {operand.kind === "const" ? (
        <input
          type="number" step="any"
          className="w-20 bg-panel-2 border border-line rounded px-1.5 py-1 text-xs"
          value={Array.isArray(operand.value) ? operand.value[0] : (operand.value ?? 0)}
          onChange={(e) => onChange({ ...operand, value: Number(e.target.value) })}
        />
      ) : (
        <>
          {meta?.fields && (
            <select
              className="bg-panel-2 border border-line rounded px-1.5 py-1 text-xs"
              value={operand.field}
              onChange={(e) => onChange({ ...operand, field: e.target.value })}
            >
              {meta.fields.map((f) => <option key={f}>{f}</option>)}
            </select>
          )}
          {meta?.params.map((pp) => (
            <input
              key={pp.key}
              type={typeof pp.def === "number" ? "number" : "text"} step="any"
              title={pp.key}
              className="w-16 bg-panel-2 border border-line rounded px-1.5 py-1 text-xs"
              value={operand.params?.[pp.key] ?? pp.def}
              onChange={(e) =>
                onChange({
                  ...operand,
                  params: { ...operand.params, [pp.key]: typeof pp.def === "number" ? Number(e.target.value) : e.target.value },
                })
              }
            />
          ))}
          <select
            className="bg-panel-2 border border-line rounded px-1.5 py-1 text-xs"
            title="타임프레임 (비우면 기준봉)"
            value={operand.timeframe ?? ""}
            onChange={(e) => onChange({ ...operand, timeframe: e.target.value || undefined })}
          >
            {TIMEFRAMES.map((tf) => <option key={tf} value={tf}>{tf || "기준봉"}</option>)}
          </select>
          <input
            type="number" step="any" placeholder="×배수"
            title="곱셈 배수 (예: 거래량 SMA × 1.5)"
            className="w-16 bg-panel-2 border border-line rounded px-1.5 py-1 text-xs"
            value={operand.multiply ?? ""}
            onChange={(e) => onChange({ ...operand, multiply: e.target.value ? Number(e.target.value) : undefined })}
          />
        </>
      )}
    </div>
  );
}

/* ---- condition list ---------------------------------------------------- */

function ConditionList({ conditions, onChange, groupOp, setGroupOp }: {
  conditions: Condition[]; onChange: (c: Condition[]) => void;
  groupOp: "AND" | "OR"; setGroupOp: (op: "AND" | "OR") => void;
}) {
  const needsRangeConst = (op: string) => op === "between" || op === "outside";
  const needsBars = (op: string) => ["rising_for", "falling_for", "touched_within", "highest_of", "lowest_of"].includes(op);
  const needsPercent = (op: string) => ["percent_above", "percent_below", "distance_percent", "touched_within"].includes(op);

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-xs">
        <span className="text-muted">조건 결합:</span>
        {(["AND", "OR"] as const).map((op) => (
          <button
            key={op}
            onClick={() => setGroupOp(op)}
            className={`px-2 py-0.5 rounded ${groupOp === op ? "bg-accent text-black" : "bg-panel-2 text-muted"}`}
          >
            {op}
          </button>
        ))}
      </div>
      {conditions.map((c, i) => (
        <div key={i} className="bg-panel-2/50 border border-line rounded-md p-2 space-y-1.5">
          <div className="flex items-start justify-between gap-2">
            <div className="space-y-1.5 flex-1">
              <OperandEditor operand={c.left} allowConst={false}
                onChange={(o) => onChange(conditions.map((x, j) => (j === i ? { ...x, left: o } : x)))} />
              <div className="flex items-center gap-2">
                <select
                  className="bg-panel border border-accent/40 rounded px-1.5 py-1 text-xs text-accent"
                  value={c.op}
                  onChange={(e) => {
                    const op = e.target.value;
                    const next = { ...c, op } as Condition;
                    if (needsRangeConst(op)) next.right = { kind: "const", value: [30, 70] };
                    onChange(conditions.map((x, j) => (j === i ? next : x)));
                  }}
                >
                  {OPERATORS.map((o) => <option key={o.op} value={o.op}>{o.label}</option>)}
                </select>
                {needsBars(c.op) && (
                  <input
                    type="number" title="N봉" placeholder="N봉"
                    className="w-14 bg-panel-2 border border-line rounded px-1.5 py-1 text-xs"
                    value={c.params?.bars ?? 3}
                    onChange={(e) =>
                      onChange(conditions.map((x, j) => (j === i ? { ...x, params: { ...x.params, bars: Number(e.target.value) } } : x)))}
                  />
                )}
                {needsPercent(c.op) && (
                  <input
                    type="number" step="0.1"
                    title={c.op === "touched_within" ? "허용 오차 %" : "%"}
                    placeholder="%"
                    className="w-14 bg-panel-2 border border-line rounded px-1.5 py-1 text-xs"
                    value={c.params?.[c.op === "distance_percent" ? "max_percent" : c.op === "touched_within" ? "tolerance_percent" : "percent"] ?? 0}
                    onChange={(e) => {
                      const key = c.op === "distance_percent" ? "max_percent" : c.op === "touched_within" ? "tolerance_percent" : "percent";
                      onChange(conditions.map((x, j) => (j === i ? { ...x, params: { ...x.params, [key]: Number(e.target.value) } } : x)));
                    }}
                  />
                )}
              </div>
              {needsRangeConst(c.op) ? (
                <div className="flex gap-1 items-center text-xs">
                  <input type="number" step="any" className="w-20 bg-panel-2 border border-line rounded px-1.5 py-1"
                    value={Array.isArray(c.right.value) ? c.right.value[0] : 0}
                    onChange={(e) => {
                      const hi = Array.isArray(c.right.value) ? c.right.value[1] : 100;
                      onChange(conditions.map((x, j) => (j === i ? { ...x, right: { kind: "const", value: [Number(e.target.value), hi] } } : x)));
                    }} />
                  <span className="text-muted">~</span>
                  <input type="number" step="any" className="w-20 bg-panel-2 border border-line rounded px-1.5 py-1"
                    value={Array.isArray(c.right.value) ? c.right.value[1] : 100}
                    onChange={(e) => {
                      const lo = Array.isArray(c.right.value) ? c.right.value[0] : 0;
                      onChange(conditions.map((x, j) => (j === i ? { ...x, right: { kind: "const", value: [lo, Number(e.target.value)] } } : x)));
                    }} />
                </div>
              ) : !["rising_for", "falling_for"].includes(c.op) && (
                <OperandEditor operand={c.right}
                  onChange={(o) => onChange(conditions.map((x, j) => (j === i ? { ...x, right: o } : x)))} />
              )}
            </div>
            <button className="text-muted hover:text-up text-xs" onClick={() => onChange(conditions.filter((_, j) => j !== i))}>
              삭제
            </button>
          </div>
        </div>
      ))}
      <Button variant="ghost" onClick={() => onChange([...conditions, defaultCondition()])}>+ 조건 추가</Button>
    </div>
  );
}

/* ---- page --------------------------------------------------------------- */

export default function BuilderPage() {
  const qc = useQueryClient();
  const strategies = useQuery({ queryKey: ["strategies"], queryFn: api.strategies });
  const templates = useQuery({ queryKey: ["templates"], queryFn: api.templates });

  const [name, setName] = useState("나의 전략");
  const [entryConds, setEntryConds] = useState<Condition[]>([defaultCondition()]);
  const [entryOp, setEntryOp] = useState<"AND" | "OR">("AND");
  const [exitConds, setExitConds] = useState<Condition[]>([]);
  const [exitOp, setExitOp] = useState<"AND" | "OR">("OR");
  const [risk, setRisk] = useState({
    stopLossType: "atr", stopLossValue: 1.0, takeProfitType: "atr", takeProfitValue: 1.8,
    trailingStopType: "none", trailingStopValue: 0, atrPeriod: 14, maxHoldBars: 96,
  });
  const [editingId, setEditingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [importText, setImportText] = useState("");

  const definition = {
    name, version: 1, marketType: "spot", direction: "long",
    entry: { operator: entryOp, conditions: entryConds },
    exit: { operator: exitOp, conditions: exitConds },
    risk: {
      ...risk,
      trailingStopType: risk.trailingStopType === "none" ? undefined : risk.trailingStopType,
    },
  };

  const save = useMutation({
    mutationFn: () =>
      editingId ? api.updateStrategy(editingId, name, definition) : api.createStrategy(name, definition),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["strategies"] }); setError(null); },
    onError: (e: Error) => setError(e.message),
  });

  const loadDefinition = (def: Record<string, unknown>, newName?: string) => {
    const d = def as {
      name?: string;
      entry?: { operator?: "AND" | "OR"; conditions?: Condition[] };
      exit?: { operator?: "AND" | "OR"; conditions?: Condition[] };
      risk?: Partial<typeof risk>;
    };
    setName(newName ?? d.name ?? "가져온 전략");
    setEntryConds((d.entry?.conditions ?? []).filter((c) => !("operator" in c)));
    setEntryOp(d.entry?.operator ?? "AND");
    setExitConds((d.exit?.conditions ?? []).filter((c) => !("operator" in c)));
    setExitOp(d.exit?.operator ?? "OR");
    if (d.risk) setRisk((r) => ({ ...r, ...d.risk, trailingStopType: d.risk?.trailingStopType ?? "none" }));
  };

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold">전략 빌더</h1>
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_380px] gap-4">
        <div className="space-y-4">
          <Card title="기본 정보">
            <div className="flex flex-wrap gap-2 items-end">
              <Field label="전략 이름">
                <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} />
              </Field>
              <Field label="기본 전략에서 시작">
                <select
                  className={inputCls}
                  defaultValue=""
                  onChange={(e) => {
                    const t = templates.data?.find((x) => x.template === e.target.value);
                    if (t) loadDefinition(t.definition, `${t.name} (복제)`);
                  }}
                >
                  <option value="">선택...</option>
                  {templates.data?.map((t) => <option key={t.template} value={t.template}>{t.name}</option>)}
                </select>
              </Field>
              {editingId && (
                <Button variant="ghost" onClick={() => { setEditingId(null); setName(name + " (복제)"); }}>
                  복제본으로 저장하기
                </Button>
              )}
            </div>
          </Card>

          <Card title="진입 조건 (매수)">
            <ConditionList conditions={entryConds} onChange={setEntryConds} groupOp={entryOp} setGroupOp={setEntryOp} />
          </Card>

          <Card title="청산 조건 (매도) — 위험관리 조건과 함께 최초 발생 조건으로 청산">
            <ConditionList conditions={exitConds} onChange={setExitConds} groupOp={exitOp} setGroupOp={setExitOp} />
          </Card>

          <Card title="위험관리">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <Field label="손절 유형">
                <select className={inputCls} value={risk.stopLossType}
                        onChange={(e) => setRisk({ ...risk, stopLossType: e.target.value })}>
                  <option value="none">없음</option><option value="atr">ATR 배수</option><option value="percent">고정 %</option>
                </select>
              </Field>
              <Field label="손절 값">
                <input type="number" step="0.1" className={inputCls} value={risk.stopLossValue}
                       onChange={(e) => setRisk({ ...risk, stopLossValue: Number(e.target.value) })} />
              </Field>
              <Field label="익절 유형">
                <select className={inputCls} value={risk.takeProfitType}
                        onChange={(e) => setRisk({ ...risk, takeProfitType: e.target.value })}>
                  <option value="none">없음</option><option value="atr">ATR 배수</option><option value="percent">고정 %</option>
                </select>
              </Field>
              <Field label="익절 값">
                <input type="number" step="0.1" className={inputCls} value={risk.takeProfitValue}
                       onChange={(e) => setRisk({ ...risk, takeProfitValue: Number(e.target.value) })} />
              </Field>
              <Field label="트레일링 스톱">
                <select className={inputCls} value={risk.trailingStopType}
                        onChange={(e) => setRisk({ ...risk, trailingStopType: e.target.value })}>
                  <option value="none">없음</option><option value="atr">ATR 배수</option><option value="percent">고정 %</option>
                </select>
              </Field>
              <Field label="트레일링 값">
                <input type="number" step="0.1" className={inputCls} value={risk.trailingStopValue}
                       onChange={(e) => setRisk({ ...risk, trailingStopValue: Number(e.target.value) })} />
              </Field>
              <Field label="ATR 기간">
                <input type="number" className={inputCls} value={risk.atrPeriod}
                       onChange={(e) => setRisk({ ...risk, atrPeriod: Number(e.target.value) })} />
              </Field>
              <Field label="최대 보유 봉 수 (0=무제한)">
                <input type="number" className={inputCls} value={risk.maxHoldBars}
                       onChange={(e) => setRisk({ ...risk, maxHoldBars: Number(e.target.value) })} />
              </Field>
            </div>
          </Card>

          <div className="flex gap-2">
            <Button onClick={() => save.mutate()}>{editingId ? "전략 수정" : "전략 저장"}</Button>
            <Button variant="ghost" onClick={() => downloadJson(`${name}.json`, definition)}>JSON 내보내기</Button>
          </div>
          {error && <ErrorBox>{error}</ErrorBox>}
          {save.isSuccess && <p className="text-good text-sm">저장되었습니다.</p>}
        </div>

        <div className="space-y-4">
          <Card title="JSON 미리보기">
            <pre className="text-[10px] bg-panel-2 rounded-md p-2 overflow-auto max-h-80">
              {JSON.stringify(definition, null, 2)}
            </pre>
          </Card>
          <Card title="JSON 가져오기">
            <textarea
              className={`${inputCls} h-24 font-mono text-[10px]`}
              placeholder='{"name": "...", "entry": {...}, ...}'
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
            />
            <Button
              variant="ghost" className="mt-2"
              onClick={() => {
                try {
                  loadDefinition(JSON.parse(importText));
                  setError(null);
                } catch {
                  setError("JSON 파싱에 실패했습니다. 형식을 확인하세요.");
                }
              }}
            >
              가져오기
            </Button>
          </Card>
          <Card title="저장된 전략">
            {strategies.data?.length ? (
              <ul className="space-y-1.5">
                {strategies.data.map((s) => (
                  <li key={s.id} className="flex items-center justify-between text-sm">
                    <button
                      className="hover:text-accent text-left"
                      onClick={() => { setEditingId(s.id); loadDefinition(s.definition, s.name); }}
                    >
                      {s.name}
                    </button>
                    <button
                      className="text-xs text-muted hover:text-up"
                      onClick={() => api.deleteStrategy(s.id).then(() => qc.invalidateQueries({ queryKey: ["strategies"] }))}
                    >
                      삭제
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-muted text-sm">저장된 전략 없음</p>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
