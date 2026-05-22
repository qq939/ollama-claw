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
    mkdir -p /home/agent/.hermes/workspace/project/logs && \
    printf "#!/bin/bash\ncd /home/agent/.hermes/workspace/project\nif [ -f user_start.sh ] && [ -s user_start.sh ]; then chmod +x user_start.sh; ./user_start.sh; fi\n" > /home/agent/.hermes/workspace/project/start.sh && \
    chmod +x /home/agent/.hermes/workspace/project/start.sh && \
    ssh-keygen -A && \
    chown -R 501:20 /etc/ssh/ssh_host_*_key && \
    chmod 0600 /etc/ssh/ssh_host_*_key && \
    chown -R 501:20 /home/agent/.hermes && \
    echo "=== Base setup complete ===" \
'

RUN bash -c ' \
    echo "=== Step 6: Install Hermes CLI ===" && \
    curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash 2>&1 || \
    npm config set registry https://registry.npmmirror.com && \
    for attempt in 1 2 3 4 5; do \
        set +e; \
        npm install -g @nousresearch/hermes-agent --loglevel=error --prefer-offline 2>&1; \
        result=$?; \
        if [ $result -eq 0 ] || [ -n "$(which hermes 2>/dev/null)" ]; then \
            echo "hermes installed successfully"; \
            break; \
        fi; \
        echo "Attempt $attempt failed, retrying..."; \
        sleep 30; \
    done; \
    echo "=== Step 7: Verify Hermes CLI ===" && \
    which hermes || (echo "ERROR: hermes not found!"; exit 1) && \
    echo "=== Hermes CLI install complete ===" \
'

USER agent
WORKDIR /home/agent/.hermes/workspace/project
EXPOSE 8082

CMD ["/bin/sh", "-lc", " \
    mkdir -p \"$HOME/.hermes\"; \
    if [ -d /agent-config ]; then cp -R -f /agent-config/. \"$HOME/.hermes/\"; fi; \
    mkdir -p /home/agent/.hermes/workspace/project/logs; \
    /usr/sbin/sshd; \
    if [ -f /home/agent/.hermes/workspace/project/start.sh ] && [ -s /home/agent/.hermes/workspace/project/start.sh ]; then \
        chmod +x /home/agent/.hermes/workspace/project/start.sh; \
        nohup bash /home/agent/.hermes/workspace/project/start.sh >> /home/agent/.hermes/workspace/project/logs/start.log 2>&1 & \
    fi; \
    exec hermes"]