import { useEffect, useMemo, useState } from "react";
import Header from "../components/Header.jsx";

const fallbackStockRows = [
  { rank: 1, name: "SK하이닉스", code: "000660", price: "126,500", change: "+5.53%", value: "540억" },
  { rank: 2, name: "삼성전자", code: "005930", price: "71,800", change: "+1.12%", value: "318억" },
  { rank: 3, name: "NAVER", code: "035420", price: "214,000", change: "-0.84%", value: "287억" },
  { rank: 4, name: "LG에너지솔루션", code: "373220", price: "373,000", change: "+2.91%", value: "251억" },
  { rank: 5, name: "현대차", code: "005380", price: "252,500", change: "-1.06%", value: "219억" },
  { rank: 6, name: "삼성바이오로직스", code: "207940", price: "852,000", change: "+0.72%", value: "193억" },
  { rank: 7, name: "기아", code: "000270", price: "108,600", change: "+1.88%", value: "182억" },
  { rank: 8, name: "KB금융", code: "105560", price: "90,200", change: "-0.42%", value: "166억" },
  { rank: 9, name: "셀트리온", code: "068270", price: "189,700", change: "+3.05%", value: "158억" },
  { rank: 10, name: "신한지주", code: "055550", price: "47,350", change: "+0.66%", value: "145억" },
];

const fallbackCoinRows = [
  { rank: 1, name: "Bitcoin", symbol: "BTC", price: "92,500,000", change: "-2.36%", volume: "3조 2,584억" },
  { rank: 2, name: "Ethereum", symbol: "ETH", price: "2,461,000", change: "-2.22%", volume: "1조 8,947억" },
  { rank: 3, name: "XRP", symbol: "XRP", price: "1,635", change: "-1.15%", volume: "5,842억" },
  { rank: 4, name: "Solana", symbol: "SOL", price: "102,900", change: "-2.28%", volume: "8,213억" },
  { rank: 5, name: "Tether", symbol: "USDT", price: "1,366.50", change: "-0.12%", volume: "4조 1,226억" },
  { rank: 6, name: "BNB", symbol: "BNB", price: "645,200", change: "-1.45%", volume: "2,313억" },
  { rank: 7, name: "USD Coin", symbol: "USDC", price: "1,366.30", change: "-0.11%", volume: "7,842억" },
  { rank: 8, name: "Dogecoin", symbol: "DOGE", price: "237.40", change: "-3.28%", volume: "1,529억" },
  { rank: 9, name: "Cardano", symbol: "ADA", price: "721.50", change: "-2.18%", volume: "1,102억" },
  { rank: 10, name: "Avalanche", symbol: "AVAX", price: "27,980", change: "-2.73%", volume: "894억" },
];

const indices = [
  { label: "KOSPI", value: "2,655.28", change: "+0.68%" },
  { label: "KOSDAQ", value: "842.21", change: "+1.12%" },
  { label: "NASDAQ", value: "16,735.02", change: "+1.28%" },
  { label: "S&P 500", value: "5,321.41", change: "+0.42%" },
  { label: "DOW", value: "38,920.26", change: "+1.08%" },
  { label: "USD/KRW", value: "1,366.50", change: "-0.12%" },
];

const filters = {
  region: ["전체", "국내", "해외"],
  metric: ["거래대금", "거래량"],
  horizon: ["실시간", "1일", "1주일", "1개월", "3개월", "6개월", "1년"],
};

const sparkBars = [34, 47, 29, 53, 41, 61, 36, 72, 58, 44, 66, 39, 52, 43, 64, 35, 70, 48, 57, 45, 67, 38, 54, 46];

function changeClass(value) {
  if (String(value).startsWith("+")) return "text-red-400";
  if (String(value).startsWith("-")) return "text-sky-400";
  return "text-slate-400";
}

function FilterChip({ label, active = false }) {
  return (
    <button
      type="button"
      className={[
        "h-10 rounded border px-4 text-[13px] font-medium tracking-[-0.01em] transition",
        active
          ? "border-ai-cyan bg-ai-cyan/10 text-ai-cyan"
          : "border-slate-700 bg-[#0f172a] text-slate-300 hover:border-ai-cyan hover:text-white",
      ].join(" ")}
    >
      {label}
    </button>
  );
}

