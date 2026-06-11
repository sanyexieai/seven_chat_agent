import type {
  FrameworkBinding,
  ProfileFrameworkCatalog,
} from "../types/profile";
import { extensionFieldHint } from "../profileUtils";

interface Props {
  frameworks: FrameworkBinding[] | undefined;
  catalogs: ProfileFrameworkCatalog[];
  keys: string[];
  value: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
}

function specFor(
  key: string,
  frameworks: FrameworkBinding[] | undefined,
  catalogs: ProfileFrameworkCatalog[],
) {
  for (const fb of frameworks ?? []) {
    const cat = catalogs.find((c) => c.id === fb.id);
    const spec = cat?.extensions_schema?.properties?.[key];
    if (spec) return spec;
  }
  return undefined;
}

export function ExtensionFieldsForm({
  frameworks,
  catalogs,
  keys,
  value,
  onChange,
}: Props) {
  if (keys.length === 0) return null;

  function setField(key: string, fieldValue: unknown) {
    const next = { ...value };
    if (
      fieldValue === "" ||
      fieldValue === undefined ||
      fieldValue === null
    ) {
      delete next[key];
    } else {
      next[key] = fieldValue;
    }
    onChange(next);
  }

  return (
    <div className="space-y-2">
      {keys.map((key) => {
        const spec = specFor(key, frameworks, catalogs);
        const hint = extensionFieldHint(key, frameworks, catalogs);
        const current = value[key];
        const label = (
          <span className="text-xs font-medium text-slate-700">
            {key}
            {hint && (
              <span className="ml-1 font-normal text-slate-400">({hint})</span>
            )}
          </span>
        );

        if (spec?.enum?.length) {
          return (
            <div key={key}>
              <label className="label">{label}</label>
              <select
                className="input text-sm"
                value={current != null ? String(current) : ""}
                onChange={(e) =>
                  setField(key, e.target.value ? e.target.value : undefined)
                }
              >
                <option value="">（未设置）</option>
                {spec.enum.map((v, i) => (
                  <option key={i} value={String(v)}>
                    {String(v)}
                  </option>
                ))}
              </select>
            </div>
          );
        }

        if (spec?.type === "boolean") {
          return (
            <label
              key={key}
              className="flex cursor-pointer items-center gap-2 text-xs text-slate-700"
            >
              <input
                type="checkbox"
                checked={Boolean(current)}
                onChange={(e) => setField(key, e.target.checked)}
              />
              {label}
            </label>
          );
        }

        if (spec?.type === "number") {
          return (
            <div key={key}>
              <label className="label">{label}</label>
              <input
                type="number"
                className="input text-sm"
                value={typeof current === "number" ? current : ""}
                onChange={(e) =>
                  setField(
                    key,
                    e.target.value.trim() === ""
                      ? undefined
                      : Number(e.target.value),
                  )
                }
              />
            </div>
          );
        }

        return (
          <div key={key}>
            <label className="label">{label}</label>
            <input
              type="text"
              className="input text-sm"
              value={current != null ? String(current) : ""}
              maxLength={spec?.max_length}
              onChange={(e) => setField(key, e.target.value || undefined)}
            />
          </div>
        );
      })}
    </div>
  );
}
