export type RuntimeMode = "cli" | "source";

export interface EvolutionCliConfig {
  binary_path: string;
  preset: string;
  active_candidate_path?: string | null;
}

export interface SourceCenterConfig {
  id: string;
  remote_url: string;
  branch: string;
  workspace_dir: string;
  build_command: string;
  test_command: string;
  built_binary_path: string;
  shallow_depth: number;
}

export interface EvolutionLoopConfig {
  enabled: boolean;
  max_concurrent_tasks: number;
  require_approval_before_push: boolean;
  require_approval_before_create_issue?: boolean;
  git_platform: string;
  trusted_orgs: string[];
  github_token?: string | null;
  issue_similarity_threshold?: number;
  analyze_use_llm?: boolean;
  max_issue_sync_items?: number;
}

export interface EvolutionSettings {
  runtime_mode: RuntimeMode;
  cli: EvolutionCliConfig;
  source?: SourceCenterConfig | null;
  evolution: EvolutionLoopConfig;
}

export type EvolutionRunStatus = "running" | "succeeded" | "failed";

export type EvolutionRunKind =
  | "sync_source"
  | "build_cli"
  | "pipeline_sync_build"
  | "analyze_source"
  | "sync_issues"
  | "pipeline_analyze_issues";

export interface EvolutionStepLog {
  name: string;
  ok: boolean;
  detail: string;
  stdout: string;
  stderr: string;
}

export interface EvolutionRunLog {
  id: string;
  kind: EvolutionRunKind;
  status: EvolutionRunStatus;
  started_at: string;
  finished_at?: string | null;
  steps: EvolutionStepLog[];
  error?: string | null;
  commit?: string | null;
  backup_dir?: string | null;
  built_binary?: string | null;
  artifact?: string | null;
}

export type OptimizationSeverity = "low" | "medium" | "high";

export interface OptimizationItem {
  id: string;
  title: string;
  severity: OptimizationSeverity;
  related_paths: string[];
  summary: string;
  suggestion: string;
  source: string;
}

export interface OptimizationReport {
  workspace_dir: string;
  commit?: string | null;
  scanned_files: number;
  items: OptimizationItem[];
  llm_enhanced: boolean;
}

export type IssueSyncAction =
  | "linked_existing"
  | "created_remote"
  | "pending_approval"
  | "skipped";

export interface IssueSyncResult {
  item_id: string;
  item_title: string;
  action: IssueSyncAction;
  remote_url?: string | null;
  local_id?: string | null;
  detail: string;
}

export interface IssueSyncReport {
  items_processed: number;
  results: IssueSyncResult[];
}

export interface EvolutionAnalyzeResponse {
  run: EvolutionRunLog;
  report: OptimizationReport;
}

export interface EvolutionPipelineAnalyzeResponse {
  run: EvolutionRunLog;
  report: OptimizationReport;
  sync: IssueSyncReport;
}

export interface EvolutionRunSummary {
  id: string;
  kind: EvolutionRunKind;
  status: EvolutionRunStatus;
  started_at: string;
  finished_at?: string | null;
  error?: string | null;
}

export interface EvolutionRegistry {
  issues: LocalIssueRecord[];
  capability: { closed_labels: string[]; avg_tokens_per_fix: number };
}

export interface LocalIssueRecord {
  local_id: string;
  remote_url?: string | null;
  first_seen_at: string;
  relevance_notes: string;
  relevance_boost: number;
  status: string;
  related_paths: string[];
  claimed_at?: string | null;
}
