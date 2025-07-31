# LLM配置指南

## 概述

本系统支持使用真实的LLM API，包括OpenAI、Anthropic和Ollama。请按照以下步骤配置您的LLM服务。

## 支持的模型提供商

### 1. OpenAI
- **模型**: gpt-3.5-turbo, gpt-4, gpt-4-turbo-preview
- **API密钥**: 从 [OpenAI Platform](https://platform.openai.com/api-keys) 获取
- **基础URL**: https://api.openai.com/v1 (默认)

### 2. Anthropic
- **模型**: claude-3-sonnet-20240229, claude-3-haiku-20240307, claude-3-opus-20240229
- **API密钥**: 从 [Anthropic Console](https://console.anthropic.com/) 获取

### 3. Ollama
- **模型**: llama2, llama2:13b, llama2:70b, codellama, mistral, qwen2:7b 等
- **安装**: 从 [Ollama官网](https://ollama.ai/) 下载并安装
- **基础URL**: http://localhost:11434 (默认)

## 环境变量配置

创建 `.env` 文件并设置以下环境变量：

```bash
# 模型提供商 (openai, anthropic, ollama)
MODEL_PROVIDER=openai

# 模型名称
MODEL=gpt-3.5-turbo

# API密钥 (OpenAI和Anthropic需要)
API_KEY=your-api-key-here

# API基础URL
BASE_URL=https://api.openai.com/v1

# Ollama基础URL (Ollama专用)
OLLAMA_BASE_URL=http://localhost:11434

# 温度参数 (0.0-2.0)
TEMPERATURE=0.7
```

## 配置示例

### OpenAI配置
```bash
MODEL_PROVIDER=openai
MODEL=gpt-3.5-turbo
API_KEY=sk-your-openai-api-key
BASE_URL=https://api.openai.com/v1
TEMPERATURE=0.7
```

### Anthropic配置
```bash
MODEL_PROVIDER=anthropic
MODEL=claude-3-sonnet-20240229
API_KEY=sk-ant-your-anthropic-api-key
TEMPERATURE=0.7
```

### Ollama配置
```bash
MODEL_PROVIDER=ollama
MODEL=llama2
OLLAMA_BASE_URL=http://localhost:11434
TEMPERATURE=0.7
```

## Ollama安装和配置

### 1. 安装Ollama
```bash
# macOS
curl -fsSL https://ollama.ai/install.sh | sh

# Linux
curl -fsSL https://ollama.ai/install.sh | sh

# Windows
# 从 https://ollama.ai/download 下载安装包
```

### 2. 启动Ollama服务
```bash
ollama serve
```

### 3. 下载模型
```bash
# 下载基础模型
ollama pull llama2

# 下载其他模型
ollama pull codellama
ollama pull mistral
ollama pull qwen2:7b
```

### 4. 验证安装
```bash
# 测试模型
ollama run llama2 "Hello, world!"
```

## 验证配置

运行以下命令测试LLM配置：

```bash
cd agent-backend
python -c "
from utils.llm_helper import get_llm_helper
import asyncio

async def test():
    try:
        llm = get_llm_helper()
        response = await llm.call('你好')
        print(f'LLM响应: {response}')
    except Exception as e:
        print(f'配置错误: {e}')

asyncio.run(test())
"
```

## 故障排除

### 1. API密钥错误
- 确保API密钥正确且有效
- 检查API密钥是否有足够的配额

### 2. 网络连接问题
- 确保能够访问API端点
- 如果在中国大陆，可能需要配置代理

### 3. Ollama连接问题
- 确保Ollama服务正在运行: `ollama serve`
- 检查端口11434是否可访问
- 验证模型是否已下载: `ollama list`

### 4. 模型不可用
- 检查模型名称是否正确
- 确认您的API密钥有权限访问该模型
- 对于Ollama，确保模型已下载

### 5. 配置错误
- 检查环境变量是否正确设置
- 确保模型提供商名称拼写正确
- 验证基础URL格式

## 高级配置

### 自定义代理
如果使用代理，可以设置环境变量：
```bash
export HTTP_PROXY=http://your-proxy:port
export HTTPS_PROXY=http://your-proxy:port
```

### 流式响应
系统默认启用流式响应，可以通过环境变量控制：
```bash
STREAM_ENABLED=True
```

### Ollama高级配置
```bash
# 自定义Ollama服务器
OLLAMA_BASE_URL=http://your-ollama-server:11434

# 使用GPU加速 (需要CUDA支持)
OLLAMA_HOST=0.0.0.0:11434
```

## 安全注意事项

1. **API密钥安全**: 不要将API密钥提交到版本控制系统
2. **环境变量**: 使用 `.env` 文件存储敏感信息
3. **访问控制**: 在生产环境中限制API访问权限
4. **监控使用**: 定期检查API使用量和费用

## 成本优化

1. **选择合适的模型**: 根据需求选择性价比合适的模型
2. **设置最大token**: 限制响应长度以控制成本
3. **缓存机制**: 对重复请求进行缓存
4. **监控使用量**: 定期检查API调用次数和费用
5. **本地部署**: 使用Ollama可以避免API调用费用

## 性能优化

### Ollama性能优化
```bash
# 使用GPU加速
OLLAMA_HOST=0.0.0.0:11434

# 调整模型参数
ollama run llama2 --num-ctx 4096 --num-thread 8
```

### 系统要求
- **CPU**: 至少4核心
- **内存**: 至少8GB RAM
- **GPU**: 推荐使用NVIDIA GPU (Ollama)
- **存储**: 至少10GB可用空间 