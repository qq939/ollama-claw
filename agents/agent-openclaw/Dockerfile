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
    mkdir -p /home/agent/.openclaw/workspace/project/logs && \
    printf "#!/bin/bash\ncd /home/agent/.openclaw/workspace/project\nif [ -f user_start.sh ] && [ -s user_start.sh ]; then chmod +x user_start.sh; ./user_start.sh; fi\n" > /home/agent/.openclaw/workspace/project/start.sh && \
    chmod +x /home/agent/.openclaw/workspace/project/start.sh && \
    ssh-keygen -A && \
    chown -R 501:20 /etc/ssh/ssh_host_*_key && \
    chmod 0600 /etc/ssh/ssh_host_*_key && \
    chown -R 501:20 /home/agent/.openclaw && \
    echo "=== Base setup complete ===" \
'

RUN bash -c ' \
    echo "=== Step 6: Install openclaw ===" && \
    npm config set registry https://registry.npmmirror.com && \
    for attempt in 1 2 3 4 5; do \
        set +e; \
        npm install -g openclaw@2026.2.9 --loglevel=error --prefer-offline 2>&1; \
        result=$?; \
        if [ $result -eq 0 ] || [ -n "$(which openclaw 2>/dev/null)" ]; then \
            echo "openclaw installed successfully"; \
            break; \
        fi; \
        echo "Attempt $attempt failed, retrying..."; \
        sleep 30; \
    done; \
    echo "=== Step 7: Verify openclaw ===" && \
    which openclaw || (echo "ERROR: openclaw not found!"; exit 1) && \
    echo "=== openclaw install complete ===" \
'

USER agent
ENV AGENT_KIND=openclaw
ENV PROJECT_PATH=/home/agent/.openclaw/workspace/project
ENV LOG_PATH=/home/agent/.openclaw/workspace/project/logs/agent_tui.log
ENV ASK_PORT=8081
ENV SERVER_PORT=8082
COPY --chown=501:20 ask_server.js /usr/local/bin/ask_server.js
COPY --chown=501:20 server.js /usr/local/bin/server.js
COPY --chown=501:20 start.sh /usr/local/bin/start.sh

WORKDIR /home/agent/.openclaw/workspace/project
EXPOSE 8082

CMD ["/bin/sh", "-lc", " \
    mkdir -p \"$HOME/.openclaw\"; \
    if [ -d /agent-config ]; then \
        for f in /agent-config/*; do \
            [ \"$f\" = \"/agent-config/workspace\" ] && continue; \
            [ \"$f\" = \"/agent-config/rules\" ] && continue; \
            [ -d \"$f\" ] && cp -R \"$f\" \"$HOME/.openclaw/\" 2>/dev/null || [ -f \"$f\" ] && cp -f \"$f\" \"$HOME/.openclaw/\" 2>/dev/null; \
        done; \
    fi; \
    mkdir -p /home/agent/.openclaw/workspace/project/logs; \
    /usr/sbin/sshd; \
    node -e ' \
        const fs=require(\"fs\"); \
        const gh=process.env.OPENCLAW_GATEWAY_HOST||\"172.31.0.10\"; \
        const gp=process.env.OPENCLAW_GATEWAY_PORT||\"18790\"; \
        const p=process.env.HOME+\"/.openclaw/openclaw.json\"; \
        if(fs.existsSync(p)){ \
            const j=JSON.parse(fs.readFileSync(p,\"utf8\")); \
            if(j.agents && j.agents.defaults){ \
                j.agents.defaults.workspace=\"/home/agent/.openclaw/workspace/project\"; \
            } \
            j.gateway = j.gateway || {}; \
            j.gateway.mode = \"remote\"; \
            j.gateway.port = 18790; \
            j.gateway.auth = j.gateway.auth || {}; \
            j.gateway.remote = j.gateway.remote || {}; \
            j.gateway.remote.url = \"ws://\" + gh + \":\" + gp; \
            if(j.gateway.auth.token){ \
                j.gateway.remote.token = j.gateway.auth.token; \
            } \
            delete j.gateway.bind; \
            fs.writeFileSync(p, JSON.stringify(j, null, 2)); \
            try { fs.chmodSync(p, 0o600); } catch(e) {} \
        } \
    '; \
    cp -f /usr/local/bin/start.sh /home/agent/.openclaw/workspace/project/start.sh; \
    chmod +x /home/agent/.openclaw/workspace/project/start.sh; \
    if [ -f /home/agent/.openclaw/workspace/project/start.sh ] && [ -s /home/agent/.openclaw/workspace/project/start.sh ]; then \
        chmod +x /home/agent/.openclaw/workspace/project/start.sh; \
        nohup bash /home/agent/.openclaw/workspace/project/start.sh >> /home/agent/.openclaw/workspace/project/logs/start.log 2>&1 & \
    fi; \
    exec openclaw tui --url \"ws://$OPENCLAW_GATEWAY_HOST:$OPENCLAW_GATEWAY_PORT\" --token \"$OPENCLAW_GATEWAY_TOKEN\""]
