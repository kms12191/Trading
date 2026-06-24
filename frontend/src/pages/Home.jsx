import { useEffect, useMemo, useState } from "react";
import Header from "../components/Header.jsx";

function formatWon(value) {
  const number = Number(value);
  if (Number.isNaN(number)) return "-";
  return new Intl.NumberFormat("ko-KR").format(number);
}

function formatSignedRate(value) {
  const number = Number(value);
  if (Number.isNaN(number)) return "0.00%";
  const prefix = number > 0 ? "+" : "";
  return `${prefix}${number.toFixed(2)}%`;
}

function rateClass(value) {
  const number = Number(value);
  if (number > 0) return "text-emerald-400";
  if (number < 0) return "text-red-400";
  return "text-slate-400";
}

function MarketList({ title, subtitle, items, emptyText }) {
  return (
    <section className="ai-glass rounded-lg p-5 flex flex-col gap-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-ai-cyan">{subtitle}</p>
          <h3 className="text-sm font-bold text-white uppercase tracking-wider mt-1">{title}</h3>
        </div>
        <span className="rounded-full border border-slate-700 px-2.5 py-1 text-[10px] font-bold text-slate-400">
          {items.length} ITEMS
        </span>
      </div>

      {items.length > 0 ? (
        <div className="space-y-2">
          {items.map((item, index) => (
            <button
              key={`${item.symbol}-${item.name}-${index}`}
              type="button"
              className="w-full rounded-lg border border-slate-800 bg-[#0f172a]/70 px-4 py-3 text-left transition hover:border-ai-cyan/40 hover:bg-[#111827]"
            >
              <div className="flex items-center justify-between gap-4">
                <div className="min-w-0 flex items-center gap-3">
                  <div className="w-7 shrink-0 text-[10px] font-mono text-slate-500">
                    {String(index + 1).padStart(2, "0")}
                  </div>
                  <div className="min-w-0">
                    <div className="truncate text-sm font-semibold text-white">{item.name}</div>
                    <div className="mt-0.5 text-[10px] font-mono text-slate-500">
                      {item.symbol}
                      {item.qty ? ` · ${formatWon(item.qty)}주` : ""}
                    </div>
                  </div>
                </div>

                <div className="text-right">
                  <div className="text-sm font-semibold text-white">{formatWon(item.price)}</div>
                  <div className={`text-xs font-bold ${rateClass(item.change_rate)}`}>
                    {Number(item.change_rate) > 0 ? "▲" : Number(item.change_rate) < 0 ? "▼" : "•"} {formatSignedRate(item.change_rate)}
                  </div>
                </div>
              </div>
            </button>
          ))}
        </div>
      ) : (
        <div className="rounded-lg border border-dashed border-slate-700 bg-[#0f172a]/50 px-4 py-8 text-sm text-slate-400">
          {emptyText}
        </div>
      )}
    </section>
  );
}

