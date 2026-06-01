# Ollama + OpenClaw 全功能 Docker Compose

基于 hermit-claw 架构开发的容器化 AI Agent 系统，支持通过 API 动态创建和管理 OpenClaw、Claude、Hermes Agent。其中 Claude 容器尽量沿用 hermit-claw 的启动习惯，OpenClaw 是本项目新增的容器类型。

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│                     控制平面 (Control Plane)                  │
│              http://localhost:${CONTROL_BASE_PORT:-18080}     │
│              动态创建/管理 Agent 容器                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐   ┌─────────────────┐   ┌──────────────┐  │
│  │   Ollama    │   │ OpenClaw Gateway │   │ OpenClaw     │  │
│  │  (LLM 推理) │◄──│  (认证网关)       │◄──│   Agent      │  │
│  │  :11434    │   │  :18789/:18790   │   │  (动态创建)  │  │
│  └─────────────┘   └─────────────────┘   └──────────────┘  │
│                                                             │
│  Network: 172.31.0.0/16                                     │
└─────────────────────────────────────────────────────────────┘
```

## 服务

| 服务 | 端口 | 说明 |
|------|------|------|
| **ollama** | 11434 | LLM 推理服务 |
| **openclaw-gateway** | 18789 | OpenClaw 认证网关 |
| **control-${CONTROL_BASE_PORT:-18080}** | `${CONTROL_BASE_PORT:-18080}` | Agent 控制 API |

默认 `.env` 可把控制面板端口起点改成 20000：

```dotenv
CONTROL_BASE_PORT=20000
OPENCLAW_GATEWAY_TOKEN=2ac145e2572b9b2fb44717b520c22588858403a75d4a6ea2
```

设置后控制面板地址为 `http://localhost:20000`，动态 Agent 端口从 `20001` 开始，最多分配到 `20999`。

## 快速开始

### 1. 启动服务

```bash
docker-compose up -d --build
```

### 2. 检查服务状态

```bash
# 查看运行中的容器
docker-compose ps

# 测试 API
curl http://localhost:18080/api/health

# 查看可用模型
docker exec openclaw-gateway openclaw models list
```

### 3. 创建 Agent

通过 API 创建 Agent：

```bash
curl -X POST http://localhost:18080/api/agents \
  -H "Content-Type: application/json" \
  -d '{
    "type": "openclaw@2026.2.9",
    "name": "my-agent"
  }'
```

可用类型：

| 类型 | 说明 |
|------|------|
| `openclaw@2026.2.9` | 本项目新增的 OpenClaw Agent，连接 `openclaw-gateway` 和本地 Ollama |
| `claude@latest` | Claude Code Agent，容器启动方式参考 hermit-claw：预置 onboarding、复制 rules、通过 `run_claude.js` 接收消息 |
| `hermes@latest` | Hermes Agent 模板 |

响应示例：
```json
{
  "container_name": "18081-my-agent",
  "agent_type": "openclaw@2026.2.9",
  "host_port": 18081,
  "service_port": 8082,
  "created_at": "2026-05-17T15:00:00.000Z"
}
```

### 4. 向 Agent 发送命令

```bash
curl -X POST http://localhost:18080/api/agents/18081-my-agent/command \
  -H "Content-Type: application/json" \
  -d '{"command": "ls -la /workspace"}'
```

### 5. 查看日志

```bash
# 查看所有 Agent 状态
curl "http://localhost:18080/api/agents?tail=50"

# 下载指定 Agent 日志
curl "http://localhost:18080/api/agents/18081-my-agent/logs/download" -o agent.log

# 查看实时日志
curl "http://localhost:18080/api/agents/18081-my-agent/logs?tail=50"
```

### 6. 删除 Agent

```bash
curl -X DELETE http://localhost:18080/api/agents/18081-my-agent
```

## API 文档

### 健康检查
```
GET /api/health
```

### 列出所有 Agent
```
GET /api/agents?tail=200
```

### 创建 Agent
```
POST /api/agents
{
  "type": "openclaw@2026.2.9",
  "name": "agent-name",
  "message": "optional initial message"
}
```

### 发送命令
```
POST /api/agents/{container_name}/command
{
  "command": "ls -la"
}
```

### 查看日志
```
GET /api/agents/{container_name}/logs?tail=200
```

### 下载日志
```
GET /api/agents/{container_name}/logs/download?tail=500
```

### 删除 Agent
```
DELETE /api/agents/{container_name}
```

## 配置说明

### OpenClaw Gateway 配置

配置文件：`config/openclaw/openclaw.json`

关键配置：
- `gateway.auth.token`: 认证令牌
- `models.providers.ollama`: Ollama 模型配置
- `agents.defaults.model.primary`: 默认使用的模型

注意：OpenClaw 会使用工具调用能力，`deepseek-r1:1.5b` 这类不支持 tools 的 Ollama 模型会报 `does not support tools`。默认配置使用 `ollama/qwen2.5:0.5b`，部署模型时请优先选择支持 tools 的 `qwen2.5`、`qwen3` 等模型。

### Claude + Ollama 配置

Claude 容器使用 `run_claude.js` 调用 Claude Code CLI，不再把 Claude 消息转给 `openclaw` 命令。控制面板会把 `config/claude/settings.json`、`config/claude/config.json` 注入到容器内的 `/home/agent/.claude/`，默认通过本项目内置的 Anthropic 兼容代理访问 Ollama：

- `ANTHROPIC_BASE_URL`: 默认 `http://control-${CONTROL_BASE_PORT}:8080/anthropic`
- `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_API_KEY`: 默认 `ollama`
- `ANTHROPIC_MODEL`: 跟随模型管理里提交并部署的 Ollama 模型

