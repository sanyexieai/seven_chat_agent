import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import { Collapsible } from "./Collapsible";
import type {
  EvolutionRunLog,
  EvolutionRunSummary,
  EvolutionSettings,
  IssueSyncReport,
  OptimizationReport,
} from "../types/evolution";

const defaultSettings: EvolutionSettings = {
  runtime_mode: "cli",
  cli: { binary_path: "", preset: "worker-bee" },
  source: {
    id: "seven-chat-agent",
    remote_url: "",
    branch: "main",
    workspace_dir: "",
    build_command: "cargo build --release -p seven-chat-agent-cli",
    test_command: "cargo test --workspace --no-run",
    built_binary_path: "target/release/seven-chat-agent-cli",
    shallow_depth: 1,
  },
  evolution: {
    enabled: false,
    max_concurrent_tasks: 1,
    require_approval_before_push: true,
    git_platform: "github",
    trusted_orgs: [],
  },
};

function runKindLabel(k: string): string {
  if (k === "sync_source") return "同步源码";
  if (k === "build_cli") return "编译 CLI";
  if (k === "pipeline_sync_build") return "同步+编译";
  if (k === "analyze_source") return "源码分析";
  if (k === "sync_issues") return "同步 Issue";
  if (k === "pipeline_analyze_issues") return "分析+Issue";
  return k;
}

function issueActionLabel(a: string): string {
  if (a === "linked_existing") return "已关联";
  if (a === "created_remote") return "已创建";
  if (a === "pending_approval") return "待审批";
  if (a === "skipped") return "跳过";
  return a;
}

