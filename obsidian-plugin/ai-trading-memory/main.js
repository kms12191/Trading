const crypto = require("crypto");
const { Notice, Plugin, PluginSettingTab, Setting } = require("obsidian");

const AUTO_MEMORY_FAVORITES_MARKER = "favorite-symbols";
const AUTO_MEMORY_MISTAKES_MARKER = "repeated-mistakes";

const DEFAULT_SETTINGS = {
  apiBaseUrl: "http://localhost:5050",
  testToken: "",
  syncFolder: "AI-Trading",
  enableAutoMemoryPull: true,
};

module.exports = class AiTradingMemoryPlugin extends Plugin {
  async onload() {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
    this.addSettingTab(new AiTradingMemorySettingTab(this.app, this));

    this.addCommand({
      id: "create-ai-trading-templates",
      name: "기본 투자노트 템플릿 생성",
      callback: () => this.createTemplateFiles(),
    });

    this.addCommand({
      id: "sync-current-note-to-ai-trading",
      name: "현재 노트 앱으로 동기화",
      checkCallback: (checking) => {
        const file = this.app.workspace.getActiveFile();
        if (!file || file.extension !== "md") {
          return false;
        }
        if (!checking) {
          void this.syncCurrentNote();
        }
        return true;
      },
    });

    this.addCommand({
      id: "sync-ai-trading-folder",
      name: "AI-Trading 폴더 전체 동기화",
      callback: () => this.syncFolder(),
    });

    this.addCommand({
      id: "pull-ai-trading-auto-memory",
      name: "자동메모리 가져오기",
      callback: () => this.pullAutoMemory(),
    });
  }

  async saveSettings() {
    await this.saveData(this.settings);
  }

  async createTemplateFiles() {
    const files = buildTemplateFiles(this.settings.syncFolder);
    let created = 0;
    let skipped = 0;

    for (const file of files) {
      const existing = this.app.vault.getAbstractFileByPath(file.path);
      if (existing) {
        skipped += 1;
        continue;
      }
      await this.ensureFolder(file.path);
      await this.app.vault.create(file.path, file.content);
      created += 1;
    }

    new Notice(`AI Trading 템플릿 생성 완료: 신규 ${created}개, 기존 ${skipped}개`);
  }

  async syncCurrentNote() {
    const file = this.app.workspace.getActiveFile();
    if (!file || file.extension !== "md") {
      new Notice("동기화할 Markdown 노트를 열어 주세요.");
      return;
    }
    const content = await this.app.vault.read(file);
    const result = await this.syncNoteFile(file, content);
    new Notice(`현재 노트 동기화 완료: ${result.status || "SUCCESS"}`);
  }

  async syncFolder() {
    const syncFolder = normalizeFolder(this.settings.syncFolder);
    const markdownFiles = this.app.vault
      .getMarkdownFiles()
      .filter((file) => file.path === `${syncFolder}.md` || file.path.startsWith(`${syncFolder}/`));

    if (markdownFiles.length === 0) {
      new Notice(`${syncFolder} 폴더에 동기화할 Markdown 노트가 없습니다.`);
      return;
    }

    let successCount = 0;
    let failedCount = 0;
    for (const file of markdownFiles) {
      try {
        const content = await this.app.vault.read(file);
        await this.syncNoteFile(file, content);
        successCount += 1;
      } catch (error) {
        failedCount += 1;
      }
    }

    new Notice(`폴더 동기화 완료: 성공 ${successCount}개, 실패 ${failedCount}개`);
  }

  async syncNoteFile(file, content) {
    const stat = file.stat || {};
    const payload = buildSyncPayload({
      vaultName: this.app.vault.getName(),
      filePath: file.path,
      content,
      modifiedAt: stat.mtime ? new Date(stat.mtime).toISOString() : new Date().toISOString(),
    });

    return postJson({
      apiBaseUrl: this.settings.apiBaseUrl,
      testToken: this.settings.testToken,
      path: "/api/knowledge/obsidian/sync-note",
      body: payload,
    });
  }

  async pullAutoMemory() {
    if (!this.settings.enableAutoMemoryPull) {
      new Notice("자동메모리 가져오기가 비활성화되어 있습니다.");
      return;
    }

    const data = await getJson({
      apiBaseUrl: this.settings.apiBaseUrl,
      testToken: this.settings.testToken,
      path: "/api/knowledge/obsidian/auto-memory",
    });

    const syncFolder = normalizeFolder(this.settings.syncFolder);
    await this.updateAutoMemoryFile({
      path: `${syncFolder}/자동메모리/관심종목_자동요약.md`,
      markerKey: AUTO_MEMORY_FAVORITES_MARKER,
      lines: toBulletLines(data.favorite_symbols),
      fallbackTitle: "# 관심종목 자동요약",
    });
    await this.updateAutoMemoryFile({
      path: `${syncFolder}/자동메모리/반복실수_자동요약.md`,
      markerKey: AUTO_MEMORY_MISTAKES_MARKER,
      lines: toBulletLines(data.repeated_mistakes || data.risk_preferences),
      fallbackTitle: "# 반복실수 자동요약",
    });

    new Notice("자동메모리 가져오기 완료");
  }

  async updateAutoMemoryFile({ path, markerKey, lines, fallbackTitle }) {
    const existing = this.app.vault.getAbstractFileByPath(path);
    const initialContent = [fallbackTitle, "", "## 내 메모", "여기는 사용자가 자유롭게 작성합니다."].join("\n");

    if (!existing) {
      await this.ensureFolder(path);
      await this.app.vault.create(path, replaceMarkerBlock(initialContent, markerKey, lines));
      return;
    }

    const content = await this.app.vault.read(existing);
    const updated = replaceMarkerBlock(content, markerKey, lines);
    await this.app.vault.modify(existing, updated);
  }

  async ensureFolder(filePath) {
    const segments = filePath.split("/").slice(0, -1);
    let current = "";
    for (const segment of segments) {
      current = current ? `${current}/${segment}` : segment;
      if (!this.app.vault.getAbstractFileByPath(current)) {
        await this.app.vault.createFolder(current);
      }
    }
  }
};

