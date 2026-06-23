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
  if (number > 0) return "text-red-400";
  if (number < 0) return "text-blue-400";
  return "text-slate-400";
}

function MarketList({ title, subtitle, items, emptyText, tone = "cyan" }) {
  return (
    <section className="rounded-3xl border border-slate-800 bg-[#0c0e15]/80 p-5 shadow-2xl shadow-black/20">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-400">{subtitle}</p>
          <h3 className={`mt-1 text-lg font-bold ${tone === "cyan" ? "text-cyan-300" : tone === "blue" ? "text-blue-300" : "text-white"}`}>
            {title}
          </h3>
        </div>
        <span className="rounded-full border border-slate-700 px-2.5 py-1 text-[10px] font-bold text-slate-400">
          {items.length} ITEMS
        </span>
      </div>

      {items.length > 0 ? (
        <div className="space-y-3">
          {items.map((item) => (
            <div
              key={`${item.symbol}-${item.name}`}
              className="rounded-2xl border border-slate-800 bg-[#11131a] px-4 py-3 transition hover:border-cyan-400/30 hover:bg-[#141824]"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-white">{item.name}</div>
                  <div className="mt-0.5 text-[11px] font-mono text-slate-500">{item.symbol}</div>
                </div>
                <div className={`text-right text-sm font-bold ${rateClass(item.change_rate)}`}>
                  {formatSignedRate(item.change_rate)}
                </div>
              </div>

              <div className="mt-3 grid grid-cols-3 gap-2 text-[11px] text-slate-400">
                <div className="rounded-lg bg-[#0c0e15] px-2 py-2">
                  <div>현재가</div>
                  <div className="mt-1 text-sm font-semibold text-white">{formatWon(item.price)}</div>
                </div>
                <div className="rounded-lg bg-[#0c0e15] px-2 py-2">
                  <div>고가</div>
                  <div className="mt-1 text-sm font-semibold text-white">{formatWon(item.high ?? item.current_price)}</div>
                </div>
                <div className="rounded-lg bg-[#0c0e15] px-2 py-2">
                  <div>저가</div>
                  <div className="mt-1 text-sm font-semibold text-white">{formatWon(item.low ?? item.current_price)}</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-2xl border border-dashed border-slate-700 bg-[#11131a] px-4 py-8 text-sm text-slate-400">
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

  const loadOverview = async (payload = {}) => {
    setLoading(true);
    setErrorMessage("");

    try {
      const response = await fetch("http://localhost:5050/api/home/overview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await response.json();

      if (!response.ok || !data.success) {
        throw new Error(data.message || "홈 요약 데이터를 불러오지 못했습니다.");
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
        hint: kisData ? "KIS 계좌 보유 종목" : "KIS 키 입력 후 조회",
      },
      {
        label: "해외 보유",
        value: foreignItems.length,
        hint: kisData ? "해외 보유 종목" : "KIS 키 입력 후 조회",
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
    <div className="min-h-screen bg-[#11131a] text-white">
      <div className="mx-auto max-w-7xl px-6 py-6">
        <Header />
      </div>

      <main className="mx-auto max-w-7xl px-6 pb-10">
        <section className="rounded-[2rem] border border-slate-800 bg-gradient-to-br from-[#0c0e15] via-[#0f1320] to-[#11131a] p-6 shadow-2xl shadow-black/30">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
            <div className="max-w-2xl">
              <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-cyan-300">HOME MARKET PANEL</p>
              <h2 className="mt-2 text-2xl font-bold tracking-tight text-white">
                국내 주식과 코인 시세를 한 화면에
              </h2>
              <p className="mt-3 text-sm leading-6 text-slate-400">
                한국투자증권 모의투자 계좌는 백엔드 연동으로 불러오고, 코인 영역은 Coinone 공개 API로 실시간 시세를 가져옵니다.
              </p>
            </div>

            <div className="w-full rounded-2xl border border-slate-800 bg-[#0b0d12] p-4 text-sm text-slate-300 lg:max-w-xl">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">AUTO SYNC</div>
                  <div className="mt-1 font-medium text-white">백엔드에서 계좌와 코인 시세를 자동으로 불러옵니다.</div>
                </div>
                <button
                  type="button"
                  onClick={() => loadOverview()}
                  disabled={loading}
                  className="rounded-lg bg-cyan-400 px-4 py-2 text-sm font-semibold text-black transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {loading ? "불러오는 중..." : "새로고침"}
                </button>
              </div>
            </div>
          </div>

          {notice ? (
            <div className="mt-4 rounded-2xl border border-cyan-500/20 bg-cyan-500/10 px-4 py-3 text-sm text-cyan-100">
              {notice}
            </div>
          ) : null}

          {errorMessage ? (
            <div className="mt-4 rounded-2xl border border-red-800 bg-red-950/30 px-4 py-3 text-sm text-red-200">
              {errorMessage}
            </div>
          ) : null}

          <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            {summaryCards.map((card) => (
              <div key={card.label} className="rounded-2xl border border-slate-800 bg-[#0b0d12] p-4">
                <div className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500">{card.label}</div>
                <div className="mt-2 text-2xl font-bold text-white">{card.value}</div>
                <div className="mt-1 text-xs text-slate-400">{card.hint}</div>
              </div>
            ))}
          </div>
        </section>

        <section className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-3">
          <MarketList
            title="국내 주식"
            subtitle="KIS ACCOUNT"
            items={domesticItems.map((item) => ({
              ...item,
              price: item.current_price,
            }))}
            emptyText="국내 계좌 보유 종목이 여기에 표시됩니다."
            tone="cyan"
          />

          <MarketList
            title="해외 주식"
            subtitle="KIS ACCOUNT"
            items={foreignItems.map((item) => ({
              ...item,
              price: item.current_price,
            }))}
            emptyText="해외 보유 종목이 있으면 여기에 표시됩니다."
            tone="blue"
          />

          <MarketList
            title="코인"
            subtitle="COINONE PUBLIC API"
            items={coinItems}
            emptyText="Coinone 공개 API 응답을 받아오는 중입니다."
            tone="white"
          />
        </section>
      </main>
    </div>
  );
}
