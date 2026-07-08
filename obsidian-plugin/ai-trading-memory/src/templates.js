const AUTO_MEMORY_FAVORITES_MARKER = "favorite-symbols";
const AUTO_MEMORY_MISTAKES_MARKER = "repeated-mistakes";

function buildTemplateFiles(syncFolder = "AI-Trading") {
  const folder = normalizeFolder(syncFolder);
  return [
    {
      path: `${folder}/00_나의_투자원칙.md`,
      content: withFrontmatter(
        {
          source: "ai-trading",
          template_key: "investing-principles",
          sync_id: "",
          symbol: "",
          market: "",
          tags: ["ai-trading", "principle"],
        },
        [
          "# 나의 투자 원칙",
          "",
          "## 투자 목표",
          "- ",
          "",
          "## 선호 시장",
          "- 국내주식:",
          "- 미국주식:",
          "- 코인:",
          "",
          "## 피해야 할 매매",
          "- ",
          "",
          "## 1회 투자 한도",
          "- ",
          "",
          "## 손절 기준",
          "- ",
          "",
          "## 익절 기준",
          "- ",
          "",
          "## AI에게 바라는 답변 방식",
          "- ",
        ].join("\n"),
      ),
    },
    {
      path: `${folder}/01_매매전_체크리스트.md`,
      content: withFrontmatter(
        {
          source: "ai-trading",
          template_key: "pre-trade-checklist",
          sync_id: "",
          symbol: "",
          market: "",
          tags: ["ai-trading", "checklist"],
        },
        [
          "# 매매 전 체크리스트",
          "",
          "## 현재 판단",
          "- 매수 / 매도 / 보류:",
          "",
          "## 근거",
          "- ",
          "",
          "## 반대 근거",
          "- ",
          "",
          "## 손절 기준",
          "- ",
          "",
          "## 익절 기준",
          "- ",
          "",
          "## 지금 안 해도 되는 이유",
          "- ",
        ].join("\n"),
      ),
    },
    {
      path: `${folder}/02_손실회고.md`,
      content: withFrontmatter(
        {
          source: "ai-trading",
          template_key: "loss-review",
          sync_id: "",
          symbol: "",
          market: "",
          tags: ["ai-trading", "review"],
        },
        [
          "# 손실 회고",
          "",
          "## 종목",
          "- ",
          "",
          "## 진입 이유",
          "- ",
          "",
          "## 손실 원인",
          "- ",
          "",
          "## 놓친 신호",
          "- ",
          "",
          "## 다음에 바꿀 규칙",
          "- ",
          "",
          "## 다시 같은 상황이면?",
          "- ",
        ].join("\n"),
      ),
    },
    {
      path: `${folder}/자동메모리/관심종목_자동요약.md`,
      content: withFrontmatter(
        {
          source: "ai-trading",
          template_key: "auto-memory-favorite-symbols",
          sync_id: "",
          symbol: "",
          market: "",
          tags: ["ai-trading", "auto-memory"],
        },
        [
          "# 관심종목 자동요약",
          "",
          markerBlock(AUTO_MEMORY_FAVORITES_MARKER, ["- 아직 앱에서 가져온 관심종목 요약이 없습니다."]),
          "",
          "## 내 메모",
          "여기는 사용자가 자유롭게 작성합니다.",
        ].join("\n"),
      ),
    },
    {
      path: `${folder}/자동메모리/반복실수_자동요약.md`,
      content: withFrontmatter(
        {
          source: "ai-trading",
          template_key: "auto-memory-repeated-mistakes",
          sync_id: "",
          symbol: "",
          market: "",
          tags: ["ai-trading", "auto-memory"],
        },
        [
          "# 반복실수 자동요약",
          "",
          markerBlock(AUTO_MEMORY_MISTAKES_MARKER, ["- 아직 앱에서 가져온 반복실수 요약이 없습니다."]),
          "",
          "## 내 메모",
          "여기는 사용자가 자유롭게 작성합니다.",
        ].join("\n"),
      ),
    },
    {
      path: `${folder}/종목분석/README.md`,
      content: withFrontmatter(
        {
          source: "ai-trading",
          template_key: "symbol-analysis-index",
          sync_id: "",
          symbol: "",
          market: "",
          tags: ["ai-trading", "symbol-analysis"],
        },
        [
          "# 종목분석 노트",
          "",
          "이 폴더에는 종목별 투자 아이디어, 긍정 요인, 리스크 요인, 진입 조건을 기록합니다.",
          "",
          "## 새 종목 노트 권장 형식",
          "- 파일명: 종목명_심볼.md",
          "- 예시: 삼성전자_005930.md",
        ].join("\n"),
      ),
    },
  ];
}

function markerBlock(markerKey, lines) {
  return [
    `<!-- ai-trading:${markerKey}:start -->`,
    ...lines,
    `<!-- ai-trading:${markerKey}:end -->`,
  ].join("\n");
}

function withFrontmatter(frontmatter, body) {
  const lines = ["---"];
  for (const [key, value] of Object.entries(frontmatter)) {
    if (Array.isArray(value)) {
      lines.push(`${key}: [${value.join(", ")}]`);
    } else {
      lines.push(`${key}: ${value}`);
    }
  }
  lines.push("---", "", body);
  return lines.join("\n");
}

function normalizeFolder(syncFolder) {
  return String(syncFolder || "AI-Trading").replace(/^\/+|\/+$/g, "") || "AI-Trading";
}

module.exports = {
  AUTO_MEMORY_FAVORITES_MARKER,
  AUTO_MEMORY_MISTAKES_MARKER,
  buildTemplateFiles,
  markerBlock,
  normalizeFolder,
  withFrontmatter,
};
