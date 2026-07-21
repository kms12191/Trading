# 한국투자증권(KIS) Open API 공식 개발 가이드북 (kis_api_guide.md)

본 문서는 한국투자증권(KIS) Developers Open API의 공식 스펙과 주요 API 규격, Rate Limit 정책 및 접근 토큰 관리 주의사항을 정리한 소스 오브 트루스(Source of Truth) 문서입니다.

---

## 1. 기본 통신 규격 및 인증

* **Base URL:**
  * **실전 투자:** `https://openapi.koreainvestment.com:9443`
  * **모의 투자:** `https://openapivts.koreainvestment.com:29443`
* **인증 방식:** OAuth 2.0 Access Token 기반 API 호출
  * **액세스 토큰 발급:** `POST /oauth2/tokenP`
  * **헤더 형식:** `Content-Type: application/json`
  * **요청 바디 파라미터:**
    ```json
    {
      "grant_type": "client_credentials",
      "appkey": "{발급 AppKey}",
      "appsecret": "{발급 AppSecret}"
    }
    ```
* **공통 API 요청 헤더 규격:**
  * `Authorization`: `Bearer {access_token}`
  * `Content-Type`: `application/json`
  * `appkey`: `{발급 AppKey}`
  * `appsecret`: `{발급 AppSecret}`
  * `tr_id`: 거래 ID (각 호출 기능 및 실전/모의 환경에 따라 상이)
  * `custtype`: 고객 구분 (개인은 `P` 고정)

---

## 2. API 그룹별 Rate Limits (호출 제한 정책)

한국투자증권은 서버 과부하 방지를 위해 초당 호출 건수(TPS) 제한 정책을 엄격히 적용하며, 초과 시 **`EGW00201 (초당 거래건수 초과)`** 또는 **`429 Too Many Requests`** 에러를 반환합니다.

| 환경 구분 | 요청 한도 (초당) | 제한 조건 |
|---|---|---|
| **실전 투자 (`REAL`)** | **최대 20건** | 초과 시 `EGW00201` 오류가 반환됩니다. |
| **모의 투자 (`MOCK`)** | **최대 5건** | 매우 협소하므로 호출 시 최소 0.2초 이상의 시간 지연이 요구됩니다. |

---

## 3. 접근 토큰(Access Token) 발급 하드 룰

접근 토큰 발급 API는 한투 서버의 과부하 방지를 위해 극도로 엄격한 횟수 제한 정책을 가지고 있습니다.

> [!IMPORTANT]
> **접근 토큰 발급 빈도 초과 제한 (`EGW00133`)**
> * 동일한 AppKey/AppSecret 조합에 대해 **1분당 최대 1회만 토큰 발급(OAuth2)이 가능**합니다.
> * 1분 이내에 동일한 Key로 토큰 발급 API를 2회 이상 호출할 경우, 아래 에러가 반환되며 모든 API 호출이 차단됩니다.
>   `{"error_code":"EGW00133","error_description":"접근토큰 발급 잠시 후 다시 시도하세요(1분당 1회)"}`

### ⚠️ 공식 토큰 관리 수명
* 발급된 토큰의 공식 유효 기간은 최대 **24시간 (86,400초)** 입니다.
* 발급된 토큰은 유효 시간 동안 계속해서 재사용해야 하며, 빈번한 재호출은 공식적으로 제한됩니다.

---

## 4. 계좌 정보 및 잔고 조회 API 명세

### 1) 주식잔고조회 (`GET /uapi/domestic-stock/v1/trading/inquire-balance`)
* **설명:** 계좌의 보유 종목 및 예수금 상세 평가 현황을 조회합니다.
* **주요 거래 ID (`tr_id`):**
  * **실전 투자 (`REAL`):** `TTTC8434R`
  * **모의 투자 (`MOCK`):** `VTTC8434R`
* **주요 요청 파라미터:**
  * `CANO` (String, Required): 계좌번호 8자리
  * `ACNT_PRDT_CD` (String, Required): 계좌상품코드 (기본 `01`)
  * `AFHR_FLG` (String, Required): 시간외단일가여부 (`N`)
  * `OFL_YN` (String, Required): 오프라인여부 (`N`)
  * `INQR_DVSN` (String, Required): 조회구분 (`02` - 한도조회 포함 전체)
  * `UNPR_DVSN` (String, Required): 단가구분 (`01` - 기본)
  * `FUND_STTL_ICLD_YN` (String, Required): 펀드결제분포함여부 (`N`)
  * `FNCG_AMT_AUTO_RDPT_YN` (String, Required): 융자금자동상환여부 (`N`)
  * `PRCS_DVSN` (String, Required): 처리구분 (`00` - 전일매매포함)
