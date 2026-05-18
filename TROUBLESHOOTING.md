# Ollama + OpenClaw 问题排查与解决

## 当前状态

### 服务运行状态
- ✅ Ollama 服务：正常运行 (http://localhost:11434)
- ✅ OpenClaw 服务：正常运行 (http://localhost:18789)
- ❌ 模型状态：没有已安装的模型

### 已验证的配置

**docker-compose.yml 环境变量：**
```yaml
environment:
  - OLLAMA_HOST=http://ollama:11434
  - OLLAMA_API_KEY=ollama-local
```

**openclaw-config.json 配置：**
```json
{
  "models": {
    "providers": {
      "ollama": {
        "apiKey": "ollama-local",
        "baseUrl": "http://ollama:11434"
      }
    }
  }
}
```

## 遇到的问题

### 1. 模型下载失败（网络错误）
```
Error: max retries exceeded: Get "...Cloudflare...: EOF
```

**原因：** 网络连接问题，无法从 CDN 下载模型。

**解决方案：**

方案 A：重试下载
```bash
docker exec -it ollama ollama pull llama3.3
```

方案 B：使用代理（如果需要）
```bash
# 设置代理
docker exec -e HTTPS_PROXY=http://your-proxy:port ollama ollama pull llama3.3
```

方案 C：直接下载 Ollama 后在本地运行（不通过 Docker）
```bash
# 在宿主机安装 Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 下载模型
ollama pull llama3.3

# 然后修改 docker-compose.yml 让 OpenClaw 连接本地 Ollama
```

### 2. "Ollama could not be reached" 警告
```
Ollama could not be reached at http://127.0.0.1:11434
```

**原因：** OpenClaw 使用环境变量 `OLLAMA_HOST=http://ollama:11434`，但在容器内部解析时可能有问题。

**验证连接：**
```bash
# 从 OpenClaw 容器内部测试
docker exec openclaw curl -s http://ollama:11434/api/tags

# 从宿主机测试（应该工作）
curl -s http://localhost:11434/api/tags
```

### 3. "Requested agent harness 'codex' is not registered" 错误
```
Embedded agent failed before reply: Requested agent harness "codex" is not registered.
```

**原因：** 这是 OpenClaw 的诊断功能尝试使用 Codex harness，但该 harness 未注册。

**状态：** 这是次要错误，不影响主要功能。OpenClaw 使用其他 agent harness 来处理请求。

**解决方案：** 如果需要使用 Codex，确保正确配置或在 OpenClaw 设置中禁用相关功能。

## 配置验证步骤

### 1. 检查 Ollama 服务
```bash
# 查看 Ollama 日志
docker-compose logs ollama --tail 20

# 测试 Ollama API
curl http://localhost:11434/api/tags

# 列出所有模型
docker exec ollama ollama list
```

### 2. 检查 OpenClaw 配置
```bash
# 查看 OpenClaw 环境变量
docker exec openclaw env | grep OLLAMA

# 查看 OpenClaw 配置
docker exec openclaw cat /root/.openclaw/config.json

# 列出 OpenClaw 模型
docker exec openclaw openclaw models list
```

### 3. 检查网络连接
```bash
# 从 OpenClaw 容器内测试 Ollama
docker exec openclaw ping -c 1 ollama
docker exec openclaw curl -v http://ollama:11434/
```

## 完整设置流程

### 步骤 1：确保服务运行
```bash
docker-compose up -d
```

### 步骤 2：下载模型（重要！）
```bash
# 方式 1：直接在容器内下载
docker exec -it ollama ollama pull llama3.3

# 方式 2：使用提供的脚本
./setup-models.sh
```

### 步骤 3：验证配置
```bash
# 检查模型是否可用
curl http://localhost:11434/api/tags

# 输出应该类似于：
# {"models":[{"name":"llama3.3","size":...,...}]}
```

### 步骤 4：访问 OpenClaw
打开浏览器访问：http://localhost:18789

### 步骤 5：配置 Agent 使用 Ollama 模型
在 OpenClaw 界面中：
1. 进入设置/配置
2. 选择 Agent 设置
3. 将默认模型设置为 `ollama/llama3.3`

## 推荐模型

### 适合新手
- **llama3.3**: 通用对话，8B 参数

### 高性能
- **gpt-oss:20b**: 大型开源模型（需要更多资源）
- **qwen2.5-coder:32b**: 代码专用模型

### 推理能力
- **deepseek-r1:32b**: 高级推理任务

## 故障排除命令

```bash
# 重启所有服务
docker-compose restart

# 查看所有日志
docker-compose logs -f

# 进入 Ollama 容器
docker exec -it ollama /bin/bash

# 进入 OpenClaw 容器
docker exec -it openclaw /bin/sh

# 清除 Ollama 模型缓存
docker exec ollama rm -rf /root/.ollama/models

# 完全重建
docker-compose down -v
docker-compose up -d
```

## 性能优化建议

### 使用 GPU
取消注释 docker-compose.yml 中的 `deploy` 配置：
```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: 1
          capabilities: [gpu]
```

### 增加并行处理
在 docker-compose.yml 中设置环境变量：
```yaml
environment:
  - OLLAMA_NUM_PARALLEL=2
  - OLLAMA_MAX_LOADED_MODELS=2
```

## 获取帮助

如果遇到问题，请：
1. 检查服务日志：`docker-compose logs -f`
2. 验证网络连接：测试容器间通信
3. 确认模型已下载：检查 Ollama 模型列表
4. 查看 OpenClaw 配置：验证配置文件是否正确应用