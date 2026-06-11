import type {
  FrameworkBinding,
  ProfileFrameworkCatalog,
} from "./types/profile";

/** 从已绑定 framework 合并允许的 extensions 字段名 */
export function allowedExtensionKeys(
  frameworks: FrameworkBinding[] | undefined,
  catalogs: ProfileFrameworkCatalog[],
): string[] {
  const keys = new Set<string>();
  for (const fb of frameworks ?? []) {
    const cat = catalogs.find((c) => c.id === fb.id);
    const props = cat?.extensions_schema?.properties;
    if (!props) continue;
    for (const k of Object.keys(props)) keys.add(k);
  }
  return [...keys].sort();
}

export function extensionFieldHint(
  key: string,
  frameworks: FrameworkBinding[] | undefined,
  catalogs: ProfileFrameworkCatalog[],
): string | null {
  for (const fb of frameworks ?? []) {
    const cat = catalogs.find((c) => c.id === fb.id);
    const spec = cat?.extensions_schema?.properties?.[key];
    if (!spec) continue;
    const parts = [spec.type];
    if (spec.enum?.length) {
      parts.push(`enum: ${spec.enum.map(String).join("|")}`);
    }
    if (spec.max_length) parts.push(`max ${spec.max_length}`);
    return parts.join(" · ");
  }
  return null;
}
