-- 内置本地引擎 Provider 去掉显示名中的「(本地)」（Base URL 已可配置，名称不再强调部署位置）
UPDATE providers SET display_name = 'Ollama' WHERE id = 'ollama' AND display_name = 'Ollama (本地)';
UPDATE providers SET display_name = 'LM Studio' WHERE id = 'lmstudio' AND display_name = 'LM Studio (本地)';
UPDATE providers SET display_name = 'vLLM' WHERE id = 'vllm' AND display_name = 'vLLM (本地)';
