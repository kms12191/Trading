const assert = require("node:assert/strict");
const test = require("node:test");

const { replaceMarkerBlock } = require("../src/marker");

test("replaceMarkerBlock updates only the protected marker area", () => {
  const original = [
    "# 관심종목 자동요약",
    "",
    "<!-- ai-trading:auto-memory:start -->",
    "- 기존 자동 요약",
    "<!-- ai-trading:auto-memory:end -->",
    "",
    "## 내 메모",
    "사용자가 직접 작성한 내용",
  ].join("\n");

  const updated = replaceMarkerBlock(original, "auto-memory", ["- 새 자동 요약"]);

  assert.match(updated, /- 새 자동 요약/);
  assert.doesNotMatch(updated, /- 기존 자동 요약/);
  assert.match(updated, /## 내 메모\n사용자가 직접 작성한 내용/);
});

test("replaceMarkerBlock appends marker block when missing", () => {
  const updated = replaceMarkerBlock("# 노트\n\n사용자 본문", "auto-memory", ["- 자동 요약"]);

  assert.match(updated, /사용자 본문/);
  assert.match(updated, /<!-- ai-trading:auto-memory:start -->/);
  assert.match(updated, /- 자동 요약/);
  assert.match(updated, /<!-- ai-trading:auto-memory:end -->/);
});
