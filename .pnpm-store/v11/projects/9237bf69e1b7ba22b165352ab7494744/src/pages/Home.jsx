import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useNavigate } from "react-router-dom";
import Header from "../components/Header.jsx";
import AssetLogo from "../components/AssetLogo.jsx";
import { deleteUserWatchlistItem, fetchUserWatchlist, normalizeWatchlistItem, upsertUserWatchlistItem } from "../supabaseClient";

const filters = {
  region: ["국내", "해외"],
  ranking: ["거래대금", "거래량", "상승률", "하락률"],
};

function getKoreanMarketState() {
  const now = new Date();
  const kstText = now.toLocaleString("en-US", { timeZone: "Asia/Seoul" });
  const kst = new Date(kstText);
  const day = kst.getDay();
  const minutes = kst.getHours() * 60 + kst.getMinutes();
  const isWeekday = day >= 1 && day <= 5;
  const isOpen = isWeekday && minutes >= 9 * 60 && minutes <= 15 * 60 + 30;
  if (isOpen) return { isOpen: true, label: "실시간 자동 갱신: 60초" };
  return { isOpen: false, label: "장 마감 자동 갱신: 10분" };
}

function formatSnapshotTime(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function changeClass(value) {
  if (String(value).startsWith("+")) return "text-red-400";
  if (String(value).startsWith("-")) return "text-sky-400";
  return "text-slate-400";
}

function formatNumber(value, decimals = 0) {
  const numberValue = Number(value);
  if (!Number.isFinite(numberValue)) return "-";
  return numberValue.toLocaleString("ko-KR", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function isForeignRow(row = {}) {
  const marketText = String(
    row.market_segment
      ?? row.market_country
      ?? row.region
      ?? row.country
      ?? "",
  ).toUpperCase();
  const assetType = String(row.asset_type ?? row.assetType ?? "").toUpperCase();
  const symbol = String(row.symbol ?? row.code ?? row.ticker ?? "").toUpperCase();
  const explicitForeign = ["US", "USA", "NASDAQ", "NYSE", "AMEX", "해외"].some((token) => marketText.includes(token));
  return explicitForeign || (assetType === "STOCK" && /^[A-Z.\-]+$/.test(symbol));
}

function formatPrice(row) {
  if (typeof row.price === "string" && row.price) {
    if (row.price === "-") return "-";
    if (isForeignRow(row)) return row.price.startsWith("$") ? row.price : `$${row.price}`;
    return row.price.endsWith("원") ? row.price : `${row.price}원`;
  }
  const price = row.price ?? row.current_price ?? row.live_price;
  if (price === undefined || price === null || price === "") return "-";
  if (isForeignRow(row)) return `$${formatNumber(price, Number(price) % 1 === 0 ? 0 : 1)}`;
  return `${formatNumber(price, Number(price) % 1 === 0 ? 0 : 1)}원`;
}

function formatChange(row) {
  // 서버 응답이 새/구 필드를 섞어서 내려줘도 같은 화면 포맷으로 보이게 맞춘다.
  // 숫자 표기 방식이 달라도 사용자는 한 가지 스타일로만 보게 하는 게 목적이다.
  if (typeof row.change === "string" && row.change) return row.change;
  const change = Number(row.change_rate ?? row.changeRate ?? row.change_percent ?? row.changePercent ?? row.live_change_rate);
  if (!Number.isFinite(change)) return "-";
  return `${change > 0 ? "+" : ""}${change.toFixed(2)}%`;
}

function formatValue(row, valueKey, ranking) {
  if (isForeignRow(row) && valueKey !== "volume" && ["상승률", "하락률"].includes(ranking)) return "-";
  const direct = valueKey === "volume"
    ? row.trading_volume ?? row.volume
    : row.trading_value ?? row.value;
  if (typeof direct === "string" && direct) return direct;
  const numeric = Number(direct);
  if (!Number.isFinite(numeric) || numeric <= 0) return "-";
  if (valueKey === "volume") return Math.round(numeric).toLocaleString("ko-KR");
  if (numeric >= 100_000_000_0000) return `${(numeric / 100_000_000_0000).toFixed(1)}조원`;
  if (numeric >= 100_000_000) return `${Math.round(numeric / 100_000_000).toLocaleString("ko-KR")}억원`;
  return `${Math.round(numeric).toLocaleString("ko-KR")}원`;
}

function numericChange(row) {
  // 정렬용 값도 표시용 값과 같은 우선순위를 따라가야 사용자 눈에 일관된다.
  // 화면에는 같은 종목이 같은 기준으로 정렬되어 보여야 혼란이 없다.
  const raw = row.change_rate ?? row.changeRate ?? row.change_percent ?? row.changePercent ?? row.live_change_rate ?? row.change;
  const value = Number(String(raw ?? "").replace("%", "").replace("+", ""));
  return Number.isFinite(value) ? value : 0;
}

function numericMetric(row, metric) {
  const raw = metric === "거래량" ? row.trading_volume ?? row.volume : row.trading_value ?? row.value;
  const text = String(raw ?? "").replace(/,/g, "").trim();
  const numberPart = Number(text.replace(/[^0-9.-]/g, ""));
  if (!Number.isFinite(numberPart)) return 0;
  if (text.includes("조")) return numberPart * 1_000_000_000_000;
  if (text.includes("억")) return numberPart * 100_000_000;
  if (text.includes("만")) return numberPart * 10_000;
  const value = Number(text.replace(/[^0-9.-]/g, ""));
  return Number.isFinite(value) ? value : 0;
}

function getWatchlistKey(row = {}, assetType = "STOCK") {
  const item = normalizeWatchlistItem({ ...row, asset_type: assetType });
  return `${item.asset_type}:${item.exchange}:${item.symbol}`;
}

function matchesRegion(row, region) {
  if (!region) return true;
  const isForeign = isForeignRow(row);
  return region === "해외" ? isForeign : !isForeign;
}

function applyClientMarketFilters(rows, activeFilters) {
  const filtered = [...rows].filter((row) => matchesRegion(row, activeFilters.region));
  const ranking = activeFilters.ranking || activeFilters.metric || "거래대금";

  if (ranking === "상승률") {
    filtered.sort((a, b) => numericChange(b) - numericChange(a));
  } else if (ranking === "하락률") {
    filtered.sort((a, b) => numericChange(a) - numericChange(b));
  } else {
    filtered.sort((a, b) => numericMetric(b, ranking) - numericMetric(a, ranking));
  }

  return filtered.map((row, index) => ({ ...row, rank: index + 1 }));
}

function FilterChip({ label, active = false, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "h-10 rounded border px-4 text-[13px] font-semibold transition",
        active
          ? "border-ai-cyan bg-ai-cyan/10 text-ai-cyan"
          : "border-slate-700 bg-[#0f172a] text-slate-300 hover:border-ai-cyan hover:text-white",
      ].join(" ")}
    >
      {label}
    </button>
  );
}

function FilterBar({ title, children }) {
  return (
    <div className="flex flex-col gap-2 rounded-lg border border-slate-800/80 bg-[#07111d]/70 px-3 py-3">
      <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">{title}</div>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  );
}

function MarketTable({ rows, titleType = "stock", ranking = "거래대금", favoriteKeys = new Set(), onToggleFavorite, moreHref = "" }) {
  const isStock = titleType === "stock";
  const nameHeader = isStock ? "종목명" : "코인명";
  const showVolume = ranking === "거래량";
  const valueHeader = isStock
    ? (showVolume ? "거래량" : "거래대금")
    : (showVolume ? "거래량" : "거래대금");
  const valueKey = showVolume ? "volume" : "value";

  return (
    <div className="overflow-hidden rounded-lg border border-slate-600/80 bg-[#061321]/90 shadow-[0_0_28px_rgba(0,224,255,0.06)]">
      <div className="border-b border-slate-700 bg-slate-800/70 px-4 py-3">
        <div className="grid grid-cols-[34px_42px_minmax(130px,1.7fr)_minmax(92px,1fr)_minmax(78px,0.8fr)_minmax(92px,1fr)] items-center gap-3 text-[12px] font-semibold text-slate-300">
          <div />
          <div className="text-center">순위</div>
          <div>{nameHeader}</div>
          <div className="text-right">현재가</div>
          <div className="text-right">등락률</div>
          <div className="text-right">{valueHeader}</div>
        </div>
      </div>

      <div className="divide-y divide-slate-700/70">
        {rows.length === 0 ? (
          <div className="px-4 py-10 text-center text-sm text-slate-500">
            표시할 데이터가 없습니다.
          </div>
        ) : rows.map((row) => {
          const symbol = row.code || row.symbol;
          const assetType = isStock ? "STOCK" : "CRYPTO";
          const assetPath = `/asset/${assetType}/${symbol}`;
          const isFavorite = favoriteKeys.has(getWatchlistKey(row, assetType));
          return (
            <Link
              key={`${row.rank}-${row.name}`}
              to={assetPath}
              className="grid min-h-[58px] grid-cols-[34px_42px_minmax(130px,1.7fr)_minmax(92px,1fr)_minmax(78px,0.8fr)_minmax(92px,1fr)] items-center gap-3 px-4 py-2 text-[14px] hover:bg-white/[0.04] active:bg-white/[0.08] cursor-pointer transition-colors text-inherit no-underline block"
            >
              <button
                type="button"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onToggleFavorite?.(row, assetType);
                }}
                className={`text-[24px] leading-none transition ${isFavorite ? 'text-red-400 hover:text-red-300' : 'text-slate-400 hover:text-ai-cyan'}`}
                aria-label="관심 종목"
                aria-pressed={isFavorite}
              >
                {isFavorite ? '♥' : '♡'}
              </button>
              <div className="text-center text-[16px] text-slate-100 tabular-nums">{row.rank}</div>
              <div className="flex min-w-0 items-center gap-3">
                <AssetLogo symbol={row.code || row.symbol} assetType={assetType} name={row.name} />
                <div className="min-w-0">
                  <div className="truncate text-[15px] font-semibold text-slate-100">{row.name}</div>
                  <div className="mt-0.5 truncate text-[12px] text-slate-500">{row.code || row.symbol}</div>
                </div>
              </div>
              <div className="text-right text-[15px] tabular-nums text-slate-100">{formatPrice(row)}</div>
              <div className={`text-right text-[15px] font-medium tabular-nums ${changeClass(formatChange(row))}`}>
                {formatChange(row)}
              </div>
              <div className="text-right text-[15px] tabular-nums text-slate-200">{formatValue(row, valueKey, ranking)}</div>
            </Link>
          );
        })}
      </div>
      <Link to={moreHref || "#"} className="block border-t border-slate-700/80 px-4 py-3 text-center text-sm font-medium text-slate-200 no-underline transition hover:bg-white/[0.03]">
        더보기<span className="ml-3 text-xl text-slate-400">→</span>
      </Link>
    </div>
  );
}

