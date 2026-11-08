# LiteLLM 网关配置指南

## 概述

项目现已改为通过 **LiteLLM 统一网关** 管理所有 API 调用，而不是硬编码 API 端点。这样做的好处：

✅ **集中管理**：所有 API 配置在一个地方（`litellm_config.yaml`）  
✅ **环境变量支持**：敏感信息（API key）从容器环境变量读取，不硬编码  
✅ **故障转移**：支持多个 API 提供商，自动切换  
✅ **安全隔离**：Local Llama 用于敏感数据，xAI 用于公开学术文献  

---

## 架构变更

### 之前（硬编码）
```
FastAPI → 直接调用 xAI API / Local Llama
         ↓
    多个数据源，多个端点分散
```

### 现在（网关）
```
FastAPI → LiteLLM 网关 → xAI API / Local Llama / OpenAI
         （统一入口，http://127.0.0.1:4000）
```

---

## 快速开始

### 1️⃣ 准备 API Key

你需要的密钥：

| 名称 | 来源 | 用途 | 必需 |
|------|------|------|------|
| `RELAY_API_KEY` | [xAI 官网](https://console.x.ai) | 学术文献推理 | ✅ |
| `OPENAI_API_KEY` | [OpenAI 官网](https://platform.openai.com) | 文本嵌入 | ✅ |
| `LOCAL_LLAMA_BASE` | 本地或 `http://127.0.0.1:8080` | 敏感田野笔记 | ⚠️ (可选) |

### 2️⃣ 配置环境变量

```bash
# 从模板复制
Copy-Item .env.example .env

# 编辑 .env 文件，填入你的 API key
```

**`.env` 文件内容** (示例)：
```env
# xAI API (学术文献)
RELAY_API_KEY=xai-your-actual-key-here

# OpenAI API (嵌入模型)
OPENAI_API_KEY=sk-your-actual-key-here

# LiteLLM 网关
LITELLM_BASE_URL=http://127.0.0.1:4000/v1
```

### 3️⃣ 启动服务

#### 方式 A：使用启动脚本（推荐）

```powershell
# 一键启动 Qdrant + LiteLLM
.\start-services.ps1
```

该脚本会：
- ✅ 检查 Docker 是否运行
- ✅ 自动创建/启动 Qdrant 容器
- ✅ 自动创建/启动 LiteLLM 容器（传入 .env 环境变量）
- ✅ 验证服务连接
- ✅ 显示接下来的步骤

#### 方式 B：使用 Docker Compose（替代方案）

```powershell
# 确保 .env 文件存在并包含 API key

# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f litellm
docker-compose logs -f qdrant
```

#### 方式 C：手动启动（调试用）

```powershell
# 1. 启动 Qdrant
docker run -d --name qdrant --restart unless-stopped -p 6333:6333 qdrant/qdrant

# 2. 启动 LiteLLM（传入环境变量）
$env:RELAY_API_KEY = "xai-your-key"
$env:OPENAI_API_KEY = "sk-your-key"
docker run -d `
  --name litellm `
  --restart unless-stopped `
  -p 4000:4000 `
  -e RELAY_API_KEY=$env:RELAY_API_KEY `
  -e OPENAI_API_KEY=$env:OPENAI_API_KEY `
  -v "$(Get-Location)\litellm_config.yaml:/app/config.yaml" `
  docker.litellm.ai/berriai/litellm:main-latest `
  python -m litellm.proxy.proxy --config /app/config.yaml --port 4000
```

---

## LiteLLM 配置详解

### `litellm_config.yaml` 结构

```yaml
model_list:
  # 学术文献用：xAI Grok（通过环境变量读取 API key）
  - model_name: grok-4.20-0309-reasoning
    litellm_params:
      model: grok-4
      api_base: "https://api.x.ai/v1"
      api_key: "${RELAY_API_KEY}"  # 从 Docker 环境变量读取
      timeout: 30
  
  # 田野笔记用：本地 Llama
  - model_name: llama-3-8b-local
    litellm_params:
      model: llama-cpp
      api_base: "http://127.0.0.1:8080/v1"
      api_key: "local_dummy_key"
      timeout: 30
  
  # 嵌入模型：OpenAI
  - model_name: text-embedding-ada-002
    litellm_params:
      model: text-embedding-ada-002
      api_key: "${OPENAI_API_KEY}"  # 从 Docker 环境变量读取
      timeout: 30
```

### 关键概念

| 配置项 | 说明 | 示例 |
|--------|------|------|
| `model_name` | 模型标识名 | `grok-4.20-0309-reasoning` |
| `model` | LiteLLM 支持的模型 ID | `grok-4` |
| `api_base` | API 端点 | `https://api.x.ai/v1` |
| `api_key` | API 密钥（支持 `${ENV_VAR}` 语法） | `${RELAY_API_KEY}` |
| `${ENV_VAR}` | 从环境变量读取 | `${RELAY_API_KEY}` 读取容器中的 `RELAY_API_KEY` |

---

## 代码如何调用

### 在 `router_manager.py` 中

```python
# 所有请求都通过 LiteLLM 代理
LITELLM_BASE_URL = os.getenv("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1")

def get_llm_client(self, data_source: str, task_type: str, model: str = None):
    if data_source == "field_notes":
        model = model or "llama-3-8b-local"
    elif data_source == "zotero_academic_papers":
        model = model or "grok-4.20-0309-reasoning"
    
    # 通过 LiteLLM 网关调用
    return OpenAI(
        base_url=LITELLM_BASE_URL,  # ← 统一入口
        api_key="sk-1234",           # LiteLLM 本地不需要真实 key
        model=model                  # ← LiteLLM 根据 model 找对应配置
    )
```

### 在 `ingestion.py` 中

```python
class LiteLLMClient:
    def __init__(self):
        self.base_url = "http://127.0.0.1:4000"
        self._client = httpx.AsyncClient(base_url=self.base_url)
    
    async def embed(self, text: str):
        # 调用 LiteLLM /embeddings 端点
        # LiteLLM 根据内部配置自动路由到相应的提供商
        payload = {"input": text}
        r = await self._client.post("/embeddings", json=payload)
        return r.json()["data"][0]["embedding"]
```

---

## 故障排查

### 1️⃣ LiteLLM 容器无法启动

**错误**：`Error: api_key: ${RELAY_API_KEY} not found`

**原因**：环境变量未传入容器

**解决**：
```powershell
# 确保 .env 文件存在
Test-Path .env

# 使用启动脚本（会自动加载 .env）
.\start-services.ps1

# 或手动传入
docker run -d `
  -e RELAY_API_KEY="xai-your-key" `
  -e OPENAI_API_KEY="sk-your-key" `
  ...
```

### 2️⃣ LiteLLM 无法连接到 xAI API

**错误**：`Failed to call grok-4: ConnectError`

**原因**：API key 不对或网络问题

**解决**：
```powershell
# 1. 验证 API key
echo $env:RELAY_API_KEY

# 2. 检查容器日志
docker logs litellm

# 3. 手动测试 xAI API
curl.exe -X POST https://api.x.ai/v1/chat/completions `
  -H "Authorization: Bearer xai-your-key" `
  -H "Content-Type: application/json" `
  -d '{"model":"grok-4","messages":[{"role":"user","content":"hello"}]}'
```

### 3️⃣ LiteLLM 环境变量替换不生效

**症状**：日志显示 `api_key: ${RELAY_API_KEY} not found`

**原因**：`litellm_config.yaml` 中的 `${VAR_NAME}` 需要容器环境变量支持

**解决**：确保使用以下方式启动：
```powershell
# ✅ 正确：通过 -e 传入，LiteLLM 和 Envsubst 会替换
docker run -d -e RELAY_API_KEY="xai-your-key" ...

# ✅ 也可以：Docker Compose 自动从 .env 读取
docker-compose up -d

# ❌ 错误：直接启动，不传环境变量
docker run -d docker.litellm.ai/berriai/litellm:main-latest ...
```

### 4️⃣ 本地 Llama 无法连接

**症状**：`Connection refused for http://127.0.0.1:8080/v1`

**原因**：本地 Llama 服务未启动

**解决**：
- 如果只用云 API，可以忽略本地 Llama
- 如果需要本地 Llama，启动它：
```powershell
# 使用 Ollama 或其他本地 LLM 服务
ollama run llama2
# 然后确保在 http://127.0.0.1:8080 运行
```

---

## 最佳实践

### ✅ 环境隔离

```powershell
# 开发环境：.env（本地）
# 生产环境：.env.production（CI/CD 注入）

# 不要提交 .env 到 Git
echo ".env" >> .gitignore
```

### ✅ 监控 LiteLLM

```powershell
# 实时查看日志
docker logs -f litellm

# 检查健康状态
Invoke-WebRequest -Uri http://127.0.0.1:4000/health

# 查看已加载的模型
Invoke-WebRequest -Uri http://127.0.0.1:4000/models
```

### ✅ API Key 轮换

无需重启服务，只需更新 `.env` 并重启容器：

```powershell
# 更新 .env
# 然后
docker-compose restart litellm
```

---

## 下一步

1. **配置完成后**，启动 FastAPI：
   ```powershell
   .venv312\Scripts\Activate.ps1
   uvicorn src.main:app --reload
   ```

2. **测试 API**：
   ```powershell
   curl.exe -X POST http://127.0.0.1:8000/query `
     -H "Content-Type: application/json" `
     -d '{"data_source":"zotero_academic_papers","task_type":"analysis","query":"测试"}'
   ```

3. **查看 Zotero 同步**：
   ```powershell
   curl.exe -X POST http://127.0.0.1:8000/ingest/zotero `
     -H "Content-Type: application/json"
   ```

---

## 参考链接

- [LiteLLM 官方文档](https://docs.litellm.ai/)
- [xAI API 文档](https://docs.x.ai/)
- [OpenAI Embeddings 文档](https://platform.openai.com/docs/api-reference/embeddings)
