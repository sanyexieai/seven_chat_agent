/** 下拉框等展示用：去掉名称末尾历史的「(本地)」后缀 */
export function providerDisplayName(raw: string | null | undefined): string {
  if (!raw) return "";
  const t = raw.trim().replace(/\s*[(（]本地[)）]\s*$/u, "").trim();
  return t || raw.trim();
}

/** 内置 Provider 的默认 Base URL（仅作「填入默认」提示，保存后以数据库为准） */
export const DEFAULT_PROVIDER_BASE_URLS: Record<string, string> = {
  openai: "https://api.openai.com/v1",
  anthropic: "https://api.anthropic.com",
  gemini: "https://generativelanguage.googleapis.com/v1beta",
  deepseek: "https://api.deepseek.com/v1",
  qwen: "https://dashscope.aliyuncs.com/compatible-mode/v1",
  moonshot: "https://api.moonshot.cn/v1",
  openrouter: "https://openrouter.ai/api/v1",
  ollama: "http://localhost:11434",
  lmstudio: "http://localhost:1234/v1",
  vllm: "http://localhost:8000/v1",
};

/** 按 kind 的通用默认（新建自定义 Provider 时用） */
export const DEFAULT_BASE_URL_BY_KIND: Record<string, string> = {
  openai_compat: "https://api.openai.com/v1",
  anthropic: "https://api.anthropic.com",
  gemini: "https://generativelanguage.googleapis.com/v1beta",
  ollama: "http://localhost:11434",
};

export function defaultBaseUrlForProvider(
  providerId: string,
  kind: string,
): string {
  return (
    DEFAULT_PROVIDER_BASE_URLS[providerId] ??
    DEFAULT_BASE_URL_BY_KIND[kind] ??
    ""
  );
}
