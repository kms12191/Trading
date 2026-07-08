const assert = require("node:assert/strict");
const test = require("node:test");

const { buildTemplateFiles } = require("../src/templates");

test("buildTemplateFiles creates the internal demo vault structure", () => {
  const files = buildTemplateFiles("AI-Trading");
  const paths = files.map((file) => file.path).sort();

  assert.deepEqual(paths, [
    "AI-Trading/00_나의_투자원칙.md",
    "AI-Trading/01_매매전_체크리스트.md",
    "AI-Trading/02_손실회고.md",
    "AI-Trading/자동메모리/관심종목_자동요약.md",
    "AI-Trading/자동메모리/반복실수_자동요약.md",
    "AI-Trading/종목분석/README.md",
  ]);
});

test("auto memory templates contain protected marker blocks", () => {
  const files = buildTemplateFiles("AI-Trading");
  const autoMemoryFiles = files.filter((file) => file.path.includes("자동메모리"));

  assert.equal(autoMemoryFiles.length, 2);
  for (const file of autoMemoryFiles) {
    assert.match(file.content, /<!-- ai-trading:[a-z-]+:start -->/);
    assert.match(file.content, /<!-- ai-trading:[a-z-]+:end -->/);
    assert.match(file.content, /## 내 메모/);
  }
});
