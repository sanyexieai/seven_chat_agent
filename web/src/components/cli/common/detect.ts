function looksLikeJsonLine(line: string): boolean {
  const t = line.trim();
  if (!t) return false;
  if (!(t.startsWith("{") || t.startsWith("["))) return false;
  try {
    JSON.parse(t);
    return true;
  } catch {
    return false;
  }
}

export function isJsonlContent(content: string): boolean {
  const lines = content
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
  if (lines.length < 2) return false;
  const ok = lines.filter(looksLikeJsonLine).length;
  return ok >= Math.ceil(lines.length * 0.7);
}

export function isJsonContent(content: string): boolean {
  const t = content.trim();
  if (!t) return false;
  if (!(t.startsWith("{") || t.startsWith("["))) return false;
  try {
    JSON.parse(t);
    return true;
  } catch {
    return false;
  }
}

export function isJsonishContent(content: string): boolean {
  return isJsonContent(content) || isJsonlContent(content);
}

