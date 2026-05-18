# Ollama + OpenClaw 全功能 Docker Compose

基于 hermit-claw 架构开发的容器化 AI Agent 系统，支持通过 API 动态创建和管理 OpenClaw Agent。

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│                     控制平面 (Control Plane)                  │
│                   http://localhost:18080                     │
│              动态创建/管理 Agent 容器                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐   ┌─────────────────┐   ┌──────────────┐  │
│  │   Ollama    │   │ OpenClaw Gateway │   │ OpenClaw     │  │
│  │  (LLM 推理) │◄──│  (认证网关)       │◄──│   Agent      │  │
│  │  :11434    │   │  :18789/:18790   │   │  (动态创建)  │  │
│  └─────────────┘   └─────────────────┘   └──────────────┘  │
│                                                             │
│  Network: 172.30.0.0/16                                     │
└─────────────────────────────────────────────────────────────┘
```

## 服务

| 服务 | 端口 | 说明 |
|------|------|------|
| **ollama** | 11434 | LLM 推理服务 |
| **openclaw-gateway** | 18789 | OpenClaw 认证网关 |
| **control-18080** | 18080 | Agent 控制 API |

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

通过 API 创建 OpenClaw Agent：

```bash
curl -X POST http://localhost:18080/api/agents \
  -H "Content-Type: application/json" \
  -d '{
    "type": "openclaw@2026.2.9",
    "name": "my-agent"
  }'
```

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

Agent 容器会自动从 `config/openclaw/` 目录读取配置。

## 目录结构

```
ollama-claw/
├── docker-compose.yml           # Docker Compose 配置
├── agents/
│   ├── gateway/                 # OpenClaw Gateway
│   │   └── Dockerfile
│   ├── agent-openclaw/          # OpenClaw Agent 模板
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
│   └── rules/                   # Agent 规则文件
├── workspaces/                  # Agent 工作目录
├── logs/                        # 日志目录
└── README.md
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OPENCLAW_GATEWAY_TOKEN` | `2ac145e2572b9b2fb44717b520c22588858403a75d4a6ea2` | Gateway 认证令牌 |
| `OPENCLAW_GATEWAY_HOST` | `172.30.0.10` | Gateway 主机地址 |
| `OPENCLAW_GATEWAY_PORT` | `18790` | Gateway WebSocket 端口 |

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

1. **专注于 OpenClaw**：移除了 claude 和 ollama agent 类型，专注于 OpenClaw Agent
2. **基于 Ollama**：使用 Ollama 作为 LLM 后端替代 Anthropic API
3. **简化配置**：移除复杂的 frpc 和 ssh-gateway 依赖

## 注意事项

1. Agent 使用资源限制：16GB 内存 + 8GB 共享内存
2. 日志文件限制：500MB 大小，最多 2 个文件轮转
3. 端口范围：Agent 分配端口 18081-18999