export default function Home() {
  const [overview, setOverview] = useState({
    kis: null,
    coins: [],
    message: "",
    updated_at: "",
  });
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const loadOverview = async () => {
    setLoading(true);
    setErrorMessage("");

    try {
      const response = await fetch("http://localhost:5050/api/home/market", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });

      const data = await response.json();

      if (!response.ok || !data.success) {
        throw new Error(data.message || "홈 시장 데이터를 불러오지 못했습니다.");
      }

      setOverview(data.data || { kis: null, coins: [], message: "", updated_at: "" });
      setNotice(data.data?.message || "");
    } catch (error) {
      setErrorMessage(error.message);
      setOverview({
        kis: null,
        coins: [],
        message: "",
        updated_at: "",
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadOverview();
  }, []);

  const kisData = overview.kis;
  const domesticItems = kisData?.domestic || [];
  const foreignItems = kisData?.foreign || [];
  const coinItems = overview.coins || [];

  const summaryCards = useMemo(
    () => [
      {
        label: "국내 보유",
        value: domesticItems.length,
        hint: kisData ? "KIS 계좌 보유 종목" : "KIS 환경변수 확인",
      },
      {
        label: "해외 보유",
        value: foreignItems.length,
        hint: kisData ? "KIS 계좌 보유 종목" : "KIS 환경변수 확인",
      },
      {
        label: "코인 시세",
        value: coinItems.length,
        hint: "Coinone 공개 API",
      },
      {
        label: "업데이트",
        value: overview.updated_at ? new Date(overview.updated_at).toLocaleTimeString("ko-KR") : "-",
        hint: "최신 반영 시간",
      },
    ],
    [coinItems.length, domesticItems.length, foreignItems.length, kisData, overview.updated_at],
  );

  return (
    <div className="min-h-screen bg-obsidian-bg text-[#e2e2ec] font-inter">
      <div className="px-6 py-8">
        <Header />

        <main className="max-w-7xl mx-auto flex flex-col gap-6">
          <section className="ai-glass rounded-lg p-6">
            <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
              <div className="max-w-2xl">
                <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-ai-cyan">HOME MARKET PANEL</p>
                <h2 className="mt-2 text-2xl font-bold text-white">
                  국내 주식과 코인 시세를 한 화면에
                </h2>
                <p className="mt-3 text-sm leading-6 text-slate-400">
                  한국투자증권 모의투자 정보는 백엔드 환경변수에서 읽고, 코인 영역은 Coinone 공개 API로 실시간 시세를 가져옵니다.
                </p>
              </div>

              <div className="w-full rounded-lg border border-slate-700/60 bg-[#0f172a]/70 p-4 text-sm text-slate-300 lg:max-w-xl">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">AUTO SYNC</div>
                    <div className="mt-1 font-medium text-white">백엔드에서 국내/해외/코인 시세를 자동으로 불러옵니다.</div>
                  </div>
                  <button
                    type="button"
                    onClick={loadOverview}
                    disabled={loading}
                    className="rounded border border-ai-cyan/80 bg-ai-cyan px-4 py-2 text-sm font-semibold text-black transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {loading ? "불러오는 중..." : "새로고침"}
                  </button>
                </div>
              </div>
            </div>

            {notice ? (
              <div className="mt-4 rounded-lg border border-ai-cyan/20 bg-ai-cyan/10 px-4 py-3 text-sm text-cyan-100">
                {notice}
              </div>
            ) : null}

            {errorMessage ? (
              <div className="mt-4 rounded-lg border border-red-800 bg-red-950/30 px-4 py-3 text-sm text-red-200">
                {errorMessage}
              </div>
            ) : null}

            <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
              {summaryCards.map((card) => (
                <div key={card.label} className="rounded-lg border border-slate-700/60 bg-[#0f172a]/70 p-4">
                  <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">{card.label}</div>
                  <div className="mt-2 text-2xl font-bold text-white">{card.value}</div>
                  <div className="mt-1 text-xs text-slate-400">{card.hint}</div>
                </div>
              ))}
            </div>
          </section>

          <section className="grid grid-cols-1 gap-6 xl:grid-cols-3">
            <MarketList
              title="국내 주식"
              subtitle="KIS ACCOUNT"
              items={domesticItems.map((item) => ({ ...item, price: item.current_price }))}
              emptyText="국내 계좌 보유 종목이 여기에 표시됩니다."
            />

            <MarketList
              title="해외 주식"
              subtitle="KIS ACCOUNT"
              items={foreignItems.map((item) => ({ ...item, price: item.current_price }))}
              emptyText="해외 보유 종목이 있으면 여기에 표시됩니다."
            />

            <MarketList
              title="코인"
              subtitle="COINONE PUBLIC API"
              items={coinItems}
              emptyText="Coinone 공개 API 응답을 기다리는 중입니다."
            />
          </section>
        </main>
      </div>
    </div>
  );
}