function MobileMarketTable({ rows, titleType = "stock", ranking = "거래대금", favoriteKeys = new Set(), onToggleFavorite }) {
  const showVolume = ranking === "거래량";
  const valueKey = showVolume ? "volume" : "value";
  const valueLabel = titleType === "stock"
    ? (showVolume ? "거래량" : "거래대금")
    : (showVolume ? "거래량" : "거래대금");
  return (
    <div className="divide-y divide-slate-700/70 overflow-hidden rounded-lg border border-slate-700 bg-[#061321]/90 md:hidden">
      {rows.length === 0 ? (
        <div className="px-4 py-8 text-center text-sm text-slate-500">표시할 데이터가 없습니다.</div>
      ) : rows.map((row) => {
        const symbol = row.code || row.symbol;
        const assetType = titleType === "stock" ? "STOCK" : "CRYPTO";
        const assetPath = `/asset/${assetType}/${symbol}`;
        const isFavorite = favoriteKeys.has(getWatchlistKey(row, assetType));
        return (
          <Link
            key={`${titleType}-${row.rank}-${row.name}`}
            to={assetPath}
            className="p-4 block text-inherit no-underline hover:bg-white/[0.02] active:bg-white/[0.04] cursor-pointer transition-colors"
          >
            <div className="flex items-center gap-3">
              <div className="w-6 text-center text-slate-300">{row.rank}</div>
              <AssetLogo symbol={symbol} assetType={assetType} name={row.name} />
              <div className="min-w-0 flex-1">
                <div className="truncate font-semibold text-slate-100">{row.name}</div>
                <div className="mt-0.5 text-[11px] text-slate-500">{row.code || row.symbol}</div>
              </div>
              <button
                type="button"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onToggleFavorite?.(row, assetType);
                }}
                className={`text-[22px] transition ${isFavorite ? 'text-red-400 hover:text-red-300' : 'text-slate-400 hover:text-ai-cyan'}`}
                aria-label="관심 종목"
                aria-pressed={isFavorite}
              >
                {isFavorite ? '♥' : '♡'}
              </button>
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2 text-right text-[13px]">
              <div>
                <div className="text-[10px] text-slate-500">현재가</div>
                <div className="mt-1 text-slate-100">{formatPrice(row)}</div>
              </div>
              <div>
                <div className="text-[10px] text-slate-500">등락률</div>
                <div className={`mt-1 ${changeClass(formatChange(row))}`}>{formatChange(row)}</div>
              </div>
              <div>
                <div className="text-[10px] text-slate-500">{valueLabel}</div>
                <div className="mt-1 text-slate-200">{formatValue(row, valueKey, ranking)}</div>
              </div>
            </div>
          </Link>
        );
      })}
    </div>
  );
}

