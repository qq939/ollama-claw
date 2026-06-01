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
    apt-get install -y --no-install-recommends ca-certificates sudo curl git coreutils openssh-server fonts-noto-cjk python3 python3-pip && \
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
    printf "{\"hasCompletedOnboarding\":true,\"hasTrustDialogAccepted\":true,\"hasCompletedProjectOnboarding\":true}" > /home/agent/.claude.json && \
    printf "#!/bin/bash\ncd /home/agent/.claude/workspace/project\nif [ -f user_start.sh ] && [ -s user_start.sh ]; then chmod +x user_start.sh; ./user_start.sh; fi\n" > /home/agent/.claude/workspace/project/start.sh && \
    chmod +x /home/agent/.claude/workspace/project/start.sh && \
    ssh-keygen -A && \
    chown -R 501:20 /etc/ssh/ssh_host_*_key && \
    chmod 0600 /etc/ssh/ssh_host_*_key && \
    chown -R 501:20 /home/agent/.claude /home/agent/.claude.json && \
    echo "=== Base setup complete ===" \
'

RUN bash -c ' \
    echo "=== Step 6: Install Claude CLI ===" && \
    npm config set registry https://registry.npmmirror.com && \
    for attempt in 1 2 3 4 5; do \
        set +e; \
        npm install -g @anthropic-ai/claude-code@2.0.69 --loglevel=error --prefer-offline 2>&1; \
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

ENV CLAUDE_CODE_TRUST_ALL=true
ENV CLAUDE_CODE_SKIP_ONBOARDING=true
ENV CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1
ENV AGENT_KIND=claude
ENV PROJECT_PATH=/home/agent/.claude/workspace/project
ENV LOG_PATH=/home/agent/.claude/workspace/project/logs/agent_tui.log
ENV ASK_PORT=8081
ENV SERVER_PORT=8082

COPY --chown=501:20 ask_server.js /usr/local/bin/ask_server.js
COPY --chown=501:20 server.js /usr/local/bin/server.js
COPY --chown=501:20 start.sh /usr/local/bin/start.sh

USER agent
WORKDIR /home/agent/.claude/workspace/project
EXPOSE 8082

CMD ["/bin/sh", "-lc", " \
    mkdir -p \"$HOME/.claude\"; \
    mkdir -p /home/agent/.claude/workspace/project/logs; \
    if [ -d /agent-config ]; then \
        for f in /agent-config/*; do \
            [ \"$f\" = \"/agent-config/workspace\" ] && continue; \
            [ -d \"$f\" ] && cp -R \"$f\" \"$HOME/.claude/\" 2>/dev/null || [ -f \"$f\" ] && cp -f \"$f\" \"$HOME/.claude/\" 2>/dev/null; \
        done; \
    fi; \
    /usr/sbin/sshd; \
    node -e 'const fs=require(\"fs\"); const p=process.env.HOME+\"/.claude/settings.json\"; let j={}; if(fs.existsSync(p)){ try{j=JSON.parse(fs.readFileSync(p,\"utf8\"));}catch(e){} } j.trustedProjects=[\"/home/agent/.claude/workspace/project\"]; j.hasCompletedOnboarding=true; j.hasTrustDialogAccepted=true; j.hasCompletedProjectOnboarding=true; fs.writeFileSync(p, JSON.stringify(j)); fs.writeFileSync(process.env.HOME+\"/.claude.json\", JSON.stringify({hasCompletedOnboarding:true,hasTrustDialogAccepted:true,hasCompletedProjectOnboarding:true}));'; \
    if [ -d \"$HOME/.claude/workspace/config-rules\" ]; then \
        echo '[config-rules] waiting for files...'; \
        for i in $(seq 1 30); do \
            if [ -f \"$HOME/.claude/workspace/config-rules/run_claude.js\" ]; then \
                cp -f \"$HOME/.claude/workspace/config-rules\"/* \"$HOME/.claude/workspace/project/\" 2>/dev/null; \
                chmod +x \"$HOME/.claude/workspace/project/run_claude.js\" 2>/dev/null; \
                echo '[config-rules] copied'; \
                break; \
            fi; \
            echo \"[config-rules] waiting... ($i/30)\"; \
            sleep 2; \
        done; \
    fi; \
    cp -f /usr/local/bin/start.sh /home/agent/.claude/workspace/project/start.sh; \
    chmod +x /home/agent/.claude/workspace/project/start.sh; \
    if [ -f /home/agent/.claude/workspace/project/start.sh ] && [ -s /home/agent/.claude/workspace/project/start.sh ]; then \
        chmod +x /home/agent/.claude/workspace/project/start.sh; \
        nohup bash /home/agent/.claude/workspace/project/start.sh >> /home/agent/.claude/workspace/project/logs/start.log 2>&1 & \
    fi; \
    exec tail -f /dev/null"]