export function EvolutionPanel() {
  const [settings, setSettings] = useState<EvolutionSettings>(defaultSettings);
  const [runs, setRuns] = useState<EvolutionRunSummary[]>([]);
  const [lastRun, setLastRun] = useState<EvolutionRunLog | null>(null);
  const [lastReport, setLastReport] = useState<OptimizationReport | null>(null);
  const [lastSync, setLastSync] = useState<IssueSyncReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  const reload = useCallback(async () => {
    const s = await api.getEvolutionSettings();
    setSettings({
      ...defaultSettings,
      ...s,
      cli: { ...defaultSettings.cli, ...s.cli },
      source: s.source
        ? { ...defaultSettings.source!, ...s.source }
        : defaultSettings.source,
      evolution: { ...defaultSettings.evolution, ...s.evolution },
    });
    const r = await api.listEvolutionRuns(20);
    setRuns(r.runs);
  }, []);

  useEffect(() => {
    reload().catch((e) => setMsg(String(e)));
  }, [reload]);

  const runAction = async (fn: () => Promise<EvolutionRunLog>, label: string) => {
    setBusy(true);
    setMsg(`${label}…`);
    try {
      const run = await fn();
      setLastRun(run);
      setMsg(
        run.status === "succeeded"
          ? `${label} 完成（${run.id}）`
          : `${label} 失败：${run.error ?? "见步骤日志"}`,
      );
      await reload();
    } catch (e) {
      setMsg(`${label} 异常：${String(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    setBusy(true);
    try {
      await api.putEvolutionSettings(settings);
      setMsg("配置已保存");
    } catch (e) {
      setMsg(`保存失败：${String(e)}`);
    } finally {
      setBusy(false);
    }
  };

  const src = settings.source ?? defaultSettings.source!;

  return (
    <div className="space-y-4 text-sm text-slate-800">
      <p className="text-xs text-slate-600 leading-relaxed">
        自我进化外环（E0～E2）：拉取源码 → 编译验证 → 静态/LLM 分析 → GitHub Issue 同步。
        进化 token 池在「策略」页的全局设置中配置。详见{" "}
        <code className="text-[11px]">docs/自我进化规则.md</code>。
      </p>
      {msg && (
        <div className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-xs whitespace-pre-wrap">
          {msg}
        </div>
      )}

      <section className="space-y-2">
        <label className="flex items-center gap-2">
          <span className="w-24 text-slate-600">运行模式</span>
          <select
            className="rounded border px-2 py-1"
            value={settings.runtime_mode}
            onChange={(e) =>
              setSettings({
                ...settings,
                runtime_mode: e.target.value as EvolutionSettings["runtime_mode"],
              })
            }
          >
            <option value="cli">CLI（仅基础二进制）</option>
            <option value="source">源码（挂载 Git 工作区）</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-slate-600">基础 CLI 路径</span>
          <input
            className="rounded border px-2 py-1 font-mono text-xs"
            value={settings.cli.binary_path}
            onChange={(e) =>
              setSettings({
                ...settings,
                cli: { ...settings.cli, binary_path: e.target.value },
              })
            }
            placeholder="/usr/local/bin/seven-chat-agent-cli"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-slate-600">远程仓库 URL</span>
          <input
            className="rounded border px-2 py-1 font-mono text-xs"
            value={src.remote_url}
            onChange={(e) =>
              setSettings({
                ...settings,
                source: { ...src, remote_url: e.target.value },
              })
            }
          />
        </label>
        <label className="flex items-center gap-2">
          <span className="w-24 text-slate-600">分支</span>
          <input
            className="flex-1 rounded border px-2 py-1 font-mono text-xs"
            value={src.branch}
            onChange={(e) =>
              setSettings({
                ...settings,
                source: { ...src, branch: e.target.value },
              })
            }
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-slate-600">编译命令（在工作区内执行）</span>
          <input
            className="rounded border px-2 py-1 font-mono text-xs"
            value={src.build_command}
            onChange={(e) =>
              setSettings({
                ...settings,
                source: { ...src, build_command: e.target.value },
              })
            }
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-slate-600">产物路径（相对工作区）</span>
          <input
            className="rounded border px-2 py-1 font-mono text-xs"
            value={src.built_binary_path}
            onChange={(e) =>
              setSettings({
                ...settings,
                source: { ...src, built_binary_path: e.target.value },
              })
            }
          />
        </label>
        {settings.cli.active_candidate_path && (
          <p className="text-xs text-emerald-800">
            候选 CLI：{settings.cli.active_candidate_path}
          </p>
        )}
        <div className="flex flex-wrap gap-2 pt-1">
          <button className="btn-primary" disabled={busy} onClick={save}>
            保存配置
          </button>
          <button
            className="btn-ghost"
            disabled={busy}
            onClick={() =>
              runAction(() => api.evolutionSyncSource(), "同步源码")
            }
          >
            ① 同步源码
          </button>
          <button
            className="btn-ghost"
            disabled={busy}
            onClick={() => runAction(() => api.evolutionBuildCli(), "编译 CLI")}
          >
            ② 编译验证
          </button>
          <button
            className="btn-ghost"
            disabled={busy}
            onClick={() =>
              runAction(
                () => api.evolutionPipelineSyncBuild(),
                "同步+编译",
              )
            }
          >
            ①+② 串联
          </button>
          <button
            className="btn-ghost"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setMsg("源码分析…");
              try {
                const res = await api.evolutionAnalyzeSource();
                setLastRun(res.run);
                setLastReport(res.report);
                setLastSync(null);
                setMsg(
                  res.run.status === "succeeded"
                    ? `分析完成：${res.report.items.length} 条优化项`
                    : `分析失败：${res.run.error ?? ""}`,
                );
                await reload();
              } catch (e) {
                setMsg(`分析异常：${String(e)}`);
              } finally {
                setBusy(false);
              }
            }}
          >
            ③ 分析源码
          </button>
          <button
            className="btn-ghost"
            disabled={busy || !lastReport}
            onClick={async () => {
              if (!lastReport) return;
              setBusy(true);
              setMsg("同步 Issue…");
              try {
                const res = await api.evolutionSyncIssues(lastReport);
                setLastRun(res.run);
                setLastSync(res.sync);
                setMsg(
                  res.run.status === "succeeded"
                    ? `Issue 同步：处理 ${res.sync.items_processed} 条`
                    : `同步失败：${res.run.error ?? ""}`,
                );
                await reload();
              } catch (e) {
                setMsg(`同步异常：${String(e)}`);
              } finally {
                setBusy(false);
              }
            }}
          >
            ④ 同步 Issue
          </button>
          <button
            className="btn-ghost"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setMsg("分析+Issue 串联…");
              try {
                const res = await api.evolutionPipelineAnalyzeIssues();
                setLastRun(res.run);
                setLastReport(res.report);
                setLastSync(res.sync);
                setMsg(
                  res.run.status === "succeeded"
                    ? `完成：${res.report.items.length} 项 / Issue ${res.sync.items_processed} 条`
                    : `失败：${res.run.error ?? ""}`,
                );
                await reload();
              } catch (e) {
                setMsg(`串联异常：${String(e)}`);
              } finally {
                setBusy(false);
              }
            }}
          >
            ③+④ 串联
          </button>
        </div>
      </section>

      {lastReport && (
        <Collapsible
          defaultOpen={false}
          summary={
            <span className="font-sans text-xs">
              分析报告 · {lastReport.items.length} 项 · 扫描{" "}
              {lastReport.scanned_files} 文件
              {lastReport.llm_enhanced ? " · LLM 增强" : ""}
            </span>
          }
        >
          <ul className="space-y-2 text-xs max-h-64 overflow-auto">
            {lastReport.items.map((item) => (
              <li key={item.id} className="border-b border-slate-100 pb-1">
                <span className="text-slate-500">[{item.severity}]</span>{" "}
                {item.title}
                {item.summary && (
                  <p className="text-slate-600 mt-0.5">{item.summary}</p>
                )}
              </li>
            ))}
          </ul>
        </Collapsible>
      )}

      {lastSync && lastSync.results.length > 0 && (
        <Collapsible
          defaultOpen={false}
          summary={
            <span className="font-sans text-xs">
              Issue 同步 · {lastSync.results.length} 条结果
            </span>
          }
        >
          <ul className="space-y-1 text-xs">
            {lastSync.results.map((r, i) => (
              <li key={i}>
                {issueActionLabel(r.action)} · {r.item_title}
                {r.remote_url && (
                  <a
                    className="ml-1 text-blue-700 underline"
                    href={r.remote_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    链接
                  </a>
                )}
                {r.detail && (
                  <span className="text-slate-500"> — {r.detail}</span>
                )}
              </li>
            ))}
          </ul>
        </Collapsible>
      )}

      {lastRun && (
        <Collapsible
          defaultOpen={lastRun.status === "failed"}
          tone="reasoning"
          summary={
            <span className="font-sans text-xs">
              最近运行 · {runKindLabel(lastRun.kind)} · {lastRun.status} ·{" "}
              {lastRun.id}
            </span>
          }
        >
          <div className="space-y-2 text-xs font-mono">
            {lastRun.error && (
              <p className="text-red-800">{lastRun.error}</p>
            )}
            {lastRun.commit && <p>commit: {lastRun.commit}</p>}
            {lastRun.built_binary && <p>binary: {lastRun.built_binary}</p>}
            {lastRun.steps.map((step, i) => (
              <div
                key={i}
                className={
                  step.ok
                    ? "text-emerald-900"
                    : "text-red-900 border border-red-100 rounded p-1"
                }
              >
                <div>
                  [{step.ok ? "OK" : "FAIL"}] {step.name}: {step.detail}
                </div>
                {step.stderr && (
                  <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap text-[10px] text-slate-600">
                    {step.stderr}
                  </pre>
                )}
              </div>
            ))}
          </div>
        </Collapsible>
      )}

      {runs.length > 0 && (
        <Collapsible
          defaultOpen={false}
          summary={
            <span className="font-sans text-xs">运行历史（{runs.length}）</span>
          }
        >
          <ul className="space-y-1 text-xs">
            {runs.map((r) => (
              <li key={r.id} className="flex gap-2">
                <span
                  className={
                    r.status === "succeeded"
                      ? "text-emerald-700"
                      : r.status === "failed"
                        ? "text-red-700"
                        : "text-slate-500"
                  }
                >
                  {r.status}
                </span>
                <span>{runKindLabel(r.kind)}</span>
                <span className="text-slate-400">{r.id}</span>
              </li>
            ))}
          </ul>
        </Collapsible>
      )}
    </div>
  );
}
