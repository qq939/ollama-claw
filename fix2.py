import re

with open('./control/app.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_func = '''    def send_openclaw_message(container, message):
        import base64
        msg_to_send = message or INITIAL_MESSAGE
        msg_b64 = base64.b64encode(msg_to_send.encode("utf-8")).decode("ascii")
        runner_path = f"{PROJECT_PATH}/.openclaw-send-message.sh"
        log_path = LOG_PATH
        runner = f"""#!/bin/sh
set -eu
mkdir -p "{LOGS_PATH}"
node -e 'const fs=require("fs"); const p=process.env.HOME+"/.openclaw/openclaw.json"; const j=JSON.parse(fs.readFileSync(p,"utf8")); j.gateway=j.gateway={{}}; j.gateway.mode="remote"; j.gateway.remote=j.gateway.remote={{}}; j.gateway.remote.url="ws://"+(process.env.OPENCLAW_GATEWAY_HOST||"172.30.0.10")+":"+(process.env.OPENCLAW_GATEWAY_PORT||"18790"); if(process.env.OPENCLAW_GATEWAY_TOKEN) j.gateway.remote.token=process.env.OPENCLAW_GATEWAY_TOKEN; delete j.gateway.bind; fs.writeFileSync(p,JSON.stringify(j,null,2)); fs.chmodSync(p,0o600);'
msg_file="$(mktemp /tmp/openclaw-message.XXXXXX)"
out_file="$(mktemp /tmp/openclaw-output.XXXXXX)"
trap 'rm -f "$msg_file" "$out_file"' EXIT
printf '%s' '{msg_b64}' | base64 -d > "$msg_file"
printf '\\n[openclaw-agent] %s\\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> "{log_path}"
if timeout 120 openclaw agent --agent main --message "$(cat "$msg_file")" --timeout 90 > "$out_file" 2>&1; then
  printf '[openclaw-agent-exit] 0\\n' >> "{log_path}"
else
  code="$?"
  printf '[openclaw-agent-exit] %s\\n' "$code" >> "{log_path}"
fi
sed -e 's/\\x1b\\[[0-?]*[ -\\/]*[@-~]//g' "$out_file" | tail -120 >> "{log_path}"
"""'''

new_func = '''    def send_openclaw_message(container, message):
        import base64
        labels = ((getattr(container, "attrs", {}) or {}).get("Config", {}) or {}).get("Labels", {}) or (getattr(container, "labels", {}) or {})
        agent_type = labels.get("hermit.agent_type") or "openclaw@2026.2.9"
        agent_paths = get_agent_paths(agent_type)
        project_path = agent_paths["project_path"]
        config_file = agent_paths["config_file"]
        agent_dir = agent_type.split("@")[0]
        
        msg_to_send = message or INITIAL_MESSAGE
        msg_b64 = base64.b64encode(msg_to_send.encode("utf-8")).decode("ascii")
        runner_path = f"{project_path}/.openclaw-send-message.sh"
        log_path = LOG_PATH
        runner = f"""#!/bin/sh
set -eu
mkdir -p "{LOGS_PATH}"
node -e 'const fs=require("fs"); const p=process.env.HOME+"/.{agent_dir}/"+"{config_file}"; if(fs.existsSync(p)){{const j=JSON.parse(fs.readFileSync(p,"utf8")); j.gateway=j.gateway={{}}; j.gateway.mode="remote"; j.gateway.remote=j.gateway={{}}; j.gateway.remote.url="ws://"+(process.env.OPENCLAW_GATEWAY_HOST||"172.30.0.10")+":"+(process.env.OPENCLAW_GATEWAY_PORT||"18790"); if(process.env.OPENCLAW_GATEWAY_TOKEN) j.gateway.remote.token=process.env.OPENCLAW_GATEWAY_TOKEN; delete j.gateway.bind; fs.writeFileSync(p,JSON.stringify(j,null,2)); fs.chmodSync(p,0o600);}}'
msg_file="$(mktemp /tmp/openclaw-message.XXXXXX)"
out_file="$(mktemp /tmp/openclaw-output.XXXXXX)"
trap 'rm -f "$msg_file" "$out_file"' EXIT
printf '%s' '{msg_b64}' | base64 -d > "$msg_file"
printf '\\n[{agent_type}] %s\\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> "{log_path}"
if timeout 120 openclaw agent --agent main --message "$(cat "$msg_file")" --timeout 90 > "$out_file" 2>&1; then
  printf '[{agent_type}-exit] 0\\n' >> "{log_path}"
else
  code="$?"
  printf '[{agent_type}-exit] %s\\n' "$code" >> "{log_path}"
fi
sed -e 's/\\x1b\\[[0-?]*[ -\\/]*[@-~]//g' "$out_file" | tail -120 >> "{log_path}"
"""'''

if old_func in content:
    content = content.replace(old_func, new_func)
    print("Replaced send_openclaw_message function")
else:
    print("Old function not found exactly, trying regex...")
    # Try regex approach
    pattern = r'def send_openclaw_message\(container, message\):.*?(?=\n    def append_user_log)'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        print(f"Found function at position {match.start()}")
        content = content[:match.start()] + new_func + '\n' + content[match.end():]
        print("Replaced via regex")
    else:
        print("Could not find function!")

with open('./control/app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done")