-- 成员在某群内的 Judge 覆盖（与好友全局无关）
ALTER TABLE group_members ADD COLUMN judge_override TEXT;