class AiTradingMemorySettingTab extends PluginSettingTab {
  constructor(app, plugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display() {
    const { containerEl } = this;
    containerEl.empty();
    containerEl.createEl("h2", { text: "AI Trading Memory" });

    new Setting(containerEl)
      .setName("API Base URL")
      .setDesc("내부 시연용 Flask API 주소입니다.")
      .addText((text) =>
        text
          .setPlaceholder("http://localhost:5050")
          .setValue(this.plugin.settings.apiBaseUrl)
          .onChange(async (value) => {
            this.plugin.settings.apiBaseUrl = value.trim();
            await this.plugin.saveSettings();
          }),
      );

    new Setting(containerEl)
      .setName("테스트 토큰")
      .setDesc("내부 시연용 Bearer 토큰입니다.")
      .addText((text) =>
        text
          .setPlaceholder("paste-test-token")
          .setValue(this.plugin.settings.testToken)
          .onChange(async (value) => {
            this.plugin.settings.testToken = value.trim();
            await this.plugin.saveSettings();
          }),
      );

    new Setting(containerEl)
      .setName("동기화 폴더")
      .setDesc("플러그인이 관리할 Vault 내 폴더명입니다.")
      .addText((text) =>
        text
          .setPlaceholder("AI-Trading")
          .setValue(this.plugin.settings.syncFolder)
          .onChange(async (value) => {
            this.plugin.settings.syncFolder = normalizeFolder(value);
            await this.plugin.saveSettings();
          }),
      );

    new Setting(containerEl)
      .setName("자동메모리 가져오기")
      .setDesc("앱에서 생성한 자동메모리를 marker 영역에 반영합니다.")
      .addToggle((toggle) =>
        toggle.setValue(this.plugin.settings.enableAutoMemoryPull).onChange(async (value) => {
          this.plugin.settings.enableAutoMemoryPull = value;
          await this.plugin.saveSettings();
        }),
      );
  }
}

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

function parseFrontmatter(markdown) {
  const content = String(markdown || "").replace(/\r\n/g, "\n");
  if (!content.startsWith("---\n")) {
    return { frontmatter: {}, body: content.trim() };
  }

  const match = content.match(/^---\n([\s\S]*?)\n---\n?([\s\S]*)$/);
  if (!match) {
    return { frontmatter: {}, body: content.trim() };
  }

  return {
    frontmatter: parseFrontmatterBody(match[1]),
    body: match[2].trim(),
  };
}

function buildSyncPayload({ vaultName, filePath, content, modifiedAt }) {
  const normalizedContent = String(content || "").replace(/\r\n/g, "\n");
  const parsed = parseFrontmatter(normalizedContent);
  return {
    sync_id: parsed.frontmatter.sync_id || "",
    vault_name: String(vaultName || "").trim(),
    file_path: String(filePath || "").trim(),
    title: extractTitle(parsed.body, filePath),
    content: normalizedContent,
    frontmatter: parsed.frontmatter,
    content_hash: sha256(normalizedContent),
    modified_at: modifiedAt || new Date().toISOString(),
  };
}

function parseFrontmatterBody(body) {
  const result = {};
  for (const rawLine of String(body || "").split("\n")) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) {
      continue;
    }
    const delimiterIndex = line.indexOf(":");
    if (delimiterIndex === -1) {
      continue;
    }
    const key = line.slice(0, delimiterIndex).trim();
    const rawValue = line.slice(delimiterIndex + 1).trim();
    result[key] = parseFrontmatterValue(rawValue);
  }
  return result;
}

