import type { TaskFlowRound } from "../taskFlow";
import { TASK_FLOW_PHASES, phaseLabel } from "../taskFlow";

interface Props {
  round: TaskFlowRound;
}

export function TaskFlowPanel({ round }: Props) {
  const current = round.currentPhase;

  return (
    <div className="border-b border-violet-200 bg-violet-50/90 px-4 py-2 text-xs text-violet-950">
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        <span className="font-semibold text-violet-900">任务流</span>
        {TASK_FLOW_PHASES.map(({ key, label }) => {
          const done = round.completedPhases.includes(key);
          const active = current === key;
          return (
            <span
              key={key}
              className={[
                "rounded-full px-2 py-0.5 font-medium",
                active
                  ? "bg-violet-600 text-white"
                  : done
                    ? "bg-violet-200/80 text-violet-900"
                    : "bg-white/70 text-violet-400",
              ].join(" ")}
            >
              {label}
            </span>
          );
        })}
        {current === "appoint" && (
          <span className="rounded-full bg-violet-600 px-2 py-0.5 font-medium text-white">
            任命
          </span>
        )}
      </div>

      {round.phaseDetail && (
        <p className="mb-2 text-[11px] text-violet-800">{round.phaseDetail}</p>
      )}

      {round.campaignDone.length > 0 && (
        <p className="mb-1 text-[11px]">
          <span className="font-medium">竞选发言：</span>
          {round.campaignDone.join("、")}
        </p>
      )}

      <div className="mb-2 rounded-md border border-violet-200/80 bg-white/70 px-2 py-1.5">
        <div className="mb-1 font-medium text-violet-900">② 互投明细</div>
        {round.votes.length === 0 ? (
          <p className="text-[11px] text-violet-600">（暂无有效票，可能互投失败或未开启）</p>
        ) : (
          <ul className="space-y-0.5 text-[11px]">
            {round.votes.map((v, i) => (
              <li key={i}>
                {v.ok ? (
                  <>
                    <span className="font-medium">{v.voterName}</span>
                    <span className="text-violet-500"> → </span>
                    <span className="font-medium">{v.endorseName}</span>
                    <span className="text-violet-600">（{v.reason}）</span>
                  </>
                ) : (
                  <span className="text-amber-800">
                    {v.voterName}：投票失败 — {v.error}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
        <p className="mt-1 text-[10px] text-violet-500">
          规则：不能投自己；平票时由 Judge LLM 选举，失败则按互投最高票 → 竞选顺序兜底。
        </p>
      </div>

      {round.election && (
        <div
          className={`rounded-md border px-2 py-1.5 ${
            round.election.electionOk
              ? "border-emerald-200 bg-emerald-50/80"
              : "border-amber-300 bg-amber-50/90"
          }`}
        >
          <div className="font-medium">
            ③ 负责人：{round.election.leaderName}
            {!round.election.electionOk && (
              <span className="ml-1 text-amber-800">（非正式选举）</span>
            )}
          </div>
          {round.election.peerVotesSummary && (
            <pre className="mt-1 whitespace-pre-wrap font-mono text-[10px] text-slate-600">
              {round.election.peerVotesSummary}
            </pre>
          )}
          <p className="mt-0.5 text-[11px]">
            理由：{round.election.reason} · 置信度{" "}
            {(round.election.confidence * 100).toFixed(0)}%
          </p>
        </div>
      )}

      {round.planLeader && (
        <p className="mt-1 text-[11px]">
          <span className="font-medium">④ 计划：</span>
          {round.planLeader} 已发布
        </p>
      )}
      {round.planReviews.length > 0 && (
        <p className="mt-0.5 text-[11px] text-violet-800">
          <span className="font-medium">⑤ 评议：</span>
          {round.planReviews.map((r) => `${r.name}`).join("、")}
        </p>
      )}

      {current && (
        <p className="mt-1 text-[11px] font-medium text-violet-900">
          当前：{phaseLabel(current)}
        </p>
      )}
    </div>
  );
}
