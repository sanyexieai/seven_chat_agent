# 记忆分级设计

## 目标

1. **原始层 (raw)**：观察、流水账等「证据」——可查、可归档，**默认不进入业务提示词**。
2. **整理层 (curated)**：助理提取 / 反思 / LLM ingest / 人工确认后的可复用记忆——**前端主展示 + 提示词召回**。
3. **作用域 (scope)**：标明记忆适用的上下文范围。
4. **重要性 (importance 0–3)**：召回排序与衰减策略。
5. **多租户 (tenant_id)**：记忆与全局策略按租户隔离（环境变量 `SEVEN_CHAT_AGENT_TENANT_ID`，默认 `default`）。

## 字段

| 字段 | 说明 |
|------|------|
| `tier` | `raw` \| `curated` |
| `scope` | `global` \| `user` \| `friend` \| `conversation` \| `ephemeral` |
| `scope_ref` | 好友 id / 会话 id；`user` 建议用 `tenant_id` |
| `importance` | 0 临时 … 3 关键 |
| `status` | `active` \| `archived` |
| `title` / `summary` | 整理层短标题与注入用摘要 |
| `tenant_id` | 租户隔离 |
| `expires_at` | 临时记忆过期时间（`ephemeral` 自动写入） |
| `embedding` | curated 向量（BLOB f32） |

## 写入路径

| 来源 | tier | 典型 scope |
|------|------|------------|
| 其他会话观察 | raw | friend / conversation |
| 协助流水账（可选） | raw | conversation |
| LLM 知识提取 | curated | global / user |
| 反思 lessons | curated | global |
| **LLM ingest（raw→curated）** | curated | LLM 指定 |
| 面板手动新建 | curated | 用户选择 |

## 召回（提示词）

仅 `tier=curated` 且 `status=active` 且未过期，并按当前会话匹配：

- 始终：`global`
- 用户偏好：`user` 且 `scope_ref` 为空或等于当前 `tenant_id`
- 若相关：`friend` / `conversation` / `ephemeral` + `scope_ref`

召回顺序：**置顶 → FTS → 向量（可选）→ 最近候选**。

## 维护流水线

队列任务 `consolidate_memory` / 面板「立即维护」执行：

1. 删除 `expires_at` 已过的记忆
2. raw 归档 / curated 衰减
3. **LLM ingest**：批量 raw → 少量 curated（`auto_ingest_raw`）
4. **向量回填**：缺 embedding 的 curated（`embedding_enabled`）

观察计数达到 `consolidate_every_n` 时入队维护任务。

## 与外部方案对照

| 方案 | 对应 |
|------|------|
| Claude Projects | `curated` + `global` |
| mem0 | `scope` + embedding 混合检索 |
| OpenViking ingest | `auto_ingest_raw` + raw 归档 |
| 多租户 SaaS | `tenant_id` + `user` scope |
