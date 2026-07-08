const assert = require("node:assert/strict");
const test = require("node:test");

const { buildSyncPayload, parseFrontmatter } = require("../src/markdown");

test("parseFrontmatter extracts yaml-like scalar and list values", () => {
  const parsed = parseFrontmatter([
    "---",
    "source: ai-trading",
    "template_key: investing-principles",
    "symbol: 005930",
    "market: KR",
    "tags: [ai-trading, principle]",
    "---",
    "# 나의 투자 원칙",
  ].join("\n"));

  assert.equal(parsed.frontmatter.source, "ai-trading");
  assert.equal(parsed.frontmatter.template_key, "investing-principles");
  assert.equal(parsed.frontmatter.symbol, "005930");
  assert.deepEqual(parsed.frontmatter.tags, ["ai-trading", "principle"]);
  assert.equal(parsed.body, "# 나의 투자 원칙");
});

test("buildSyncPayload returns stable hash and title", () => {
  const payload = buildSyncPayload({
    vaultName: "Demo Vault",
    filePath: "AI-Trading/00_나의_투자원칙.md",
    content: "---\ntemplate_key: investing-principles\n---\n# 나의 투자 원칙\n내용",
    modifiedAt: "2026-07-08T12:00:00.000Z",
  });

  assert.equal(payload.vault_name, "Demo Vault");
  assert.equal(payload.file_path, "AI-Trading/00_나의_투자원칙.md");
  assert.equal(payload.title, "나의 투자 원칙");
  assert.equal(payload.frontmatter.template_key, "investing-principles");
  assert.equal(payload.content_hash.length, 64);
  assert.equal(payload.modified_at, "2026-07-08T12:00:00.000Z");
});
