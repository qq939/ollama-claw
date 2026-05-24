with open('./control/app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. First, add agent type detection at the start of the function
old_start = '''    def send_openclaw_message(container, message):
        import base64
        msg_to_send = message or INITIAL_MESSAGE'''

new_start = '''    def send_openclaw_message(container, message):
        import base64
        labels = ((getattr(container, "attrs", {}) or {}).get("Config", {}) or {}).get("Labels", {}) or (getattr(container, "labels", {}) or {})
        agent_type = labels.get("hermit.agent_type") or "openclaw@2026.2.9"
        agent_paths = get_agent_paths(agent_type)
        project_path = agent_paths["project_path"]
        config_file = agent_paths["config_file"]
        agent_dir = agent_type.split("@")[0]
        
        msg_to_send = message or INITIAL_MESSAGE'''

# 2. Replace PROJECT_PATH with project_path
old_path = 'f"{PROJECT_PATH}/.openclaw-send-message.sh"'
new_path = 'f"{project_path}/.openclaw-send-message.sh"'

# 3. Replace hardcoded .openclaw/openclaw.json with dynamic path
old_config = "node -e 'const fs=require(\"fs\"); const p=process.env.HOME+\"/.openclaw/openclaw.json\""
new_config = "node -e 'const fs=require(\"fs\"); const p=process.env.HOME+\"/.{agent_dir}/\"+\"{config_file}\""

# 4. Add if exists check after reading config
old_read = "const j=JSON.parse(fs.readFileSync(p,\"utf8\")); j.gateway=j.gateway={{}}; j.gateway.mode=\"remote\""
new_read = "if(fs.existsSync(p)){{const j=JSON.parse(fs.readFileSync(p,\"utf8\")); j.gateway=j.gateway={{}}; j.gateway.mode=\"remote\""

# 5. Close the if block after chmodSync
old_close = "fs.chmodSync(p,0o600);'\\nmsg_file="
new_close = "fs.chmodSync(p,0o600);}}'\\nmsg_file="

# 6. Replace hardcoded [openclaw-agent] with [agent_type]
old_log1 = "printf '\\\\n[openclaw-agent] %s\\\\n'"
new_log1 = "printf '\\\\n[{agent_type}] %s\\\\n'"

old_log2 = "printf '[openclaw-agent-exit] 0\\\\n'"
new_log2 = "printf '[{agent_type}-exit] 0\\\\n'"

old_log3 = "printf '[openclaw-agent-exit] %s\\\\n'"
new_log3 = "printf '[{agent_type}-exit] %s\\\\n'"

# Apply all replacements
changes = [
    (old_start, new_start),
    (old_path, new_path),
    (old_config, new_config),
    (old_read, new_read),
    (old_close, new_close),
    (old_log1, new_log1),
    (old_log2, new_log2),
    (old_log3, new_log3),
]

for old, new in changes:
    if old in content:
        content = content.replace(old, new)
        print(f"Replaced: {old[:50]}...")
    else:
        print(f"NOT FOUND: {old[:50]}...")

with open('./control/app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done")