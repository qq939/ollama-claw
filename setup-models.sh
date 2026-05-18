#!/bin/bash
# Ollama 模型下载脚本

echo "正在检查 Ollama 服务状态..."
curl -s http://localhost:11434/api/tags > /dev/null
if [ $? -ne 0 ]; then
    echo "错误：Ollama 服务未运行"
    echo "请先运行: docker-compose up -d"
    exit 1
fi

echo "当前已安装的模型："
docker exec ollama ollama list

echo ""
echo "推荐下载的模型："
echo "1. llama3.3 - 通用对话模型（推荐新手）"
echo "2. gpt-oss:20b - 大型开源模型"
echo "3. qwen2.5-coder:32b - 代码专用模型"
echo "4. deepseek-r1:32b - 推理模型"
echo ""

read -p "请输入要下载的模型名称（或直接按回车下载 qwen2.5:0.5b）: " model

if [ -z "$model" ]; then
    model="qwen2.5:0.5b"
fi

echo "开始下载模型: $model"
echo "这可能需要几分钟到几十分钟，取决于网络速度和模型大小"
echo ""

docker exec -it ollama ollama pull $model

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ 模型下载完成！"
    echo ""
    echo "下载的模型列表："
    docker exec ollama ollama list
    echo ""
    echo "现在可以访问 OpenClaw: http://localhost:18789"
else
    echo ""
    echo "✗ 模型下载失败"
    exit 1
fi
