# Upbit Strategy Lab

업비트 공개 시세 데이터로 현물 단타·스윙 전략을 백테스트하고 비교하는 **연구·검증 도구**입니다.

> ⚠️ 이 앱의 모든 결과는 과거 데이터 기반 시뮬레이션이며 **투자 추천이 아닙니다**.
> 현물 롱 전용 · 공개 Quotation API만 사용 · 자동주문/개인 API 연동 없음.

## 주요 기능

- **데이터**: KRW 마켓 전 종목, 1분~일봉 캔들 자동 다운로드 + Parquet 로컬 캐시(부족분만 추가 수집), Rate Limit(429/418) 준수, UTC 저장·KST 표시, 빈 캔들 원본유지/합성채움 정책
- **지표**: SMA·EMA·WMA·RSI·MACD·Stochastic·ROC·ADX·ATR·볼린저·돈치안·OBV·MFI·상대거래량·Supertrend·VWAP(업비트 일봉/KST/Anchored) 등 — 전부 직접 구현 + 단위 테스트
- **백테스트 엔진**: 신호 다음 캔들 시가 체결(미래 데이터 사용 금지), 매수·매도 수수료/슬리피지, 동일 캔들 손절·익절 동시 도달 시 보수적/낙관적/무효 모드, 트레일링 스톱, 최대 보유 봉 수, 단일 포지션·물타기/피라미딩 금지, 마지막 캔들 강제청산 옵션
- **기본 전략 7종**: VWAP 눌림매수 · EMA 눌림매수 · EMA 골든크로스(상위 TF 필터) · RSI 추세 반등 · 볼린저 평균회귀 · 돈치안 돌파 · MACD 추세
- **전략 빌더**: 코드 없이 조건(crosses_above, touched_within, between, …)을 조합, JSON 저장/가져오기, 멀티 타임프레임 조건(상위봉 종료 후에만 값 사용 — 누출 방지 단위 테스트 포함)
- **결과**: 수익률·MDD·승률·PF·Sharpe·Sortino·Calmar·Expectancy·노출률·월/요일/시간대 손익, 캔들 차트 매매 마커(클릭 시 거래 상세), 자산/낙폭/분포 차트, 거래 내역 정렬·필터·CSV
- **비교/최적화**: 여러 전략 비교표+수익 곡선, 그리드 서치(훈련/검증 분리 기본, 목적함수 선택, 진행률/취소), 과최적화 경고

## 실행 방법

### Docker (권장)

```bash
docker compose up --build
# web: http://localhost:3000  /  api: http://localhost:8000/docs
```

### 로컬 개발

```bash
# 백엔드
cd apps/api
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --reload --port 8000

# 프론트엔드 (새 터미널)
cd apps/web
npm install
npm run dev   # http://localhost:3000
```

로그인 없이 바로 사용합니다. 백테스트를 실행하면 필요한 업비트 캔들을 자동으로 내려받아
`data/candles/market=…/timeframe=…/year=…/month=….parquet`에 캐시합니다.

인터넷 없이 UI를 만져보려면(개발용, 실데이터 아님):

```bash
cd apps/api && .venv/bin/python scripts/seed_demo_data.py 90 KRW-BTC 5m
```

### 테스트

```bash
cd apps/api && .venv/bin/python -m pytest      # 데이터/지표/DSL/엔진/지표 50+ 테스트
cd apps/web && npm run lint && npx tsc --noEmit
```

## 폴더 구조

```
apps/
  api/        FastAPI + pandas 백테스트 엔진 (app/upbit, app/data, app/indicators,
              app/strategies, app/backtest) + tests/
  web/        Next.js 16 + Tailwind + lightweight-charts + Recharts
data/         Parquet 캔들 캐시 + SQLite 메타데이터 (git 미포함)
docs/         설계 문서 (실거래 아키텍처 설계 포함)
```

## 백테스트 체결 규칙 (기본값)

- 지표·신호는 **완성된 캔들**에서 계산, 체결은 **다음 캔들 시가** (합성 캔들이면 다음 실캔들로 이월)
- 시장가 매수 체결가 = 기준가 × (1+슬리피지), 매도 = × (1−슬리피지), 수수료는 양방향 각각
- 한 캔들에서 손절·익절 가격에 모두 닿으면 기본 **보수적 모드**(손절 우선) — 갭 발생 시 시가 체결
- 잔액 초과 매수 금지, 최소 주문금액 미만 진입 건너뜀, 복리 반영

## 실거래·모의매매에 대하여

실시간 PAPER/LIVE 매매(개인 API 연동)는 이번 버전에 **포함되지 않았습니다**.
계층 분리(Strategy → Risk → Execution → Broker Adapter), 주문 identifier 중복 방지,
Reconciliation 등 안전 설계는 [docs/live-trading.md](docs/live-trading.md)에 정리되어 있으며
단계적 롤아웃 원칙(백테스트 → PAPER → 계정 조회 → 제한된 LIVE)을 따릅니다.

## License

MIT
