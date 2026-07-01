# 토스증권 Open API 공식 개발 가이드북 (toss_api_guide.md)

본 문서는 토스증권 Open API의 공식 스펙과 시세, 계좌/자산 엔드포인트 사양 및 주문 생성/정정/취소용 상세 데이터 모델(Request/Response Schema)을 정리한 소스 오프 트루스(Source of Truth) 문서입니다.

---

## 1. 기본 통신 규격 및 인증

* **Base URL:** `https://openapi.tossinvest.com`
* **인증 방식:** OAuth 2.0 Client Credentials Grant
  * **액세스 토큰 발급:** `POST /oauth2/token`
  * **헤더 형식:** `Content-Type: application/x-www-form-urlencoded`
  * **요청 바디 파라미터:**
    * `grant_type=client_credentials`
    * `client_id={WTS 발급 Client ID}`
    * `client_secret={WTS 발급 Client Secret}`
* **계좌 인증 헤더:** 계좌/자산 조회 및 주문 관련 API는 `Authorization: Bearer {token}` 외에 **`X-Tossinvest-Account: {accountSeq}`** 헤더를 필수 전송해야 합니다. (`GET /api/v1/accounts` 에서 획득한 시퀀스 전달)

---

## 2. API 그룹별 Rate Limits (TPS 한도)

| Rate Limits Group | 요청 한도 (초당) | 피크시간 한도 (09:00 ~ 09:10 KST) |
|-------------------|-----------|----------------|
| `AUTH` | 최대 5회 | - |
| `ACCOUNT` | 최대 1회 | - |
| `ASSET` | 최대 5회 | - |
| `STOCK` | 최대 5회 | - |
| `MARKET_INFO` | 최대 3회 | - |
| `MARKET_DATA` | 최대 10회 | - |
| `MARKET_DATA_CHART`| 최대 5회 | - |
| `ORDER` | 최대 6회 | **최대 3회** |
| `ORDER_HISTORY` | 최대 5회 | - |
| `ORDER_INFO` | 최대 6회 | **최대 3회** |

> [!NOTE]
> **Rate Limit 응답 헤더 사양**
> 모든 API 응답(성공 및 429 에러 모두 포함)에는 다음 헤더가 포함됩니다.
> * `X-RateLimit-Limit`: 현재 허용된 초당 요청 수
> * `X-RateLimit-Remaining`: 버킷에 남은 토큰 수 (429 발생 시 0)
> * `X-RateLimit-Reset`: 토큰 1개 재충전까지 예상 대기 초
> * `Retry-After`: 재시도 권장 대기 시간(초) (429 에러 응답에만 포함)

---

## 3. 시세 및 종목 정보 API 명세

### 1) 현재가 조회 (`GET /api/v1/prices`)
* **설명:** 종목의 실시간 현재가 정보를 다건 조회(최대 200건)합니다.
* **파라미터:** `symbols` (콤마로 구분된 종목 코드 예: `005930,000660` 또는 `AAPL,MSFT`)
* **데이터 모델 (`PriceResponse`):**
  * `symbol` (String): 종목 심볼
  * `timestamp` (Date): 데이터 최종 체결 시각 (체결 미발생 시 null)
  * `lastPrice` (BigDecimal): 현재가
  * `currency` (Currency): 거래 통화

### 2) 캔들 차트 조회 (`GET /api/v1/candles`)
* **설명:** 종목의 캔들(OHLCV) 차트 데이터를 조회합니다. (최대 200개 반환)
* **파라미터:** `symbol`, `interval` (`1m` 또는 `1d`), `count` (최대 200), `adjusted` (수정주가 적용 여부, 기본 true)
* **데이터 모델 (`Candle`):**
  * `open` (BigDecimal): 시가
  * `high` (BigDecimal): 고가
  * `low` (BigDecimal): 저가
  * `close` (BigDecimal): 종가
  * `volume` (BigDecimal): 거래량
  * `timestamp` (Date): 봉 기준 시각

### 3) 최근 체결 내역 조회 (`GET /api/v1/trades`)
* **설명:** 당일 최근 체결 내역을 조회합니다. (최대 50건)
* **파라미터:** `symbol`, `count` (조회 건수, 최대 50)
* **데이터 모델 (`Trade`):**
  * `price` (BigDecimal): 체결가
  * `volume` (BigDecimal): 체결 수량
  * `timestamp` (Date): 체결 시각
  * `currency` (Currency): 거래 통화

### 4) 종목 기본 정보 조회 (`GET /api/v1/stocks`)
* **설명:** 상장된 주식의 마스터 데이터를 조회합니다.
* **응답 모델 (`StockInfo`):**
  * `symbol` (String): 종목 심볼
  * `name` (String): 한글 종목명
  * `englishName` (String): 영문 종목명
  * `isinCode` (String): 국제증권식별번호
  * `market` (String): 상장 시장
  * `securityType` (String): 종목 유형 (STOCK 등)
  * `isCommonShare` (Boolean): 보통주 여부 (우선주인 경우 false)
  * `status` (String): 상장 상태
  * `sharesOutstanding` (BigDecimal): 발행주식수
  * `koreanMarketDetail` (KrMarketDetail): 국내 종목일 경우 국내시장 상세 데이터 (해외주식은 null)