function parseFrontmatterValue(rawValue) {
  if (rawValue.startsWith("[") && rawValue.endsWith("]")) {
    const inner = rawValue.slice(1, -1).trim();
    if (!inner) {
      return [];
    }
    return inner
      .split(",")
      .map((item) => stripQuotes(item.trim()))
      .filter(Boolean);
  }
  return stripQuotes(rawValue);
}

function stripQuotes(value) {
  return String(value || "").replace(/^['"]|['"]$/g, "");
}

function extractTitle(body, filePath) {
  for (const line of String(body || "").split("\n")) {
    if (line.startsWith("# ")) {
      return line.slice(2).trim();
    }
  }
  const fileName = String(filePath || "Untitled.md").split("/").pop() || "Untitled.md";
  return fileName.replace(/\.md$/i, "") || "Untitled";
}

function sha256(value) {
  return crypto.createHash("sha256").update(String(value || ""), "utf8").digest("hex");
}

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

function markerBlock(markerKey, lines) {
  return [`<!-- ai-trading:${markerKey}:start -->`, ...lines, `<!-- ai-trading:${markerKey}:end -->`].join("\n");
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

async function postJson({ apiBaseUrl, testToken, path, body }) {
  const baseUrl = normalizeBaseUrl(apiBaseUrl);
  if (!baseUrl) {
    throw new Error("API Base URL을 설정해 주세요.");
  }
  if (!testToken) {
    throw new Error("내부 시연용 테스트 토큰을 설정해 주세요.");
  }

  const response = await fetch(`${baseUrl}${path}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${testToken}`,
      "Content-Type": "application/json",
      "X-AI-Trading-Plugin": "obsidian-internal-demo",
    },
    body: JSON.stringify(body),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.success === false) {
    throw new Error(payload.message || `API 요청 실패: ${response.status}`);
  }
  return payload.data || payload;
}

async function getJson({ apiBaseUrl, testToken, path }) {
  const baseUrl = normalizeBaseUrl(apiBaseUrl);
  if (!baseUrl) {
    throw new Error("API Base URL을 설정해 주세요.");
  }
  if (!testToken) {
    throw new Error("내부 시연용 테스트 토큰을 설정해 주세요.");
  }

  const response = await fetch(`${baseUrl}${path}`, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${testToken}`,
      "X-AI-Trading-Plugin": "obsidian-internal-demo",
    },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.success === false) {
    throw new Error(payload.message || `API 요청 실패: ${response.status}`);
  }
  return payload.data || payload;
}

function normalizeBaseUrl(apiBaseUrl) {
  return String(apiBaseUrl || "").trim().replace(/\/+$/g, "");
}

function normalizeFolder(syncFolder) {
  return String(syncFolder || "AI-Trading").replace(/^\/+|\/+$/g, "") || "AI-Trading";
}

function toBulletLines(values) {
  const items = Array.isArray(values) ? values : [];
  const lines = items.map((item) => String(item || "").trim()).filter(Boolean);
  if (lines.length === 0) {
    return ["- 앱에서 가져온 자동메모리가 없습니다."];
  }
  return lines.map((line) => (line.startsWith("- ") ? line : `- ${line}`));
}

module.exports.DEFAULT_SETTINGS = DEFAULT_SETTINGS;
