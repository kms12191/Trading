import { useState, useEffect } from "react";

/**
 * 자산(주식/가상자산)의 로고 이미지 URL을 반환하는 헬퍼 함수
 */
export function getAssetLogoUrl(symbol, assetType) {
  if (!symbol) return null;
  
  const cleanSymbol = String(symbol).trim();
  const upperType = String(assetType || "").toUpperCase();

  if (upperType === "CRYPTO") {
    // 가상자산 로고 CDN (spothq cryptocurrency-icons) - 소문자 기호
    return `https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/128/color/${cleanSymbol.toLowerCase()}.png`;
  } else {
    // 토스증권 주식 이미지 CDN - 대문자 기호/종목코드
    return `https://static.toss.im/png-icons/securities/icn-sec-fill-${cleanSymbol.toUpperCase()}.png`;
  }
}

/**
 * 주식 및 가상자산 로고를 렌더링하는 공용 컴포넌트
 * 이미지 로드에 실패할 경우, 기존의 2글자 텍스트 그라디언트 배지(Fallback)를 표시합니다.
 */
export default function AssetLogo({ symbol, assetType, name, size = "h-9 w-9", className = "" }) {
  const [failedUrl, setFailedUrl] = useState("");
  const logoUrl = getAssetLogoUrl(symbol, assetType);
  const displayName = name || symbol || "?";
  
  // 2글자 이니셜 추출
  const initialText = String(displayName)
    .trim()
    .slice(0, 2)
    .toUpperCase();

  // symbol 이 변경될 경우 에러 상태 초기화
  useEffect(() => {
    setFailedUrl("");
  }, [logoUrl]);

  if (logoUrl && failedUrl !== logoUrl) {
    return (
      <img
        src={logoUrl}
        alt={displayName}
        onError={() => setFailedUrl(logoUrl)}
        className={`${size} shrink-0 rounded-full object-cover transition-opacity duration-200 ${className}`}
      />
    );
  }

  // Fallback UI (기존 RankIcon 스타일 준수)
  return (
    <div
      className={`grid ${size} shrink-0 place-items-center rounded-full bg-gradient-to-br from-ai-cyan/90 to-blue-700 text-[10px] font-black text-white shadow-[0_0_18px_rgba(0,224,255,0.18)] ${className}`}
    >
      {initialText}
    </div>
  );
}