---

## 4. 계좌 및 보유 자산 API 명세

### 1) 계좌 목록 조회 (`GET /api/v1/accounts`)
* **설명:** 사용자가 보유한 토스증권 계좌 목록을 조회합니다.
* **응답 모델 (`Account`):**
  * `accountSeq` (Long): 계좌 식별 시퀀스 (**이후 모든 계좌/주문 API의 X-Tossinvest-Account 헤더에 필수 주입**)
  * `accountNo` (String): 계좌번호
  * `accountName` (String): 계좌 별칭
  * `isDefault` (Boolean): 기본 계좌 여부

### 2) 보유 주식 조회 (`GET /api/v1/holdings`)
* **설명:** 본인 계좌의 자산 보유 주식 상세와 평가액/평가손익 합산을 조회합니다.
* **응답 모델 (`HoldingsItem`):**
  * `symbol` (String): 종목 심볼 (KR: 6자리 숫자, US: 티커)
  * `name` (String): 종목명
  * `marketCountry` (MarketCountry): 시장 국가 (`KR` 또는 `US`)
  * `currency` (Currency): 거래 통화
  * `quantity` (BigDecimal): 보유 수량
  * `lastPrice` (BigDecimal): 현재가 (거래 통화 기준)
  * `averagePurchasePrice` (BigDecimal): 매수 평균가 (거래 통화 기준)
  * `marketValue` (MarketValue): 평가 금액
  * `profitLoss` (ProfitLoss): 평가 손익
  * `dailyProfitLoss` (DailyProfitLoss): 당일 손익
  * `cost` (Cost): 매수 총비용

---

## 5. 주문(Order) API 상세 명세

### 1) 주문 생성 (`POST /api/v1/orders`)
* **설명:** 매수 또는 매도 주문을 생성합니다. (수량 기준 혹은 금액 기준)
* **요청 바디 모델 (`OrderCreateRequest`):**
  * `clientOrderId` (String, Optional): 클라이언트 지정 주문 식별자 (멱등성 키로 작동, 최대 36자, 영숫자 및 `-`, `_` 허용. 10분간 유효).
  * `symbol` (String, Required): 종목 코드/티커
  * `side` (String, Required): 주문 방향 (`BUY` or `SELL`)
  * `orderType` (String, Required): 호가 유형 (`LIMIT` - 지정가, `MARKET` - 시장가)
  * `price` (BigDecimal, Optional): 주문 가격 (`orderType`이 `LIMIT`일 때 필수). KR은 호가 단위(원)에 맞춰야 하며, US는 1달러 이상은 소수점 둘째 자리까지 지원.
  * `quantity` (BigDecimal, Optional): 주문 수량 (소수점은 미국 주식 시장가 매도 `MARKET`+`SELL`에만 6자리까지 지원, 그 외 정수 필수).
  * `orderAmount` (BigDecimal, Optional): 주문 금액 (달러). 지정 금액만큼 환산 주문 (**US MARKET 시장가 매수 전용**, 정규장 시간에만 가능)
  * `timeInForce` (String, Optional): 주문 유효 조건 (`DAY` - 당일 유효, `CLS` - 장마감 지정가 LOC). 기본값 `DAY`.
  * `confirmHighValueOrder` (Boolean, Optional): 1억원 이상 고액 주문 시 `true`를 명시해야 필터 통과. 기본값 `false`.

### 2) 주문 정정 (`POST /api/v1/orders/{orderId}/modify`)
* **설명:** 기존 대기 주문의 가격 또는 수량을 정정합니다.
* **공식 OpenAPI 기준:** `OrderModifyRequest`는 `orderType`이 필수입니다. `clientOrderId`는 정정 요청 바디에 포함하지 않습니다.
* **요청 바디 모델 (`OrderModifyRequest`):**
  * `orderType` (String, Required): 변경할 호가 유형 (`LIMIT` 또는 `MARKET`).
  * `quantity` (String decimal, Conditional): 변경할 수량.
    * 국내 주식(KR): 필수. 양의 정수만 허용합니다. 미전달, 0, 음수, 소수점은 `400 invalid-request`.
    * 해외 주식(US): 전달 불가. 제공 시 `400 us-modify-quantity-not-supported`.
  * `price` (String decimal, Conditional): 변경할 가격.
    * `LIMIT`: 필수. 미전달 시 `400 invalid-request`.
    * `MARKET`: 전달 불가. 전달 시 `400 invalid-request`.
    * KR: 정수 원 단위이며 호가 단위에 맞아야 합니다.
    * US: 달러 단위. 1달러 미만은 소수점 넷째 자리까지, 1달러 이상은 소수점 둘째 자리까지 지원합니다.
  * `confirmHighValueOrder` (Boolean, Optional): 정정 후 1억원 이상 주문 시 `true` 필요. 기본값 `false`.
