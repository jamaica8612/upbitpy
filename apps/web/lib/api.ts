export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* keep default detail */
    }
    throw new Error(detail);
  }
  return res.json();
}

export interface Market {
  market: string;
  korean_name: string;
  english_name: string;
  is_warning: boolean;
  is_caution: boolean;
}

export interface StrategyTemplate {
  template: string;
  name: string;
  defaults: Record<string, unknown>;
  definition: Record<string, unknown>;
}

export interface Strategy {
  id: string;
  name: string;
  definition: Record<string, unknown> & {
    template?: string;
    params?: Record<string, unknown>;
  };
  created_at: string;
  updated_at: string;
}

export interface Trade {
  entry_index: number;
  entry_ts: string;
  entry_price: number;
  quantity: number;
  invested_krw: number;
  entry_fee: number;
  entry_snapshot: Record<string, number>;
  exit_index: number | null;
  exit_ts: string | null;
  exit_price: number | null;
  exit_fee: number;
  exit_reason: string | null;
  proceeds_krw: number | null;
  pnl_krw: number | null;
  return_pct: number | null;
  gross_return_pct: number | null;
  hold_bars: number;
  mfe_pct: number;
  mae_pct: number;
  ambiguous: boolean;
  forced_exit: boolean;
}

export interface Metrics {
  final_equity: number;
  total_return_pct: number;
  buy_hold_return_pct: number;
  excess_return_pct: number;
  max_drawdown_pct: number;
  cagr_pct: number;
  sharpe: number;
  sortino: number;
  calmar: number;
  trade_count: number;
  win_rate_pct: number;
  profit_factor: number | null;
  avg_win_pct: number;
  avg_loss_pct: number;
  payoff_ratio: number;
  expectancy_pct: number;
  max_win_streak: number;
  max_loss_streak: number;
  avg_hold_bars: number;
  max_hold_bars: number;
  exposure_pct: number;
  total_fees_krw: number;
  best_trade_pct: number | null;
  worst_trade_pct: number | null;
  monthly_pnl: Record<string, number>;
  weekday_pnl: Record<string, number>;
  hourly_pnl: Record<string, number>;
  warnings: string[];
  drawdown_curve: number[];
}

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  is_synthetic: boolean;
}

export interface BacktestResult {
  metrics: Metrics;
  trades: Trade[];
  equity_curve: number[];
  buy_hold_curve: number[];
  timestamps: string[];
  candles: Candle[];
  synthetic_ratio: number;
}

export interface BacktestRun {
  id: string;
  created_at: string;
  status: string;
  config: Record<string, unknown> & {
    market?: string;
    timeframe?: string;
    template?: string;
    start?: string;
    end?: string;
  };
  strategy_snapshot?: Record<string, unknown> & { name?: string };
  progress: { stage?: string; count?: number } | null;
  result: BacktestResult | null;
  error: string | null;
}

export interface OptimizationRun {
  id: string;
  created_at: string;
  status: string;
  config: Record<string, unknown>;
  progress: { total?: number; done?: number } | null;
  result: {
    results: {
      params: Record<string, number>;
      train: Record<string, number | null>;
      valid: Record<string, number | null> | null;
      score: number;
      valid_score?: number;
    }[];
    keys: string[];
    warnings: string[];
    train_ratio: number;
    combinations: number;
  } | null;
  error: string | null;
}

export interface DataStatus {
  market: string;
  timeframe: string;
  first_ts: string;
  last_ts: string;
  candle_count: number;
  gap_count: number;
  size_bytes: number;
  last_updated: number;
}

export const api = {
  markets: () => request<Market[]>("/api/markets"),
  dataStatus: () => request<DataStatus[]>("/api/data/status"),
  deleteCache: (market: string, timeframe?: string) =>
    request(`/api/data/cache?market=${market}${timeframe ? `&timeframe=${timeframe}` : ""}`, { method: "DELETE" }),
  estimate: (market: string, timeframe: string, start: string, end: string) =>
    request<{ estimated_candles: number; cached_candles: number; estimated_requests: number }>(
      `/api/data/estimate?market=${market}&timeframe=${timeframe}&start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`,
    ),
  templates: () => request<StrategyTemplate[]>("/api/strategies/templates"),
  strategies: () => request<Strategy[]>("/api/strategies"),
  createStrategy: (name: string, definition: Record<string, unknown>) =>
    request<Strategy>("/api/strategies", { method: "POST", body: JSON.stringify({ name, definition }) }),
  updateStrategy: (id: string, name: string, definition: Record<string, unknown>) =>
    request<Strategy>(`/api/strategies/${id}`, { method: "PUT", body: JSON.stringify({ name, definition }) }),
  deleteStrategy: (id: string) => request(`/api/strategies/${id}`, { method: "DELETE" }),
  runBacktest: (config: Record<string, unknown>) =>
    request<{ id: string }>("/api/backtests", { method: "POST", body: JSON.stringify(config) }),
  backtest: (id: string) => request<BacktestRun>(`/api/backtests/${id}`),
  backtests: (limit = 30) => request<BacktestRun[]>(`/api/backtests?limit=${limit}`),
  cancelBacktest: (id: string) => request(`/api/backtests/${id}/cancel`, { method: "POST" }),
  runOptimization: (config: Record<string, unknown>) =>
    request<{ id: string; combinations: number }>("/api/optimizations", {
      method: "POST",
      body: JSON.stringify(config),
    }),
  optimization: (id: string) => request<OptimizationRun>(`/api/optimizations/${id}`),
  cancelOptimization: (id: string) => request(`/api/optimizations/${id}/cancel`, { method: "POST" }),
  settings: () => request<Record<string, unknown>>("/api/settings"),
  saveSettings: (values: Record<string, unknown>) =>
    request("/api/settings", { method: "PUT", body: JSON.stringify({ values }) }),
};