export default function Home({ isLoggedIn, userEmail, handleLogout }) {
  const navigate = useNavigate();
  const [stockCandidates, setStockCandidates] = useState([]);
  const [coins, setCoins] = useState([]);
  const [status, setStatus] = useState("loading");
  const [message, setMessage] = useState("");
  const [favoriteKeys, setFavoriteKeys] = useState(new Set());
  const [marketState, setMarketState] = useState(getKoreanMarketState());
  const [snapshotMeta, setSnapshotMeta] = useState({});
  const [updatedAt, setUpdatedAt] = useState("");
  const [stockFilters, setStockFilters] = useState({
    region: "국내",
    ranking: "거래대금",
    horizon: "실시간",
  });
  const [coinFilters, setCoinFilters] = useState({
    ranking: "거래대금",
  });
  const stocks = useMemo(
    () => applyClientMarketFilters(stockCandidates, stockFilters).slice(0, 10),
    [stockCandidates, stockFilters.region, stockFilters.ranking],
  );
  const filteredCoins = useMemo(
    () => applyClientMarketFilters(coins, coinFilters).slice(0, 10),
    [coins, coinFilters.ranking],
  );
  const stockRankingOptions = stockFilters.region === "해외"
    ? filters.ranking.filter((label) => label !== "거래대금")
    : filters.ranking;
  const stockMoreHref = `/market-rankings?assetType=stock&region=${encodeURIComponent(stockFilters.region)}&ranking=${encodeURIComponent(stockFilters.ranking)}`;
  const coinMoreHref = `/market-rankings?assetType=coin&ranking=${encodeURIComponent(coinFilters.ranking)}`;

  const loadFavorites = async () => {
    if (!isLoggedIn) {
      setFavoriteKeys(new Set());
      return;
    }

    try {
      const items = await fetchUserWatchlist();
      setFavoriteKeys(new Set(items.map((item) => getWatchlistKey(item, item.assetType))));
    } catch (error) {
      console.warn('Failed to load watchlist.', error);
      setFavoriteKeys(new Set());
    }
  };

  const handleToggleFavorite = async (row, assetType) => {
    if (!isLoggedIn) {
      alert('로그인이 필요한 서비스입니다.');
      navigate('/login');
      return;
    }

    const key = getWatchlistKey(row, assetType);
    const nextKeys = new Set(favoriteKeys);
    const isFavorite = nextKeys.has(key);

    try {
      if (isFavorite) {
        nextKeys.delete(key);
        setFavoriteKeys(nextKeys);
        await deleteUserWatchlistItem({ ...row, asset_type: assetType });
      } else {
        nextKeys.add(key);
        setFavoriteKeys(nextKeys);
        await upsertUserWatchlistItem({ ...row, asset_type: assetType });
      }
    } catch (error) {
      await loadFavorites();
      alert(error.message || '관심종목 저장 중 문제가 발생했습니다.');
    }
  };

  const loadOverview = async (requestFilters = stockFilters, requestCoinFilters = coinFilters) => {
      try {
        setStatus("loading");
        const currentMarketState = getKoreanMarketState();
        setMarketState(currentMarketState);
        const response = await fetch("http://localhost:5050/api/home/market", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ filters: requestFilters, coinFilters: requestCoinFilters }),
        });

        const data = await response.json();
        if (!response.ok || !data.success) {
          throw new Error(data.message || "홈 시세를 불러오지 못했습니다.");
        }

        const stockRows = Array.isArray(data.data?.stocks) ? data.data.stocks : [];
        const marketSnapshot = data.data?.market_snapshot || {};
        setStockCandidates(stockRows);
        setCoins(Array.isArray(data.data?.coins) ? data.data.coins : []);
        setSnapshotMeta(marketSnapshot);
        const unsupportedHorizon = requestFilters.horizon !== "실시간"
          ? "기간별 랭킹은 아직 지원하지 않아 실시간 기준으로 표시됩니다."
          : "";
        setMessage([data.data?.message || "", unsupportedHorizon].filter(Boolean).join(" "));
        setUpdatedAt(new Date().toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
        setStatus("ready");
      } catch (error) {
        setStockCandidates([]);
        setCoins([]);
        setSnapshotMeta({});
        setMessage(error.message || "홈 데이터를 불러오지 못했습니다.");
        setStatus("error");
      }
    };

  const refreshOverview = () => {
    loadOverview({
      region: stockFilters.region,
      ranking: stockFilters.ranking,
      horizon: stockFilters.horizon,
      forceRefresh: true,
    }, coinFilters);
  };
  const snapshotTimeText = snapshotMeta.as_of ? ` · 데이터 기준 ${formatSnapshotTime(snapshotMeta.as_of)}` : "";
  const checkedTimeText = updatedAt ? ` · 확인 ${updatedAt}` : "";
  const marketStatusText = message
    || (status === "loading"
      ? "시장 데이터를 불러오는 중입니다."
      : `시장 데이터 정상 표시 중${snapshotTimeText}${checkedTimeText}`);

  useEffect(() => {
    loadFavorites();
  }, [isLoggedIn]);

  useEffect(() => {
    let timeoutId;
    let cancelled = false;
    const requestFilters = {
      region: stockFilters.region,
      ranking: stockFilters.ranking,
      horizon: stockFilters.horizon,
    };
    const requestCoinFilters = {
      ranking: coinFilters.ranking,
    };

    const scheduleNextLoad = () => {
      const currentMarketState = getKoreanMarketState();
      setMarketState(currentMarketState);
      const delay = currentMarketState.isOpen ? 60_000 : 600_000;
      timeoutId = window.setTimeout(async () => {
        if (cancelled) return;
        await loadOverview(requestFilters, requestCoinFilters);
        if (!cancelled) scheduleNextLoad();
      }, delay);
    };

    loadOverview(requestFilters, requestCoinFilters).then(() => {
      if (!cancelled) scheduleNextLoad();
    });

    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
    };
  }, [stockFilters.region, stockFilters.ranking, stockFilters.horizon, coinFilters.ranking]);

  return (
    <div className="min-h-screen bg-obsidian-bg text-[#e2e2ec] font-inter">
      <div className="px-4 py-4 sm:px-6 sm:py-6">
        <Header isLoggedIn={isLoggedIn} userEmail={userEmail} handleLogout={handleLogout} />

        <main className="mx-auto flex w-full max-w-7xl flex-col gap-6">
          <section className="ai-glass rounded-lg p-4 sm:p-6">
            <div className="flex flex-col gap-4">
              <div className="flex flex-col gap-3">
                <div className="grid gap-3 xl:grid-cols-2">
                  <FilterBar title="주식 필터">
                    {filters.region.map((label) => (
                      <FilterChip
                        key={`stock-region-${label}`}
                        label={label}
                        active={stockFilters.region === label}
                        onClick={() => setStockFilters((prev) => ({
                          ...prev,
                          region: label,
                          ranking: label === "해외" && prev.ranking === "거래대금" ? "거래량" : prev.ranking,
                        }))}
                      />
                    ))}
                    <span className="mx-1 hidden h-7 w-px bg-slate-700 md:block" />
                    {stockRankingOptions.map((label) => (
                      <FilterChip
                        key={`stock-ranking-${label}`}
                        label={label}
                        active={stockFilters.ranking === label}
                        onClick={() => setStockFilters((prev) => ({ ...prev, ranking: label }))}
                      />
                    ))}
                  </FilterBar>

                  <FilterBar title="코인 필터">
                    {filters.ranking.map((label) => (
                      <FilterChip
                        key={`coin-ranking-${label}`}
                        label={label}
                        active={coinFilters.ranking === label}
                        onClick={() => setCoinFilters((prev) => ({ ...prev, ranking: label }))}
                      />
                    ))}
                  </FilterBar>
                </div>

                <div className="text-right text-xs text-slate-500">
                  {status === "loading"
                    ? "LOADING"
                    : marketState.label}
                </div>
              </div>
            </div>
          </section>

          <section className="grid grid-cols-1 gap-5 xl:grid-cols-2">
            <div className="xl:col-span-2 flex flex-col gap-3 rounded-lg border border-slate-700 bg-[#061321]/80 px-4 py-3 text-sm text-slate-300 sm:flex-row sm:items-center sm:justify-between">
              <span className="min-w-0 break-words">{marketStatusText}</span>
              <button
                type="button"
                onClick={refreshOverview}
                disabled={status === "loading"}
                className="h-8 shrink-0 rounded border border-ai-cyan/70 px-3 text-xs font-bold text-ai-cyan transition hover:bg-ai-cyan/10 disabled:cursor-not-allowed disabled:border-slate-700 disabled:text-slate-500"
              >
                새로고침
              </button>
            </div>
            <div className="hidden md:block">
              <MarketTable rows={stocks} titleType="stock" ranking={stockFilters.ranking} favoriteKeys={favoriteKeys} onToggleFavorite={handleToggleFavorite} moreHref={stockMoreHref} />
            </div>
            <MobileMarketTable rows={stocks} titleType="stock" ranking={stockFilters.ranking} favoriteKeys={favoriteKeys} onToggleFavorite={handleToggleFavorite} />
            <Link to={stockMoreHref} className="rounded-lg border border-slate-700 bg-[#061321]/90 px-4 py-3 text-center text-sm font-medium text-slate-200 no-underline transition hover:bg-white/[0.03] md:hidden">
              더보기
            </Link>

            <div className="hidden md:block">
              <MarketTable rows={filteredCoins} titleType="coin" ranking={coinFilters.ranking} favoriteKeys={favoriteKeys} onToggleFavorite={handleToggleFavorite} moreHref={coinMoreHref} />
            </div>
            <MobileMarketTable rows={filteredCoins} titleType="coin" ranking={coinFilters.ranking} favoriteKeys={favoriteKeys} onToggleFavorite={handleToggleFavorite} />
            <Link to={coinMoreHref} className="rounded-lg border border-slate-700 bg-[#061321]/90 px-4 py-3 text-center text-sm font-medium text-slate-200 no-underline transition hover:bg-white/[0.03] md:hidden">
              더보기
            </Link>
          </section>

        </main>
      </div>
    </div>
  );
}
