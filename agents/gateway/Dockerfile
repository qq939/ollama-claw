FROM node:22-bookworm-slim

RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && apt-get install -y --no-install-recommends ca-certificates sudo curl git coreutils && \
    rm -rf /var/lib/apt/lists/*

RUN npm install -g openclaw@2026.2.9 --registry=https://registry.npmmirror.com

RUN useradd -m -s /bin/bash agent \
    && echo "agent ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/agent \
    && chmod 0440 /etc/sudoers.d/agent

USER agent
WORKDIR /home/agent/.openclaw/workspace/project
EXPOSE 18790

CMD ["/bin/sh", "-lc", "mkdir -p \"$HOME/.openclaw\"; if [ -d /agent-config ]; then cp -R -f /agent-config/. \"$HOME/.openclaw/\"; fi; node -e 'const fs=require(\"fs\"); const p=process.env.HOME+\"/.openclaw/openclaw.json\"; const token=process.env.OPENCLAW_GATEWAY_TOKEN||\"\"; const port=Number(process.env.OPENCLAW_GATEWAY_PORT||18790); let j={}; if(fs.existsSync(p)){try{j=JSON.parse(fs.readFileSync(p,\"utf8\"));}catch(e){}} if(!j.gateway){j.gateway={};} j.gateway.mode=\"local\"; j.gateway.port=port; j.gateway.bind=\"lan\"; j.gateway.auth=j.gateway.auth||{}; j.gateway.auth.mode=\"token\"; if(token){j.gateway.auth.token=token;} j.gateway.remote=j.gateway.remote||{}; j.gateway.remote.url=\"ws://127.0.0.1:\"+port; if(j.gateway.auth.token){j.gateway.remote.token=j.gateway.auth.token;} if(j.agents&&j.agents.defaults){j.agents.defaults.workspace=\"/home/agent/.openclaw/workspace/project\";} fs.writeFileSync(p,JSON.stringify(j,null,2)); try{fs.chmodSync(p,0o600)}catch(e){}'; mkdir -p /home/agent/.openclaw/workspace/project/logs; (openclaw gateway run --force --bind lan --port ${OPENCLAW_GATEWAY_PORT:-18790} --token \"$OPENCLAW_GATEWAY_TOKEN\" --ws-log compact --verbose > /home/agent/.openclaw/workspace/project/logs/gateway.log 2>&1 &); while true; do sleep 1; done"]
