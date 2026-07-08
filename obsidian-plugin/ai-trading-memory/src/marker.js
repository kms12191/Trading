function replaceMarkerBlock(markdown, markerKey, replacementLines) {
  const content = String(markdown || "");
  const safeLines = normalizeReplacementLines(replacementLines);
  const block = buildMarkerBlock(markerKey, safeLines);
  const pattern = new RegExp(
    `<!--\\s*ai-trading:${escapeRegExp(markerKey)}:start\\s*-->[\\s\\S]*?<!--\\s*ai-trading:${escapeRegExp(markerKey)}:end\\s*-->`,
    "m",
  );

  if (pattern.test(content)) {
    return content.replace(pattern, block);
  }

  const separator = content.endsWith("\n") || content.length === 0 ? "" : "\n";
  return `${content}${separator}\n${block}\n`;
}

function buildMarkerBlock(markerKey, lines) {
  return [
    `<!-- ai-trading:${markerKey}:start -->`,
    ...normalizeReplacementLines(lines),
    `<!-- ai-trading:${markerKey}:end -->`,
  ].join("\n");
}

function normalizeReplacementLines(lines) {
  if (!Array.isArray(lines) || lines.length === 0) {
    return ["- 가져온 자동메모리가 없습니다."];
  }
  return lines.map((line) => String(line || "").trim()).filter(Boolean);
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

module.exports = {
  buildMarkerBlock,
  replaceMarkerBlock,
};
