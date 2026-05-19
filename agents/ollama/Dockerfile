FROM debian:bookworm-slim

RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    bash -c ' \
    for attempt in 1 2 3; do \
        set +e; \
        apt-get update && apt-get install -y --no-install-recommends \
            ca-certificates sudo curl git gnupg python3 fonts-noto-cjk \
            && break; \
        sleep 10; \
    done; \
    rm -rf /var/lib/apt/lists/* \
'

RUN curl -fsSL https://ollama.com/install.sh | sh || true

RUN useradd -m -s /bin/bash -u 501 -g 20 agent \
    && echo "agent:agent" | chpasswd \
    && echo "agent ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/agent \
    && chmod 0440 /etc/sudoers.d/agent \
    && mkdir -p /home/agent/.ollama

ENV OLLAMA_HOST=0.0.0.0
ENV OLLAMA_PORT=11434

EXPOSE 11434

CMD ["/bin/sh", "-lc", " \
    mkdir -p \"$HOME/.ollama\"; \
    if [ -d /agent-config ]; then cp -R -f /agent-config/. \"$HOME/.ollama/\" 2>/dev/null; fi; \
    if ! pgrep ollama > /dev/null 2>&1; then \
        nohup ollama serve >> \"$HOME/.ollama/ollama.log\" 2>&1 & \
        sleep 5; \
    fi; \
    exec tail -f /dev/null \
"]