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

module.exports = {
  getJson,
  normalizeBaseUrl,
  postJson,
};
