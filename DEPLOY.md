# Ollama-Claw 部署指南

## 部署步骤

### 1. 在第一台机器上构建并推送镜像

```bash
# 进入项目目录
cd ollama-claw

# 构建所有镜像
docker compose build

# 登录 Docker Hub（或其他 registry）
docker login

# 标记镜像（替换 YOUR_USERNAME 为你的 Docker Hub 用户名）
docker tag ollama-claw-agent-openclaw:latest YOUR_USERNAME/ollama-claw-agent-openclaw:latest
docker tag ollama-claw-ollama:latest YOUR_USERNAME/ollama-claw-ollama:latest
docker tag ollama-claw-gateway:latest YOUR_USERNAME/ollama-claw-gateway:latest
docker tag ollama-claw-control:latest YOUR_USERNAME/ollama-claw-control:latest

# 推送镜像
docker push YOUR_USERNAME/ollama-claw-agent-openclaw:latest
docker push YOUR_USERNAME/ollama-claw-ollama:latest
docker push YOUR_USERNAME/ollama-claw-gateway:latest
docker push YOUR_USERNAME/ollama-claw-control:latest
```

### 2. 在其他机器上部署

#### 方式 A：使用 Docker Hub（推荐）

```bash
# 在其他机器上创建项目目录
mkdir -p ollama-claw && cd ollama-claw

# 下载 docker-compose.yml（可以只下载这个文件）
# 然后修改镜像地址为你的用户名下的镜像

# 下载配置文件（需要包含 config/openclaw/openclaw.json）
# 或者手动创建 config 目录

# 运行（会自动拉取镜像）
docker compose up -d
```

需要修改 `docker-compose.yml` 中的镜像地址：

```yaml
agent-image-openclaw:
  image: YOUR_USERNAME/ollama-claw-agent-openclaw:latest  # 改为你的镜像地址

ollama:
  image: YOUR_USERNAME/ollama-claw-ollama:latest

openclaw-gateway:
  image: YOUR_USERNAME/ollama-claw-gateway:latest

control-18080:
  image: YOUR_USERNAME/ollama-claw-control:latest
```

#### 方式 B：使用阿里云容器镜像服务

```bash
# 1. 登录阿里云 Docker Registry
docker login --username=你的阿里云用户名 registry.cn-hangzhou.aliyuncs.com

# 2. 标记镜像
docker tag ollama-claw-agent-openclaw:latest registry.cn-hangzhou.aliyuncs.com/你的命名空间/ollama-claw-agent-openclaw:latest

# 3. 推送
docker push registry.cn-hangzhou.aliyuncs.com/你的命名空间/ollama-claw-agent-openclaw:latest
```

#### 方式 C：使用 GitHub Container Registry

```bash
# 1. 登录 GHCR
echo $GITHUB_TOKEN | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin

# 2. 标记镜像
docker tag ollama-claw-agent-openclaw:latest ghcr.io/YOUR_USERNAME/ollama-claw-agent-openclaw:latest

# 3. 推送
docker push ghcr.io/YOUR_USERNAME/ollama-claw-agent-openclaw:latest
```

### 3. 验证部署

```bash
# 检查容器状态
docker compose ps

# 测试 API
curl http://localhost:18080/api/health

# 查看日志
docker compose logs -f
```

## 常见问题

### 问题 1：Agent image missing

**错误信息：**
```
Agent image missing. Please run: docker compose build
```

**解决方案：**
1. 确保在部署前构建了所有镜像：
   ```bash
   docker compose build
   ```

2. 或者确保镜像已推送到 registry，并在其他机器上正确拉取

### 问题 2：镜像拉取失败

**解决方案：**
1. 检查网络连接
2. 确认登录了正确的 registry
3. 检查镜像名称和标签是否正确

### 问题 3：端口被占用

**解决方案：**
修改 `docker-compose.yml` 中的端口映射：
```yaml
ports:
  - "18081:8080"  # 改为其他端口
```

## 快速部署脚本

创建 `deploy.sh`：

```bash
#!/bin/bash
set -e

# 替换为你的 Docker Hub 用户名
DOCKER_USERNAME="YOUR_USERNAME"

# 镜像列表
IMAGES=(
    "ollama-claw-agent-openclaw:latest"
    "ollama-claw-ollama:latest"
    "ollama-claw-gateway:latest"
    "ollama-claw-control:latest"
)

# 登录 Docker Hub
docker login

# 推送镜像
for img in "${IMAGES[@]}"; do
    docker tag "$img" "${DOCKER_USERNAME}/${img}"
    docker push "${DOCKER_USERNAME}/${img}"
done

echo "✓ 所有镜像已推送完成"
echo "在其他机器上部署时，请修改 docker-compose.yml 中的镜像地址为："
echo "  - ${DOCKER_USERNAME}/ollama-claw-agent-openclaw:latest"
echo "  - ${DOCKER_USERNAME}/ollama-claw-ollama:latest"
echo "  - ${DOCKER_USERNAME}/ollama-claw-gateway:latest"
echo "  - ${DOCKER_USERNAME}/ollama-claw-control:latest"
```

设置执行权限并运行：
```bash
chmod +x deploy.sh
./deploy.sh
```
