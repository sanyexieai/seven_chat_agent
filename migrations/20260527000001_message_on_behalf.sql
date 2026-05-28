-- 群助理代用户发言标记
ALTER TABLE messages ADD COLUMN on_behalf_of INTEGER NOT NULL DEFAULT 0;
