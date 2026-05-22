import re

with open('./control/app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 定义新的send_openclaw_message函数
new_function = '''def send_openclaw_message(container, message):
        import base64
        labels = ((getattr(container, "attrs", {}) or {}).get("Config", {}) or {}).get("Labels", {}) or (getattr(container, "labels", {}) or {})
        agent_type = labels.get("hermit.agent_type") or "openclaw@2026.2.9"
        agent_paths = get_agent_paths(agent_type)
        project_path = agent_paths["project_path"]
        config_file = agent_paths["config_file"]
        
        msg_to_send = message or INITIAL_MESSAGE
        msg_b64 = base64.b64encode(msg_to_send.encode("utf-8")).decode("ascii")
        runner_path = f"{project_path}/.openclaw-send-message.sh"
        log_path = LOG_PATH
        agent_dir = agent_type.split("@")[0]
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
"""
        runner_b64 = base64.b64encode(runner.encode("utf-8")).decode("ascii")
        write_cmd = f"printf '%s' '{runner_b64}' | base64 -d > '{runner_path}' && chmod +x '{runner_path}'"
        result = container.exec_run(["/bin/sh", "-lc", write_cmd], user=AGENT_RUNTIME_USER)
        if result.exit_code != 0:
            output = result.output.decode("utf-8", errors="replace") if isinstance(result.output, bytes) else str(result.output)
            raise RuntimeError(output or "failed to write OpenClaw message runner")
        run_cmd = f"nohup /bin/sh '{runner_path}' >> '{log_path}' 2>&1 &"
        result = container.exec_run(["/bin/sh", "-lc", run_cmd], user=AGENT_RUNTIME_USER, detach=True)
        env = container_env(container)
        token = env.get("OPENCLAW_GATEWAY_TOKEN", "")
        if token:
            time.sleep(2)
            if auto_pair_openclaw_client(token, timeout_seconds=3):
                container.exec_run(["/bin/sh", "-lc", run_cmd], user=AGENT_RUNTIME_USER, detach=True)
        return result

'''

# 找到函数并替换
# 查找从 "def send_openclaw_message" 到下一个 "def append_user_log" 的内容
pattern = r'def send_openclaw_message\(container, message\):.*?(?=\n    def append_user_log)'
if re.search(pattern, content, re.DOTALL):
    content = re.sub(pattern, new_function.strip(), content, flags=re.DOTALL)
    print("Replaced send_openclaw_message function")
else:
    print("Pattern not found, trying alternative...")
    # 尝试直接查找函数开始
    if 'def send_openclaw_message(container, message):' in content:
        print("Found function start")
    else:
        print("Function start not found")

with open('./control/app.py', 'w', encoding='utf-8') as f:
    f.write(content)