function MarketTable({ rows, columns }) {
  return (
    <div className="overflow-hidden rounded-lg border border-slate-700/80 bg-slate-surface/90">
      <div className="border-b border-slate-700 bg-slate-800/70 px-4 py-3">
        <div className="grid grid-cols-[52px_minmax(0,1.7fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)] gap-3 text-[11px] uppercase tracking-[0.16em] text-slate-400">
          {columns.map((column) => (
            <div
              key={column}
              className={column === "현재가" || column === "등락률" || column === "거래대금" || column === "거래량" ? "text-right" : ""}
            >
              {column}
            </div>
          ))}
        </div>
      </div>

      <div className="divide-y divide-slate-700/70">
        {rows.map((row) => (
          <div
            key={`${row.rank}-${row.name}`}
            className="grid grid-cols-[52px_minmax(0,1.7fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)] gap-3 px-4 py-3 text-[14px] hover:bg-white/[0.04]"
          >
            <div className="flex items-center text-slate-400 tabular-nums">{String(row.rank).padStart(2, "0")}</div>
            <div className="min-w-0">
              <div className="truncate font-medium text-slate-100">{row.name}</div>
              <div className="mt-0.5 text-[11px] text-slate-500">{row.code || row.symbol}</div>
            </div>
            <div className="text-right tabular-nums text-slate-100">{row.price}</div>
            <div className={`text-right tabular-nums font-medium ${changeClass(row.change)}`}>{row.change}</div>
            <div className="text-right tabular-nums text-slate-300">{row.value || row.volume}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function IndexCard({ label, value, change }) {
  return (
    <div className="rounded-lg border border-slate-700/80 bg-[#0f172a]/80 p-4">
      <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">{label}</div>
      <div className="mt-2 flex items-end justify-between gap-3">
        <div className="font-mono text-[15px] text-slate-100">{value}</div>
        <div className={`text-[13px] font-medium tabular-nums ${changeClass(change)}`}>{change}</div>
      </div>
    </div>
  );
}

export default function Home() {
  const [stocks, setStocks] = useState([]);
  const [coins, setCoins] = useState(fallbackCoinRows);
  const [tossDebug, setTossDebug] = useState([]);
  const [status, setStatus] = useState("loading");

  const chartBars = useMemo(
    () => sparkBars.map((height, index) => ({ height, active: index % 5 === 0 || index === sparkBars.length - 1 })),
    [],
  );

  useEffect(() => {
    const loadOverview = async () => {
      try {
        const response = await fetch("http://localhost:5050/api/home/market", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
        });

        const data = await response.json();
        if (!response.ok || !data.success) {
          throw new Error(data.message || "홈 시세를 불러오지 못했습니다.");
        }

        setStocks(Array.isArray(data.data?.stocks) ? data.data.stocks : []);
        setCoins(Array.isArray(data.data?.coins) && data.data.coins.length > 0 ? data.data.coins : fallbackCoinRows);
        setTossDebug(Array.isArray(data.data?.toss_debug) ? data.data.toss_debug : []);
        setStatus("ready");
      } catch {
        setStocks([]);
        setCoins(fallbackCoinRows);
        setTossDebug([]);
        setStatus("error");
      }
    };

    loadOverview();
  }, []);

  return (
    <div className="min-h-screen bg-obsidian-bg text-[#e2e2ec] font-inter">
      <div className="px-4 py-4 sm:px-6 sm:py-6">
        <Header isLoggedIn={false} />

        <main className="mx-auto flex w-full max-w-7xl flex-col gap-6">
          <section className="ai-glass rounded-lg p-4 sm:p-6">
            <div className="flex flex-col gap-4">
              <div className="flex flex-wrap items-center gap-2">
                <span className="mr-2 text-[11px] uppercase tracking-[0.26em] text-slate-500">실시간 필터</span>
                {filters.region.map((label, index) => (
                  <FilterChip key={label} label={label} active={index === 0} />
                ))}
                <span className="mx-2 hidden h-7 w-px bg-slate-700 md:block" />
                {filters.metric.map((label, index) => (
                  <FilterChip key={label} label={label} active={index === 0} />
                ))}
                <span className="mx-2 hidden h-7 w-px bg-slate-700 md:block" />
                {filters.horizon.map((label, index) => (
                  <FilterChip key={label} label={label} active={index === 0} />
                ))}
              </div>

              <div className="flex flex-col gap-3 rounded-lg border border-slate-700/80 bg-slate-surface/90 px-4 py-3">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <div className="text-[11px] uppercase tracking-[0.24em] text-ai-cyan">실시간 차트</div>
                    <div className="mt-1 text-sm text-slate-300">짧은 시장 흐름 스트립</div>
                  </div>
                  <div className="text-xs text-slate-500">
                    {status === "loading" ? "LOADING" : status === "ready" ? "UPDATE: LIVE" : "LIVE FALLBACK"}
                  </div>
                </div>

                <div className="flex h-16 items-end gap-1 overflow-hidden rounded-md border border-slate-700 bg-[#0f172a] px-2 py-2">
                  {chartBars.map((bar, index) => (
                    <div key={`${bar.height}-${index}`} className="flex-1">
                      <div
                        className={[
                          "mx-auto w-full max-w-[18px] rounded-[2px] transition-all",
                          bar.active ? "bg-ai-cyan/80" : "bg-white/15",
                        ].join(" ")}
                        style={{ height: `${bar.height}%` }}
                      />
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </section>

          <section className="grid grid-cols-1 gap-5 xl:grid-cols-2">
            <MarketTable rows={stocks} columns={["순위", "종목명", "현재가", "등락률", "거래대금"]} />
            <MarketTable rows={coins} columns={["순위", "코인명", "현재가", "등락률", "거래량"]} />
          </section>

          <section className="ai-glass rounded-lg p-4 sm:p-6">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">지수</div>
                <div className="mt-1 text-sm text-slate-300">보조 시장 지표</div>
              </div>
              <div className="text-xs text-slate-500">MAJOR INDICES</div>
            </div>

            <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
              {indices.map((item) => (
                <IndexCard key={item.label} label={item.label} value={item.value} change={item.change} />
              ))}
            </div>
          </section>

          <section className="ai-glass rounded-lg p-4 sm:p-6">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <div className="text-[11px] uppercase tracking-[0.24em] text-slate-500">토스 연동 상태</div>
                <div className="mt-1 text-sm text-slate-300">실시간 조회 결과 확인용</div>
              </div>
              <div className="text-xs text-slate-500">
                {tossDebug.length > 0 ? `${tossDebug.length} ROWS` : "NO DEBUG"}
              </div>
            </div>

            <div className="overflow-hidden rounded-lg border border-slate-700/80 bg-[#0f172a]/80">
              <div className="grid grid-cols-[120px_120px_1fr_140px_minmax(0,1.4fr)] gap-3 border-b border-slate-700 bg-slate-800/70 px-4 py-3 text-[11px] uppercase tracking-[0.16em] text-slate-400">
                <div>종목</div>
                <div>조회 심볼</div>
                <div>현재가</div>
                <div>등락률</div>
              </div>
              <div className="divide-y divide-slate-700/70">
                {tossDebug.length > 0 ? (
                  tossDebug.map((item) => (
                    <div
                      key={`${item.symbol}-${item.used_symbol}`}
                      className="grid grid-cols-[120px_120px_1fr_140px_minmax(0,1.4fr)] gap-3 px-4 py-3 text-[13px]"
                    >
                      <div className="truncate text-slate-100">{item.symbol || "-"}</div>
                      <div className="truncate text-slate-300">{item.used_symbol || "-"}</div>
                      <div className="font-mono text-slate-100">
                        {typeof item.price === "number" ? item.price.toLocaleString("ko-KR") : "-"}
                      </div>
                      <div className={`font-medium ${changeClass(item.change_rate >= 0 ? `+${item.change_rate}` : `${item.change_rate}`)}`}>
                        {typeof item.change_rate === "number" ? `${item.change_rate > 0 ? "+" : ""}${item.change_rate.toFixed(2)}%` : "-"}
                      </div>
                      <div className="truncate text-[12px] text-slate-500">{item.error || "-"}</div>
                    </div>
                  ))
                ) : (
                  <div className="px-4 py-6 text-sm text-slate-500">
                    아직 토스 조회 결과가 없습니다. 키가 잘못되었거나 심볼 조회에 실패했을 수 있습니다.
                  </div>
                )}
              </div>
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}
