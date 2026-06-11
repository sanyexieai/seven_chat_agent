import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { GroupPublicMemoriesResponse } from "../types";

interface Props {
  groupId: string;
}

export function GroupPublicMemoryPanel({ groupId }: Props) {
  const [data, setData] = useState<GroupPublicMemoriesResponse | null>(null);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getGroupPublicMemories(groupId, {
        q: query.trim() || undefined,
        include_raw: true,
        limit: 12,
      });
      setData(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [groupId, query]);

  useEffect(() => {
    void load();
  }, [load]);

  const rebuild = async () => {
    setRebuilding(true);
    setError(null);
    try {
      await api.rebuildGroupPublicMemories(groupId);
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRebuilding(false);
    }
  };

  return (
    <div
      id="group-public-memory"
      className="rounded-md border border-slate-200 bg-slate-50/80 p-3"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="text-xs font-semibold text-slate-800">群共识记忆</div>
        <button
          type="button"
          className="btn-ghost text-xs"
          disabled={rebuilding}
          onClick={() => void rebuild()}
        >
          {rebuilding ? "整理中…" : "手动整理"}
        </button>
      </div>
      <p className="mt-1 text-[11px] text-slate-600">
        助理整理的本群共识（只读）；成员接话时会引用。raw 为每回合表现快照。
      </p>
      <div className="mt-2 flex gap-2">
        <input
          className="input flex-1 text-xs"
          placeholder="搜索共识…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void load();
          }}
        />
        <button
          type="button"
          className="btn-secondary text-xs"
          disabled={loading}
          onClick={() => void load()}
        >
          搜索
        </button>
      </div>
      {error && (
        <p className="mt-2 text-xs text-red-600">{error}</p>
      )}
      {loading && !data ? (
        <p className="mt-2 text-xs text-slate-500">加载中…</p>
      ) : (
        <>
          <div className="mt-3">
            <div className="text-[11px] font-medium text-slate-700">
              当前共识（latest）
            </div>
            {data?.latest ? (
              <>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    className="btn-ghost text-[10px]"
                    disabled={loading}
                    onClick={() =>
                      void (async () => {
                        try {
                          await api.patchGroupPublicLatest(groupId, {
                            pinned: !data.latest?.pinned,
                            importance: data.latest?.pinned ? 2 : 3,
                          });
                          await load();
                        } catch (e: unknown) {
                          setError(e instanceof Error ? e.message : String(e));
                        }
                      })()
                    }
                  >
                    {data.latest.pinned ? "取消置顶" : "置顶共识"}
                  </button>
                  {data.latest.pinned && (
                    <span className="text-[10px] text-amber-700">已置顶</span>
                  )}
                </div>
                <pre className="mt-1 max-h-48 overflow-y-auto whitespace-pre-wrap rounded border border-slate-200 bg-white p-2 font-sans text-[11px] text-slate-800">
                  {data.latest.content}
                </pre>
                <p className="mt-1 text-[10px] text-slate-500">
                  更新于 {new Date(data.latest.updated_at).toLocaleString()}
                </p>
              </>
            ) : (
              <p className="mt-1 text-xs text-slate-500">尚无共识，聊几轮后会自动生成。</p>
            )}
          </div>
          {data?.search_hits && data.search_hits.length > 0 && (
            <div className="mt-3">
              <div className="text-[11px] font-medium text-slate-700">搜索结果</div>
              <ul className="mt-1 space-y-1 text-[11px] text-slate-700">
                {data.search_hits.map((h) => (
                  <li key={h.id} className="rounded bg-white px-2 py-1">
                    {h.content}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {data?.raw_recent && data.raw_recent.length > 0 && (
            <details className="mt-3">
              <summary className="cursor-pointer text-[11px] font-medium text-slate-600">
                近期 raw 快照（{data.raw_recent.length}）
              </summary>
              <ul className="mt-1 max-h-36 space-y-1 overflow-y-auto text-[10px] text-slate-600">
                {data.raw_recent.map((r) => (
                  <li key={r.id} className="rounded border border-slate-100 bg-white p-1.5">
                    <span className="text-slate-400">
                      {new Date(r.created_at).toLocaleString()}
                    </span>
                    <div className="mt-0.5 whitespace-pre-wrap">{r.content}</div>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
    </div>
  );
}
