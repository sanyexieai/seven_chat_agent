-- 记忆分级：原始(raw) vs 整理(curated)；作用域(scope)；重要性；归档状态
ALTER TABLE memories ADD COLUMN tier TEXT NOT NULL DEFAULT 'curated';
ALTER TABLE memories ADD COLUMN scope TEXT NOT NULL DEFAULT 'global';
ALTER TABLE memories ADD COLUMN scope_ref TEXT;
ALTER TABLE memories ADD COLUMN importance INTEGER NOT NULL DEFAULT 1;
ALTER TABLE memories ADD COLUMN status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE memories ADD COLUMN title TEXT;
ALTER TABLE memories ADD COLUMN summary TEXT;

CREATE INDEX IF NOT EXISTS idx_memories_recall
    ON memories(owner_friend_id, tier, status, scope, importance DESC);

-- 历史观察/流水 → 原始层，不参与默认召回
UPDATE memories
SET tier = 'raw',
    scope = CASE
        WHEN content LIKE '[默认观察/%' AND content LIKE '%群聊:%' THEN 'conversation'
        WHEN content LIKE '[默认观察/%' THEN 'friend'
        ELSE scope
    END,
    importance = 0
WHERE content LIKE '[默认观察/%'
   OR content LIKE '[协助记录]%'
   OR content LIKE '[待办执行]%'
   OR content LIKE '[空闲守护完成]%';

-- 知识类默认全局整理层
UPDATE memories
SET tier = 'curated',
    scope = 'global',
    importance = CASE WHEN importance < 1 THEN 2 ELSE importance END
WHERE kind IN ('knowledge', 'fact', 'preference', 'project', 'relation', 'lesson');
