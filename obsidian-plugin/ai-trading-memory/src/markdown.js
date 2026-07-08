const crypto = require("crypto");

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
    return inner.split(",").map((item) => stripQuotes(item.trim())).filter(Boolean);
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

module.exports = {
  buildSyncPayload,
  extractTitle,
  parseFrontmatter,
  sha256,
};
