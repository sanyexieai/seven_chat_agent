-- 用户消息附件（图片/文件），JSON 数组存于 messages.attachments
ALTER TABLE messages ADD COLUMN attachments TEXT;
