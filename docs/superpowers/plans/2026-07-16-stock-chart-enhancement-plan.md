# 주식 및 가상자산 차트 고도화 구현 계획서 (stock-chart-enhancement-plan)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `lightweight-charts`를 고도화하여 이동평균선(MA 3종), 거래량(컴팩트/크게보기 상태 연동), 실시간 OHLCV 오버레이 레전드, Supabase 기반 체결 완료 마커(BUY/SELL)를 연동합니다.

**Architecture:** 
1. 수학적 계산 및 순수 데이터 포맷팅 로직은 별도 유틸리티 파일(`chartUtils.js`)로 분리하여 Node.js assert 기반으로 독립 테스트를 수행합니다.
2. [assetDetailChartPanel.jsx](file:///Users/kangheesung/10-19_%EA%B0%9C%EB%B0%9C/13_%ED%94%84%EB%A1%9C%EC%A0%9D%ED%8A%B8/13.05_%E1%84%90%E1%85%B3%E1%84%85%E1%85%A6%E1%84%8B%E1%85%B5%E1%84%83%E1%85%B5%E1%86%BC/teamproject/frontend/src/pages/assetDetailChartPanel.jsx)에 OHLCV 텍스트 오버레이 컴포넌트를 마운트하고 React State와 연동합니다.
3. [AssetDetail.jsx](file:///Users/kangheesung/10-19_%EA%B0%9C%EB%B0%9C/13_%ED%94%84%EB%A1%9C%EC%A0%9D%ED%8A%B8/13.05_%E1%84%90%E1%85%B3%E1%84%85%E1%85%A6%E1%84%8B%E1%85%B5%E1%84%83%E1%85%B5%E1%86%BC/teamproject/frontend/src/pages/AssetDetail.jsx)에서 차트 인스턴스 생성 시 이평선/거래량을 결합하고, 크로스헤어 무브 구독 및 Supabase 체결 마커 주입 함수를 추가합니다.

**Tech Stack:** React 19, Vite 8, lightweight-charts v5.2.0, Supabase JS Client, Node.js

## Global Constraints
* 모든 주석 및 코드는 영문 표준을 준수하며, 설명서 및 커밋 로그는 한국어를 적용합니다.
* 불필요한 console.log나 dead code는 발견 시 즉시 제거합니다.
* 외부 네트워크 API 호출 횟수를 절대 추가하지 않고 기존 응답 데이터만 정제해서 렌더링합니다.

---

### Task 1: 차트 헬퍼 유틸리티 구현 및 Node.js 유닛 테스트

**Files:**
* Create: `frontend/src/pages/chartUtils.js`
* Create: `frontend/src/pages/__tests__/chartUtils.test.js`

**Interfaces:**
* Consumes: 기존 프론트엔드가 수신하는 `candleData` 배열 객체 `[{ time, open, high, low, close, volume }]`
* Produces: 
  * `calculateSMA(data, period)`: `{ time: number|string, value: number|undefined }[]`
  * `getVolumeColor(candle, prevCandle)`: `'#10b981' | '#ef4444'` (상승 시 녹색, 하락 시 적색)

- [ ] **Step 1: 실패하는 Node.js 테스트 파일 생성**
  `frontend/src/pages/__tests__/chartUtils.test.js` 파일을 만들고 아래 코드를 작성합니다. 아직 `chartUtils.js`가 없으므로 import 에러로 실패해야 합니다.

```javascript
import assert from 'assert';
import { calculateSMA, getVolumeColor } from '../chartUtils.js';

console.log('Running chartUtils tests...');

try {
  // Test calculateSMA
  const mockCandles = [
    { time: 1000, close: 10 },
    { time: 2000, close: 12 },
    { time: 3000, close: 14 },
    { time: 4000, close: 16 },
  ];
  
  const sma3 = calculateSMA(mockCandles, 3);
  assert.strictEqual(sma3[0].value, undefined, 'Data point 0 should be undefined for period 3');
  assert.strictEqual(sma3[1].value, undefined, 'Data point 1 should be undefined for period 3');
  assert.strictEqual(sma3[2].value, 12, 'SMA of 10,12,14 should be 12');
  assert.strictEqual(sma3[3].value, 14, 'SMA of 12,14,16 should be 14');

  // Test getVolumeColor
  assert.strictEqual(getVolumeColor({ close: 15, open: 10 }, null), '#10b981');
  assert.strictEqual(getVolumeColor({ close: 8, open: 10 }, null), '#ef4444');
  assert.strictEqual(getVolumeColor({ close: 10, open: 10 }, { close: 8 }), '#10b981');
  
  console.log('All tests passed successfully!');
} catch (error) {
  console.error('Test failed:', error.message);
  process.exit(1);
}
```

- [ ] **Step 2: 테스트 실행 및 실패 확인**
  Run: `node frontend/src/pages/__tests__/chartUtils.test.js`
  Expected: `Cannot find module '../chartUtils.js'` 에러 출력.

- [ ] **Step 3: 유틸리티 구현 작성**
  `frontend/src/pages/chartUtils.js` 파일을 생성하고 아래의 프로덕션 코드를 작성합니다.

```javascript
/**
 * 주어진 캔들 데이터에 기반하여 단순 이동평균(SMA) 라인을 계산합니다.
 * @param {Array} data - [{time, close}, ...] 형태의 데이터
 * @param {number} period - 이동평균 계산 기간 (예: 5, 20, 60)
 * @returns {Array} - [{time, value: number|undefined}] 형태의 이평선 데이터
 */
export function calculateSMA(data, period) {
  if (!data || data.length === 0) return [];
  const smaData = [];
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      smaData.push({ time: data[i].time, value: undefined });
    } else {
      let sum = 0;
      for (let j = 0; j < period; j++) {
        sum += data[i - j].close;
      }
      smaData.push({ time: data[i].time, value: sum / period });
    }
  }
  return smaData;
}

/**
 * 캔들 시가/종가 및 전일 종가 비교를 통해 거래량 막대그래프의 색상을 결정합니다.
 * @param {Object} candle - 현재 봉 데이터
 * @param {Object|null} prevCandle - 전일 봉 데이터
 * @returns {string} - HEX 색상코드
 */
export function getVolumeColor(candle, prevCandle) {
  const currentClose = candle.close ?? 0;
  const currentOpen = candle.open ?? 0;
  
  if (currentClose > currentOpen) {
    return '#10b981'; // 상승 초록
  } else if (currentClose < currentOpen) {
    return '#ef4444'; // 하락 빨강
  }
  
  // 시가와 종가가 같을 경우 전일 대비 비교
  if (prevCandle && currentClose < (prevCandle.close ?? 0)) {
    return '#ef4444';
  }
  return '#10b981';
}
```

- [ ] **Step 4: 테스트 실행 및 패스 확인**
  Run: `node frontend/src/pages/__tests__/chartUtils.test.js`
  Expected: `All tests passed successfully!` 메세지 출력.

- [ ] **Step 5: Git 커밋**
  Run:
  ```bash
  git add frontend/src/pages/chartUtils.js frontend/src/pages/__tests__/chartUtils.test.js
  git commit -m "feat(chart): implement and test chart math and coloring utilities"
  ```

---

### Task 2: 차트 패널 UI 컴포넌트 고도화 (OHLCV 레전드 오버레이 마운트)

**Files:**
* Modify: `frontend/src/pages/assetDetailChartPanel.jsx`

**Interfaces:**
* Consumes:
  * `hoverData`: `{ time: string, open: number, high: number, low: number, close: number, volume: number, changeRate: number } | null`
  * `currentPriceInfo`: `{ open: number, high: number, low: number, close: number, volume: number, changeRate: number }` (호버되지 않았을 때 기본으로 보여줄 최신 봉 데이터)
* Produces: 상단 Absolute 영역에 반응형으로 노출되는 가시성 높은 레전드 태그 렌더링.

- [ ] **Step 1: 마크업 수정 적용**
  `frontend/src/pages/assetDetailChartPanel.jsx` 파일의 88-94라인 근처를 수정하여 차트 캔버스 좌측 상단에 실시간 레전드를 마운트합니다.

```jsx
// Target Content (assetDetailChartPanel.jsx:88-94)
        <div className={chartPanelClassName}>
          <div className={`absolute inset-0 flex items-center justify-center bg-[#0e1529]/95 z-10 rounded transition-opacity duration-200 ${loadingChart ? 'opacity-100' : 'opacity-0 pointer-events-none hidden'}`}>
            <span className="text-xs text-cyan-400 font-mono animate-pulse">시세 차트 로드 중...</span>
          </div>
          <div ref={chartContainerRef} className="h-full w-full" />
        </div>

// Replacement Content
        <div className={`${chartPanelClassName} relative`}>
          {/* 실시간 OHLCV 오버레이 레전드 */}
          {!loadingChart && (hoverData || defaultLegendData) && (
            <div className="absolute top-2 left-3 z-20 flex flex-wrap gap-x-3 gap-y-1 rounded bg-[#0f172a]/75 p-1.5 text-[10px] font-mono text-slate-400 backdrop-blur-sm pointer-events-none border border-[#1e293b]/50">
              <span className="text-slate-300 font-bold">
                {hoverData ? '선택' : '최신'}
              </span>
              <span>
                시 <strong className={((hoverData || defaultLegendData).open >= ((hoverData || defaultLegendData).close ?? 0) ? 'text-red-400' : 'text-emerald-400')}>
                  {Number((hoverData || defaultLegendData).open).toLocaleString(undefined, { maximumFractionDigits: 4 })}
                </strong>
              </span>
              <span>
                고 <strong className="text-red-400">
                  {Number((hoverData || defaultLegendData).high).toLocaleString(undefined, { maximumFractionDigits: 4 })}
                </strong>
              </span>
              <span>
                저 <strong className="text-blue-400">
                  {Number((hoverData || defaultLegendData).low).toLocaleString(undefined, { maximumFractionDigits: 4 })}
                </strong>
              </span>
              <span>
                종 <strong className={((hoverData || defaultLegendData).close >= ((hoverData || defaultLegendData).open ?? 0) ? 'text-emerald-400' : 'text-red-400')}>
                  {Number((hoverData || defaultLegendData).close).toLocaleString(undefined, { maximumFractionDigits: 4 })}
                </strong>
              </span>
              <span>
                량 <strong className="text-slate-200">
                  {Number((hoverData || defaultLegendData).volume).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </strong>
              </span>
              {((hoverData || defaultLegendData).changeRate !== undefined) && (
                <span>
                  대비 <strong className={(hoverData || defaultLegendData).changeRate >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                    {(hoverData || defaultLegendData).changeRate >= 0 ? '+' : ''}
                    {Number((hoverData || defaultLegendData).changeRate).toFixed(2)}%
                  </strong>
                </span>
              )}
            </div>
          )}
          <div className={`absolute inset-0 flex items-center justify-center bg-[#0e1529]/95 z-10 rounded transition-opacity duration-200 ${loadingChart ? 'opacity-100' : 'opacity-0 pointer-events-none hidden'}`}>
            <span className="text-xs text-cyan-400 font-mono animate-pulse">시세 차트 로드 중...</span>
          </div>
          <div ref={chartContainerRef} className="h-full w-full" />
        </div>
```

* `AssetDetailChartPanel` 함수의 매개변수 선언부에도 `hoverData`와 `defaultLegendData`가 전달될 수 있도록 속성을 추가합니다.
```jsx
// Target Content (assetDetailChartPanel.jsx:26-38)
export default function AssetDetailChartPanel({
  assetType,
  chartInterval,
  chartCardClassName,
  chartPanelClassName,
  chartContainerRef,
  isChartExpanded,
  loadingChart,
  marketFeeds,
  onIntervalChange,
  onToggleExpanded,
  onCloseExpanded,
}) {

// Replacement Content
export default function AssetDetailChartPanel({
  assetType,
  chartInterval,
  chartCardClassName,
  chartPanelClassName,
  chartContainerRef,
  isChartExpanded,
  loadingChart,
  marketFeeds,
  onIntervalChange,
  onToggleExpanded,
  onCloseExpanded,
  hoverData = null,
  defaultLegendData = null,
}) {
```

- [ ] **Step 2: ESLint 검증**
  Run: `npm run lint` (Vite frontend 디렉토리 기준)
  Expected: 컴포넌트 수정에 따른 문법오류 및 린트 경고 없음.

- [ ] **Step 3: Git 커밋**
  Run:
  ```bash
  git add frontend/src/pages/assetDetailChartPanel.jsx
  git commit -m "feat(chart): mount OHLCV overlay legend panel to ChartPanel"
  ```

---

### Task 3: 메인 차트 렌더러 연동 (이평선, 거래량 3안 하이브리드, 체결 마커 결합)

**Files:**
* Modify: `frontend/src/pages/AssetDetail.jsx`

**Interfaces:**
* Consumes:
  * `supabase` 클라이언트 세션
  * `chartUtils.js` (`calculateSMA`, `getVolumeColor`)
* Produces:
  * 3종 이평선 라인 및 거래량(컴팩트/크게보기 상태 연동) 렌더링.
  * 크로스헤어 이동 이벤트 구독 및 `hoverData` / `defaultLegendData` 주입.
  * `loadTradingMarkers` 수행 및 마커 갱신.

- [ ] **Step 1: 유틸리티 임포트 및 React State 추가**
  [AssetDetail.jsx](file:///Users/kangheesung/10-19_%EA%B0%9C%EB%B0%9C/13_%ED%94%84%EB%A1%9C%EC%A0%9D%ED%8A%B8/13.05_%E1%84%90%E1%85%B3%E1%84%85%E1%85%A6%E1%84%8B%E1%85%B5%E1%84%83%E1%85%B5%E1%86%BC/teamproject/frontend/src/pages/AssetDetail.jsx) 상단에 헬퍼 유틸리티를 임포트하고, 호버 상태 정보를 담당할 State를 정의합니다.

```jsx
// Target Content (AssetDetail.jsx:3-10)
import { createChart, CandlestickSeries } from 'lightweight-charts'
import AssetDetailChartPanel from './assetDetailChartPanel.jsx'

// Replacement Content
import { createChart, CandlestickSeries } from 'lightweight-charts'
import AssetDetailChartPanel from './assetDetailChartPanel.jsx'
import { calculateSMA, getVolumeColor } from './chartUtils.js'
```

```jsx
// Target Content (AssetDetail.jsx:324-336)
  }

  const chartContainerRef = useRef(null)
  const chartRef = useRef(null)
  const candleSeriesRef = useRef(null)
  const hasAppliedInitialFitRef = useRef(false)

// Replacement Content
  }

  const [hoverData, setHoverData] = useState(null)
  const [defaultLegendData, setDefaultLegendData] = useState(null)

  const chartContainerRef = useRef(null)
  const chartRef = useRef(null)
  const candleSeriesRef = useRef(null)
  const ma5SeriesRef = useRef(null)
  const ma20SeriesRef = useRef(null)
  const ma60SeriesRef = useRef(null)
  const volumeSeriesRef = useRef(null)
  const hasAppliedInitialFitRef = useRef(false)
```

- [ ] **Step 2: 차트 생성 및 시리즈(이평선, 거래량) 결합 로직 수정**
  `AssetDetail.jsx`의 `useEffect` 차트 초기화 블록(2240~2340라인 근처)을 고도화하여 이평선 3종 및 거래량을 추가합니다.

```javascript
// Target Content (AssetDetail.jsx:2280-2292)
      const candleSeries = chart.addSeries(CandlestickSeries, {
        upColor: '#ef4444', // 한국 상승 빨강
        downColor: '#3b82f6', // 한국 하락 파랑
        borderVisible: false,
        wickUpColor: '#ef4444',
        wickDownColor: '#3b82f6',
        priceFormat: getChartPriceFormatEvent(getChartSetupSnapshot().currentPrice),
      })

      chartRef.current = chart
      candleSeriesRef.current = candleSeries

// Replacement Content
      // 1. 캔들스틱 추가
      const candleSeries = chart.addSeries(CandlestickSeries, {
        upColor: '#ef4444',
        downColor: '#3b82f6',
        borderVisible: false,
        wickUpColor: '#ef4444',
        wickDownColor: '#3b82f6',
        priceFormat: getChartPriceFormatEvent(getChartSetupSnapshot().currentPrice),
      })

      // 2. 이평선 3종 라인 시리즈 추가
      const ma5Series = chart.addLineSeries({ color: '#ffd700', lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false })
      const ma20Series = chart.addLineSeries({ color: '#a855f7', lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false })
      const ma60Series = chart.addLineSeries({ color: '#06b6d4', lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false })

      // 3. 거래량 시리즈 추가 (하이브리드 분할/오버레이 대응)
      const volumeOptions = {
        priceFormat: { type: 'volume' },
        priceLineVisible: false,
        lastValueVisible: false,
      }
      
      // 크게보기(isChartExpanded) 여부에 따라 단독 패널(pane: 1)로 분리할지 결정
      const volumeSeries = isChartExpanded 
        ? chart.addHistogramSeries(volumeOptions, 1) // Pane 1
        : chart.addHistogramSeries({
            ...volumeOptions,
            priceScaleId: '', // Overlay 모드
          }) // Pane 0 (Default overlay)

      if (!isChartExpanded) {
        volumeSeries.priceScale().applyOptions({
          scaleMargins: {
            top: 0.8, // 차트 하단 20% 영역에 오버레이
            bottom: 0,
          },
        })
      }

      // 자석 모드 및 크로스헤어 옵션 추가
      chart.applyOptions({
        crosshair: {
          mode: 0, // CrosshairMode.MagnetOHLC 대응
        }
      })

      chartRef.current = chart
      candleSeriesRef.current = candleSeries
      ma5SeriesRef.current = ma5Series
      ma20SeriesRef.current = ma20Series
      ma60SeriesRef.current = ma60Series
      volumeSeriesRef.current = volumeSeries

      // 크로스헤어 이동 이벤트 구독 (OHLCV 레전드 갱신용)
      chart.subscribeCrosshairMove((param) => {
        if (!param || !param.time || !param.point || param.point.x < 0 || param.point.y < 0) {
          setHoverData(null)
          return
        }
        const candle = param.seriesData.get(candleSeries)
        const volumeData = param.seriesData.get(volumeSeries)
        if (candle) {
          const index = candleData.findIndex(c => c.time === param.time)
          let changeRate = 0
          if (index > 0 && candleData[index - 1].close) {
            changeRate = ((candle.close - candleData[index - 1].close) / candleData[index - 1].close) * 100
          }
          setHoverData({
            time: param.time,
            open: candle.open,
            high: candle.high,
            low: candle.low,
            close: candle.close,
            volume: volumeData ? volumeData.value : 0,
            changeRate
          })
        }
      })
```

- [ ] **Step 3: 데이터 로드 시 이평선 및 거래량 매핑 갱신**
  차트 데이터가 갱신되는 `useEffect` 블록(2344~2355라인 근처)에서 데이터 셋을 구성합니다.

```javascript
// Target Content (AssetDetail.jsx:2344-2350)
  useEffect(() => {
    if (!candleData.length || !chartRef.current || !candleSeriesRef.current) return

    try {
      candleSeriesRef.current.setData(candleData)

      // 데이터가 성공적으로 들어왔을 때, 컨테이너 크기를 최종적으로 한번 더 정밀 싱크

// Replacement Content
  useEffect(() => {
    if (!candleData.length || !chartRef.current || !candleSeriesRef.current) return

    try {
      // 1. 캔들 세팅
      candleSeriesRef.current.setData(candleData)

      // 2. 이평선 데이터 계산 및 주입
      const ma5Data = calculateSMA(candleData, 5)
      const ma20Data = calculateSMA(candleData, 20)
      const ma60Data = calculateSMA(candleData, 60)
      
      if (ma5SeriesRef.current) ma5SeriesRef.current.setData(ma5Data)
      if (ma20SeriesRef.current) ma20SeriesRef.current.setData(ma20Data)
      if (ma60SeriesRef.current) ma60SeriesRef.current.setData(ma60Data)

      // 3. 거래량 데이터 및 색상 매핑 주입
      if (volumeSeriesRef.current) {
        const volumeFormatted = candleData.map((candle, idx) => {
          const prevCandle = idx > 0 ? candleData[idx - 1] : null
          return {
            time: candle.time,
            value: candle.volume ?? 0,
            color: getVolumeColor(candle, prevCandle),
          }
        })
        volumeSeriesRef.current.setData(volumeFormatted)
      }

      // 4. 레전드 기본값 설정 (가장 최근 캔들 정보)
      const lastCandle = candleData[candleData.length - 1]
      let lastChangeRate = 0
      if (candleData.length > 1 && candleData[candleData.length - 2].close) {
        lastChangeRate = ((lastCandle.close - candleData[candleData.length - 2].close) / candleData[candleData.length - 2].close) * 100
      }
      setDefaultLegendData({
        ...lastCandle,
        changeRate: lastChangeRate
      })

      // 5. 마커 연동 호출
      loadTradingMarkers()

      // 데이터가 성공적으로 들어왔을 때, 컨테이너 크기를 최종적으로 한번 더 정밀 싱크
```

* `loadTradingMarkers` 비동기 함수를 [AssetDetail.jsx](file:///Users/kangheesung/10-19_%EA%B0%9C%EB%B0%9C/13_%ED%94%84%EB%A1%9C%EC%A0%9D%ED%8A%B8/13.05_%E1%84%90%E1%85%B3%E1%84%85%E1%85%A6%E1%84%8B%E1%85%B5%E1%84%83%E1%85%B5%E1%86%BC/teamproject/frontend/src/pages/AssetDetail.jsx) 컴포넌트 내부에 구현합니다.

```javascript
  const loadTradingMarkers = async () => {
    if (!chartRef.current || !candleSeriesRef.current || !symbol) return
    
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (!session?.user?.id) return

      // Supabase trade_proposals에서 체결된(EXECUTED) 이력 쿼리
      const { data, error } = await supabase
        .from('trade_proposals')
        .select('side, executed_at, price')
        .eq('exchange', exchange)
        .eq('status', 'EXECUTED')
        .or(buildSymbolOrFilter())
        .order('executed_at', { ascending: true })

      if (error) throw error
      if (!data || data.length === 0) {
        candleSeriesRef.current.setMarkers([])
        return
      }

      // 캔들 타임라인과 타임스탬프 매핑
      const markers = data.map((item) => {
        const dateObj = new Date(item.executed_at)
        // 차트와 동일한 Unix timestamp(초 단위) 포맷으로 변환
        const timeVal = Math.floor(dateObj.getTime() / 1000)
        
        const isBuy = item.side === 'BUY'
        return {
          time: timeVal,
          position: isBuy ? 'belowBar' : 'aboveBar',
          color: isBuy ? '#10b981' : '#ef4444',
          shape: isBuy ? 'arrowUp' : 'arrowDown',
          text: isBuy ? 'BUY' : 'SELL',
        }
      })

      candleSeriesRef.current.setMarkers(markers)
    } catch (err) {
      console.error('실패한 매매 마커 로드 에러:', err)
    }
  }
```

- [ ] **Step 4: 컴포넌트 JSX에 props 전달**
  [AssetDetail.jsx](file:///Users/kangheesung/10-19_%EA%B0%9C%EB%B0%9C/13_%ED%94%84%EB%A1%9C%EC%A0%9D%ED%8A%B8/13.05_%E1%84%90%E1%85%B3%E1%84%85%E1%85%A6%E1%84%8B%E1%85%B5%E1%84%83%E1%85%B5%E1%86%BC/teamproject/frontend/src/pages/AssetDetail.jsx) 렌더링 영역의 `AssetDetailChartPanel` 컴포넌트 마운트 지점을 찾아 속성을 추가해줍니다.

```jsx
// Target Content (AssetDetail.jsx 렌더러 영역)
          <AssetDetailChartPanel
            assetType={resolvedAssetType}
            chartInterval={chartInterval}
            chartCardClassName={chartCardClassName}
            chartPanelClassName={chartPanelClassName}
            chartContainerRef={chartContainerRef}
            isChartExpanded={isChartExpanded}
            loadingChart={loadingChart}
            marketFeeds={marketFeeds}
            onIntervalChange={handleIntervalChange}
            onToggleExpanded={handleToggleChartExpanded}
            onCloseExpanded={handleCloseChartExpanded}
          />

// Replacement Content
          <AssetDetailChartPanel
            assetType={resolvedAssetType}
            chartInterval={chartInterval}
            chartCardClassName={chartCardClassName}
            chartPanelClassName={chartPanelClassName}
            chartContainerRef={chartContainerRef}
            isChartExpanded={isChartExpanded}
            loadingChart={loadingChart}
            marketFeeds={marketFeeds}
            onIntervalChange={handleIntervalChange}
            onToggleExpanded={handleToggleChartExpanded}
            onCloseExpanded={handleCloseChartExpanded}
            hoverData={hoverData}
            defaultLegendData={defaultLegendData}
          />
```

- [ ] **Step 5: 전체 빌드 및 문법 검증**
  Run: `npm run build` (Vite 프론트엔드 빌드 실행)
  Expected: 빌드가 경고 및 에러 없이 완벽히 컴파일 완료.

- [ ] **Step 6: Git 커밋**
  Run:
  ```bash
  git add frontend/src/pages/AssetDetail.jsx
  git commit -m "feat(chart): integrate MA, Volume Pane, hover legend, and Supabase markers in AssetDetail"
  ```
