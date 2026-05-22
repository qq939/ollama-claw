FROM node:22-bookworm-slim

RUN bash -c ' \
    echo "=== Step 1: Update apt ===" && \
    sed -i "s/deb.debian.org/mirrors.aliyun.com/g" /etc/apt/sources.list.d/debian.sources && \
    for attempt in 1 2 3; do \
        set +e; \
        apt-get update && break; \
        sleep 10; \
    done && \
    echo "=== Step 2: Install packages ===" && \
    apt-get install -y --no-install-recommends ca-certificates sudo curl git coreutils openssh-server python3 python3-pip && \
    echo "=== Step 3: Verify packages ===" && \
    dpkg -l openssh-server && \
    which sshd || (echo "ERROR: sshd not found!"; exit 1) && \
    rm -rf /var/lib/apt/lists/* && \
    echo "=== Step 4: Configure SSH ===" && \
    mkdir -p /var/run/sshd && \
    sed -i "s/#PermitRootLogin prohibit-password/PermitRootLogin no/" /etc/ssh/sshd_config && \
    sed -i "s/#PasswordAuthentication yes/PasswordAuthentication yes/" /etc/ssh/sshd_config && \
    sed -i "s/#PermitEmptyPasswords no/PermitEmptyPasswords no/" /etc/ssh/sshd_config && \
    echo "=== Step 5: Create agent user ===" && \
    useradd -m -s /bin/bash -u 501 -g 20 agent && \
    echo "agent:agent" | chpasswd && \
    echo "agent ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/agent && \
    chmod 0440 /etc/sudoers.d/agent && \
    mkdir -p /home/agent/.claude/workspace/project/logs && \
    printf "#!/bin/bash\ncd /home/agent/.claude/workspace/project\nif [ -f user_start.sh ] && [ -s user_start.sh ]; then chmod +x user_start.sh; ./user_start.sh; fi\n" > /home/agent/.claude/workspace/project/start.sh && \
    chmod +x /home/agent/.claude/workspace/project/start.sh && \
    ssh-keygen -A && \
    chown -R 501:20 /etc/ssh/ssh_host_*_key && \
    chmod 0600 /etc/ssh/ssh_host_*_key && \
    chown -R 501:20 /home/agent/.claude && \
    echo "=== Base setup complete ===" \
'

RUN bash -c ' \
    echo "=== Step 6: Install Claude CLI ===" && \
    npm config set registry https://registry.npmmirror.com && \
    for attempt in 1 2 3 4 5; do \
        set +e; \
        npm install -g @anthropic-ai/claude-code@latest --loglevel=error --prefer-offline 2>&1; \
        result=$?; \
        if [ $result -eq 0 ] || [ -n "$(which claude 2>/dev/null)" ]; then \
            echo "claude installed successfully"; \
            break; \
        fi; \
        echo "Attempt $attempt failed, retrying..."; \
        sleep 30; \
    done; \
    echo "=== Step 7: Verify Claude CLI ===" && \
    which claude || (echo "ERROR: claude not found!"; exit 1) && \
    echo "=== Claude CLI install complete ===" \
'

USER agent
WORKDIR /home/agent
EXPOSE 8082

CMD ["/bin/sh", "-lc", " \
    mkdir -p \"$HOME/.claude\"; \
    if [ -d /agent-config ]; then cp -R -f /agent-config/. \"$HOME/.claude/\"; fi; \
    mkdir -p \"$HOME/.claude/workspace/project/logs\"; \
    /usr/sbin/sshd; \
    node -e ' \
        const fs=require(\"fs\"); \
        const gh=process.env.OPENCLAW_GATEWAY_HOST||\"172.30.0.10\"; \
        const gp=process.env.OPENCLAW_GATEWAY_PORT||\"18790\"; \
        const p=process.env.HOME+\"/.claude/settings.json\"; \
        if(fs.existsSync(p)){ \
            const j=JSON.parse(fs.readFileSync(p,\"utf8\")); \
            if(j.claudeCode && j.claudeCode.agent){ \
                j.claudeCode.agent.workspace=process.env.HOME+\"/.claude/workspace/project\"; \
            } \
            j.gateway = j.gateway || {}; \
            j.gateway.mode = \"remote\"; \
            j.gateway.port = 18790; \
            j.gateway.auth = j.gateway.auth || {}; \
            j.gateway.remote = j.gateway.remote || {}; \
            j.gateway.remote.url = \"ws://\" + gh + \":\" + gp; \
            if(j.gateway.auth && j.gateway.auth.token){ \
                j.gateway.remote.token = j.gateway.auth.token; \
            } \
            delete j.gateway.bind; \
            fs.writeFileSync(p, JSON.stringify(j, null, 2)); \
            try { fs.chmodSync(p, 0o600); } catch(e) {} \
        } \
    '; \
    cd \"$HOME/.claude/workspace/project\"; \
    if [ -f start.sh ] && [ -s start.sh ]; then \
        chmod +x start.sh; \
        nohup bash start.sh >> \"$HOME/.claude/workspace/project/logs/start.log\" 2>&1 & \
    fi; \
    exec claude run --url \"ws://$OPENCLAW_GATEWAY_HOST:$OPENCLAW_GATEWAY_PORT\" --token \"$OPENCLAW_GATEWAY_TOKEN\""]