模型管理页面的“提交并部署”会同时更新 OpenClaw 与 Claude 配置：OpenClaw 写入 `config/openclaw/openclaw.json`，Claude 写入 `config/claude/settings.json` 和 `config/claude/config.json`。这样选择 Ollama 模型后，Claude 容器可以用同一套本地 key 与模型配置一键部署。

内置 Anthropic 代理支持 `/anthropic/v1/messages` 和 `/anthropic/v1/models`，并会把 Claude Code 的 streaming 请求包装成 Ollama Chat 调用。默认不把 Claude Code 的 tools schema 转发给 Ollama，以避免小模型出现 `does not support tools` 或长时间卡住；如确实要透传工具 schema，可在控制面板环境变量中设置 `CLAUDE_PROXY_ENABLE_TOOLS=true`。

### 下载模型到 Ollama

```bash
# 进入 Ollama 容器
docker exec -it ollama /bin/sh

# 下载模型
ollama pull llama3.3
ollama pull qwen2.5-coder:32b
ollama pull deepseek-r1:32b

# 退出
exit
```

### Agent 配置

Agent 容器会按类型读取配置：

| 类型 | 配置目录 | 容器内工作目录 |
|------|----------|----------------|
| `openclaw@2026.2.9` | `config/openclaw/` | `/home/agent/.openclaw/workspace/project` |
| `claude@latest` | `config/claude/` | `/home/agent/.claude/workspace/project` |
| `hermes@latest` | `config/hermes/` | `/home/agent/.hermes/workspace/project` |

## 目录结构

```
ollama-claw/
├── docker-compose.yml           # Docker Compose 配置
├── agents/
│   ├── gateway/                 # OpenClaw Gateway
│   │   └── Dockerfile
│   ├── agent-openclaw/          # OpenClaw Agent 模板（本项目新增）
│   ├── agent-claude/            # Claude Agent 模板（参考 hermit-claw）
│   ├── agent-hermes/            # Hermes Agent 模板
│   │   └── Dockerfile
│   └── ollama/                  # Ollama 服务
│       └── Dockerfile
├── control/                     # 控制平面 API
│   ├── Dockerfile
│   ├── app.py
│   └── requirements.txt
├── config/
│   ├── openclaw/                # OpenClaw 配置
│   │   └── openclaw.json
│   ├── claude/                  # Claude 配置
│   │   ├── config.json          # Claude/Ollama provider 配置
│   │   ├── openclaw.json
│   │   └── settings.json
│   ├── hermes/                  # Hermes 配置
│   │   └── openclaw.json
│   └── rules/                   # Agent 规则文件
├── workspaces/                  # Agent 工作目录
├── logs/                        # 日志目录
└── README.md
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OPENCLAW_GATEWAY_TOKEN` | `2ac145e2572b9b2fb44717b520c22588858403a75d4a6ea2` | Gateway 认证令牌 |
| `OPENCLAW_GATEWAY_HOST` | `172.31.0.10` | Gateway 主机地址 |
| `OPENCLAW_GATEWAY_PORT` | `18790` | Gateway WebSocket 端口 |
| `CONTROL_BASE_PORT` | `18080` | 控制面板宿主机端口；Agent 端口从该值 + 1 开始 |
| `CLAUDE_ANTHROPIC_BASE_URL` | `http://control-${CONTROL_BASE_PORT}:8080/anthropic` | Claude 容器访问本地 Anthropic 兼容代理的地址 |
| `CLAUDE_ANTHROPIC_AUTH_TOKEN` | `ollama` | 注入 Claude 的本地 API key/token |
| `CLAUDE_PROXY_ENABLE_TOOLS` | 空 | 设置为 `true` 时把 Claude tools schema 透传给 Ollama |

## 故障排查

### 查看日志

```bash
# 所有服务日志
docker-compose logs -f

# 单个服务日志
docker-compose logs -f ollama
docker-compose logs -f openclaw-gateway
docker-compose logs -f control-18080
```

### 重启服务

```bash
docker-compose restart
```

### 完全重建

```bash
docker-compose down -v
docker-compose up -d --build
```

## 与 hermit-claw 的区别

1. **新增 OpenClaw 容器类型**：`openclaw@2026.2.9` 是本项目新增的 Agent 模板，默认接入本地 Ollama 和 `openclaw-gateway`
2. **保留 Claude 容器思路**：`claude@latest` 参考 hermit-claw 的 Claude 容器，预置信任/跳过 onboarding，并通过 `run_claude.js` 处理控制面板发送的消息
3. **动态端口起点**：通过 `.env` 或环境变量设置 `CONTROL_BASE_PORT`，控制面板使用该端口，Agent 从 `CONTROL_BASE_PORT + 1` 递增
4. **Claude 走本地 Anthropic 代理**：`claude@latest` 通过 `run_claude.js` 调 Claude Code CLI，并用 Ollama key 风格的一键配置接入本地代理
5. **基于 Ollama**：OpenClaw 默认使用 Ollama 作为 LLM 后端，模型需支持工具调用

## 注意事项

1. Agent 使用资源限制：16GB 内存 + 8GB 共享内存
2. 日志文件限制：500MB 大小，最多 2 个文件轮转
3. 端口范围：Agent 分配端口为 `CONTROL_BASE_PORT + 1` 到 `CONTROL_BASE_PORT + 999`，默认是 `18081-19079`；当前 `.env` 示例是 `20001-20999`