* **국내 주식 (KR) 예시:**
  ```json
  {
    "orderType": "LIMIT",
    "quantity": "15",
    "price": "71000"
  }
  ```
* **해외 주식 (US) 예시:**
  ```json
  {
    "orderType": "LIMIT",
    "price": "185.5"
  }
  ```
* **주요 오류:**
  * `account-header-required` (400): `X-Tossinvest-Account` 헤더 누락.
  * `invalid-request` (400): 필수 필드 누락, 수량/가격 형식 오류, 호가 단위 불일치.
  * `us-modify-quantity-not-supported` (400): 미국 주식 정정 요청에 `quantity` 포함.
  * `already-filled`, `already-canceled`, `already-modified`, `already-rejected` (409): 정정 불가 상태.
  * `modify-restricted`, `order-hours-closed`, `max-order-amount-exceeded` (422): 거래소 비즈니스 규칙 위반.
* **구현 주의:** 정정 성공 응답의 `result.orderId`는 새로 발급된 주문 식별자이며 원주문의 `orderId`와 다릅니다. 정정 성공 후 앱의 `external_order_id`를 새 주문번호로 갱신해야 이후 취소/재정정이 정상 동작합니다.

### 3) 주문 취소 (`POST /api/v1/orders/{orderId}/cancel`)
* **설명:** 기존 주문을 취소합니다. 이미 체결 완료된 주문은 취소할 수 없습니다.

---

## 6. 에러 코드 및 디버그 힌트

API 에러 발생 시 HTTP Status와 함께 응답 바디의 `error.code`를 통해 상황을 진단합니다.

* `expired-token` (401): 토큰 만료. 즉시 토큰을 다시 발급받아 재시도해야 합니다.
* `confirm-high-value-required` (400): 1억원 이상 주문 시 `confirmHighValueOrder` 누락.
* `insufficient-buying-power` (422): 주문 가능 금액(예수금) 부족.
* `price-out-of-range` (422): 주문 가격이 상하한가를 벗어남.
* `amount-order-outside-regular-hours` (422): 국내외 거래 시간 외에 주문을 쏜 경우.
* `edge-rate-limit-exceeded` / `rate-limit-exceeded` (429): Rate Limit TPS 제한 도달.

---

## 7. 미지원 차트 주기의 자체 리샘플링(Resampling) 구현 스펙

토스증권 Open API가 공식적으로 지원하는 캔들 차트 주기는 오직 `1m`(1분봉)과 `1d`(일봉) 두 가지뿐입니다. 따라서 `5m`, `15m`, `30m`, `1h`(60m) 및 `1w`(주봉), `1M`(월봉) 등의 캔들을 조회할 수 있도록 백엔드 어플리케이션단에서 자체 리샘플링(Resampling) 데이터 합성 로직이 구현되어 동작합니다.

### 7.1 분봉/시간봉 리샘플링 (5m, 15m, 30m, 1h)
1. **기본 소스 수집:** 백엔드는 토스 캔들 API를 통해 가장 해상도가 높은 `1m` (1분봉) 원시 데이터를 수집합니다.
2. **타임 윈도우 버킷팅:** KST(한국 표준시) 기준으로 요청된 분(minutes) 단위 크기(5/15/30/60)에 맞추어 시간 축을 내림 정렬(`_floor_kst_bucket_timestamp`)하여 버킷으로 그룹화합니다.
3. **캔들 병합 연산:**
   * `open` = 그룹 내 첫 1분봉의 시가
   * `high` = 그룹 내 1분봉들 중 최고가
   * `low` = 그룹 내 1분봉들 중 최저가
   * `close` = 그룹 내 마지막 1분봉의 종가
   * `volume` = 그룹 내 모든 1분봉들의 거래량 총합

### 7.2 주봉/월봉 리샘플링 (1w, 1M)
1. **기본 소스 수집:** 백엔드는 토스 캔들 API를 통해 `1d` (일봉) 원시 데이터를 수집합니다.
2. **날짜 버킷팅:** 
   * **주봉:** 해당 일자의 월요일 날짜(`%Y-%m-%d`)로 날짜 축을 정렬하여 버킷을 형성합니다.
   * **월봉:** 해당 월의 1일 날짜(`%Y-%m-01`)로 날짜 축을 정렬하여 버킷을 형성합니다.
3. **캔들 병합 연산:** 분봉과 동일한 시가(첫날), 최고가, 최저가, 종가(마지막날), 거래량 총합 연산을 수행하여 반환합니다.
