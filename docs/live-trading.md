# 실시간 모의매매(PAPER) · 실거래(LIVE) 설계 문서

> **상태: 미구현 (설계만 확정).** 이번 버전은 백테스트 전용입니다.
> 실주문 코드는 검증 없이 넣기에 위험이 커서, 스펙의 단계적 롤아웃 원칙에 따라
> 아래 설계를 먼저 고정하고 다음 단계에서 구현합니다.

## 실행 모드

| 모드 | 데이터 | 주문 | 자산 영향 |
|------|--------|------|-----------|
| BACKTEST | 과거 OHLCV | 없음 | 없음 |
| PAPER | 실시간 WebSocket 시세·호가 | 앱 내부 가상 체결 | 없음 |
| LIVE | 실시간 + Exchange API | 실제 주문 | **있음** |

- 모드는 DB·주문기록·화면에서 항상 구분, LIVE는 화면 상단 상시 표시.
- LIVE는 기본 비활성화. 서버 재시작 시 `LIVE_TRADING_ENABLED=false`로 복귀(명시적 유지 옵션 제외).
- 활성화 절차: 권한 확인(자산조회·주문조회·주문하기만, 출금 권한 금지) → 주문 테스트 API 성공 →
  위험관리 설정(허용 종목·1회/일일 한도·손실 한도, 기본 0원=거래 불가) → 확인 문구 직접 입력.

## 계층 구조

```
Market Data → Indicator Engine → Strategy Engine → Signal
  → Position Manager → Risk Manager → Order Intent
  → Execution Engine → Broker Adapter (Paper | Upbit) → Upbit API
```

- Strategy Engine은 신호만 생성(주문 금액·API 결정 금지). 백테스트와 동일한 DSL/지표 코드
  (`app/strategies/dsl.py`)를 재사용하고, 데이터 입력·체결 계층만 교체한다.
- Risk Manager: LIVE 활성 여부, 허용 종목, 한도(1회/종목/전체/일일), 잔고, 쿨다운, 긴급정지,
  시세 신선도(stale threshold), 중복 신호를 검사해 승인된 신호만 Order Intent로 변환.
- Broker Adapter 인터페이스:

```python
class BrokerAdapter(Protocol):
    async def get_balances(self): ...
    async def get_order_chance(self, market: str): ...
    async def test_order(self, order): ...
    async def create_order(self, order): ...
    async def get_order(self, identifier: str): ...
    async def cancel_order(self, identifier: str): ...
    async def get_open_orders(self, market: str | None): ...
    async def get_closed_orders(self, market: str | None): ...
```

구현체: `PaperBrokerAdapter`(호가 기반 가상 체결), `UpbitBrokerAdapter`(실 API).

## 중복 주문 방지 (가장 중요한 포인트)

- 모든 주문에 클라이언트 identifier 부여: `usl-{mode}-{strategyId}-{market}-{signalTs}-{rand}`.
  identifier는 계정 전체에서 **재사용 금지**(주문 성패와 무관).
- 전송 순서: Intent 저장 → identifier 저장 → `SUBMITTING` → API 호출 → UUID 저장 → `SUBMITTED`.
- **타임아웃 시 절대 즉시 재전송하지 않는다.** identifier로 기존 주문 조회 →
  존재하면 추적, 부재 확정 시에만 재전송 판단.
- Signal Dedup Key: `strategyId + market + timeframe + completedCandleTs + action` — 같은 신호는 1회만.

## 주문 상태 머신

`CREATED → TESTING → READY → SUBMITTING → SUBMITTED → PARTIALLY_FILLED → FILLED`
와 `RISK_REJECTED / TEST_REJECTED / CANCEL_REQUESTED / CANCELLED / RECONCILING / UNKNOWN / FAILED`.
응답 유실은 FAILED가 아니라 **UNKNOWN**으로 기록 후 거래소 조회로 복구한다.

## Reconciliation

앱 시작·재연결·타임아웃·불일치·주기마다: 잔고/미체결/최근 종료 주문 조회 →
identifier·UUID 매칭 → 부분 체결·평단 갱신 → 로컬에 없는 주문은 `EXTERNAL_ORDER` 표시(자동 취소 금지) →
미해결 항목 존재 시 자동매매 일시정지.

## API Key 보안

- Key는 백엔드 환경변수(`UPBIT_ACCESS_KEY`/`UPBIT_SECRET_KEY`)에만 저장. 프론트 전달·로그 출력 금지.
- 필요 권한: 자산조회·주문조회·주문하기. 출금 관련 권한은 사용하지 않으며 요구하지도 않는다.
- 운영 환경은 Secret Manager/Docker Secret 사용, 고정 공인 IP 등록 안내.

## 캔들 확정 신호 · 안전장치

- 신호는 완전히 종료된 캔들에서만 계산(미완성 캔들 반복 신호 금지), 캔들→신호→주문 각 시각 기록.
- 손실 차단: 일일 손실 한도/연속 손실/UNKNOWN 발생/시세 지연/WS 단절 시 **신규 매수 중지**
  (보유 포지션 자동 청산은 별도 설정, 기본 금지).
- Kill Switch 2단계(신규 주문 중지 / 전체 중지) + 보유 자산 시장가 매도는 별도 확인 절차.

## 구현 단계

1. ~~백테스트 MVP~~ (완료 — 현재 저장소)
2. WebSocket 시세 + Paper Broker + 가상 잔고
3. 계정 조회(잔고·주문가능정보·주문 테스트, 실주문 없음)
4. 제한된 LIVE(단일 종목·단일 전략·시장가·한도 필수)
5. 확장(복수 전략, 지정가, 부분 체결, 알림, 운영 대시보드)
