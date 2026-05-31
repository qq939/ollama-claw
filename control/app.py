INITIAL_MESSAGE = "你负责的是完整的开发、测试、发现bug、变更的流程，项目是web app 8082（端口号），web app 8082所在的目录是/home/agent/.openclaw/workspace/project，如果project文件夹有web app，请查看启动脚本是否存在，/home/agent/.openclaw/workspace/project/user_start.sh。如果不存在启动脚本，请立即写好启动脚本user_start.sh，输出日志到当前目录下的logs/start.log。并且整理日志文件logs/agent_tui.log里的主要内容，梳理出项目构建的结构和细节，总结最后3轮对话的内容。项目所有惯例信息都在systemreadme.md中记载，最后更新项目README.md和项目SKILL.md"
# Used in docker compose volume mount (docker-compose.yml) to bind frpc binary into containers.
FRPC_PATH = "/Users/jimjiang/Downloads/frpc"
import os
import re
import sys
import time
import json
import threading
import urllib.request
from datetime import datetime, timezone, timedelta
from io import BytesIO

import docker
from docker.types import LogConfig
from flask import Flask, jsonify, make_response, request, send_file
from flask_sock import Sock

# GLOBAL PARAMETERS
# Control panel base port - all other ports are relative to this
CONTROL_BASE_PORT = int(os.environ.get("CONTROL_BASE_PORT", 18080))
# Used in find_next_port (line 76) as the first generated agent host port.
START_HOST_PORT = CONTROL_BASE_PORT + 1
# Used in find_next_port (line 76) as the upper bound for generated host ports.
END_HOST_PORT = 18999
# Used in create_agent (line 123) and API responses to enforce fixed in-container service port.
SERVICE_PORT = 8082
PROJECT_PATH = "/home/agent/.openclaw/workspace/project"
SESSIONS_PATH = "/home/agent/.openclaw/projects"
LOG_PATH = f"{PROJECT_PATH}/logs/agent_tui.log"
LOGS_PATH = f"{PROJECT_PATH}/logs"
RULES_PATH = "/home/agent/.openclaw/workspace/config-rules"
# Used in helper filters (line 52, 67) to identify containers created by this control plane.
MANAGED_LABEL_KEY = "hermit.managed"
# Used in create_agent (line 139) to mark new containers as managed by this control plane.
MANAGED_LABEL_VALUE = "true"
# Used in create_agent (line 127, 144) and validation to map UI type to image/config directory.
AGENT_SPECS = {
    "openclaw@2026.2.9": {"image": "ollama-claw-agent-openclaw:latest", "config_subdir": "openclaw"},
    "claude@latest": {"image": "ollama-claw-agent-claude:latest", "config_subdir": "claude"},
    "hermes@latest": {"image": "ollama-claw-agent-hermes:latest", "config_subdir": "hermes"},
}
AGENT_PATHS = {
    "openclaw@2026.2.9": {"project_path": "/home/agent/.openclaw/workspace/project", "sessions_path": "/home/agent/.openclaw/projects", "rules_path": "/home/agent/.openclaw/workspace/config-rules", "config_file": "openclaw.json"},
    "claude@latest": {"project_path": "/home/agent/.claude/workspace/project", "sessions_path": "/home/agent/.claude/projects", "rules_path": "/home/agent/.claude/workspace/config-rules", "config_file": "openclaw.json"},
    "hermes@latest": {"project_path": "/home/agent/.hermes/workspace/project", "sessions_path": "/home/agent/.hermes/projects", "rules_path": "/home/agent/.hermes/workspace/config-rules", "config_file": "openclaw.json"},
}

def get_agent_paths(agent_type):
    return AGENT_PATHS.get(agent_type, AGENT_PATHS["openclaw@2026.2.9"])

# Used in API handlers (line 259, 300, 310) as default line count shown in each card.
DEFAULT_TAIL_LINES = 200
# Used in _safe_name_part (line 92) to sanitize user-provided agent names.
NAME_SANITIZE_PATTERN = re.compile(r"[^a-zA-Z0-9_-]+")
COMMIT_HASH_PATTERN = re.compile(r"^[0-9a-fA-F]{4,40}$")
ANSI_ESCAPE_PATTERN = re.compile(r"(?:\x1b\][^\x07]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]|\x1b[()][A-Za-z0-9])")
# Used in create_agent (line 132) and api_command (line 247) so container startup and exec run as non-root agent user.
AGENT_RUNTIME_USER = "agent"
# Used in create_app (line 46-50) and create_agent (line 118-130) to translate in-container paths to actual host bind mount paths when creating new containers via Docker socket.
HOST_CONFIG_ROOT_ENV = "HOST_CONFIG_ROOT"
# Used in create_app (line 46-50) and create_agent (line 118-130) to translate in-container paths to actual host bind mount paths when creating new containers via Docker socket.
HOST_WORKSPACES_ROOT_ENV = "HOST_WORKSPACES_ROOT"
GATEWAY_CONTAINER_ENV = "OPENCLAW_GATEWAY_CONTAINER"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def create_app(docker_client=None):
    app = Flask(__name__)
    sock = Sock(app)
    app.config["DOCKER_CLIENT"] = docker_client
    app.config["CONFIG_ROOT"] = "/config"
    app.config["WORKSPACES_ROOT"] = "/workspaces"
    app.config["HOST_CONFIG_ROOT"] = os.environ.get(HOST_CONFIG_ROOT_ENV) or app.config["CONFIG_ROOT"]
    # 容器内将 host.docker.internal 替换为宿主机实际路径（如果是相对路径 ./config）
    host_cfg = app.config["HOST_CONFIG_ROOT"]
    if host_cfg.startswith("./"):
        import subprocess
        try:
            pwd = subprocess.check_output(["sh", "-c", "echo $PWD"], text=True).strip()
            host_cfg = pwd + host_cfg[1:]
        except:
            pass
        app.config["HOST_CONFIG_ROOT"] = host_cfg
    app.config["HOST_WORKSPACES_ROOT"] = os.environ.get(HOST_WORKSPACES_ROOT_ENV) or app.config["WORKSPACES_ROOT"]
    # 处理相对路径 logs
    host_ws = app.config["HOST_WORKSPACES_ROOT"]
    if host_ws.startswith("./"):
        import subprocess
        try:
            pwd = subprocess.check_output(["sh", "-c", "echo $PWD"], text=True).strip()
            host_ws = pwd + host_ws[1:]
        except:
            pass
    app.config["HOST_WORKSPACES_ROOT"] = host_ws
    app.config["HOST_LOGS_ROOT"] = os.path.join(os.path.dirname(host_ws), "logs")
    app.config["PUBLIC_PREVIEW_BASE_URL"] = os.environ.get("PUBLIC_PREVIEW_BASE_URL", "http://localhost").rstrip("/")
    ollama_pull_jobs = {}
    ollama_api_state = {"base_url": None}

    def ollama_base_urls():
        configured = os.environ.get("OLLAMA_BASE_URL", "").strip()
        candidates = []
        if configured:
            candidates.extend([item.strip() for item in configured.split(",") if item.strip()])
        candidates.extend([
            "http://ollama:11434",
            "http://host.docker.internal:11434",
        ])
        if ollama_api_state.get("base_url"):
            candidates.insert(0, ollama_api_state["base_url"])
        deduped = []
        for item in candidates:
            normalized = item.rstrip("/")
            if normalized and normalized not in deduped:
                deduped.append(normalized)
        return deduped

    def ollama_json_request(path, payload=None, timeout=10):
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        errors = []
        for base_url in ollama_base_urls():
            try:
                req = urllib.request.Request(f"{base_url}{path}", data=data, headers=headers)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw = resp.read().decode("utf-8")
                ollama_api_state["base_url"] = base_url
                return json.loads(raw) if raw else {}
            except Exception as e:
                errors.append(f"{base_url}: {e}")
        raise RuntimeError("Unable to reach Ollama API. Tried " + "; ".join(errors))

    def ollama_stream_request(path, payload=None, timeout=60 * 60):
        data = None
        headers = {"Content-Type": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
        errors = []
        for base_url in ollama_base_urls():
            try:
                req = urllib.request.Request(f"{base_url}{path}", data=data, headers=headers)
                req.add_header("Accept", "application/json")
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    content_type = resp.headers.get("Content-Type", "")
                    for line in resp:
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith(b"data:"):
                            line = line[5:].strip()
                        try:
                            yield json.loads(line.decode("utf-8"))
                        except json.JSONDecodeError:
                            pass
                return
            except Exception as e:
                errors.append(f"{base_url}: {e}")

    def list_ollama_models():
        data = ollama_json_request("/api/tags", timeout=5)
        return data.get("models", [])

    def docker_client_or_default():
        configured = app.config.get("DOCKER_CLIENT")
        if configured is not None:
            return configured
        return docker.from_env()

    def all_containers():
        return docker_client_or_default().containers.list(all=True)

    def is_managed(container):
        labels = ((getattr(container, "attrs", {}) or {}).get("Config", {}) or {}).get("Labels", {}) or {}
        if MANAGED_LABEL_KEY in labels:
            return labels.get(MANAGED_LABEL_KEY) == MANAGED_LABEL_VALUE
        return (getattr(container, "labels", {}) or {}).get(MANAGED_LABEL_KEY) == MANAGED_LABEL_VALUE

    def is_compose_member(container):
        labels = ((getattr(container, "attrs", {}) or {}).get("Config", {}) or {}).get("Labels", {}) or {}
        project = labels.get("com.docker.compose.project") or ""
        return project == "ollama-claw"

    def managed_containers():
        return sorted([c for c in all_containers() if is_managed(c)], key=lambda c: c.name)

    def display_containers():
        items = []
        control_name = f"control-{CONTROL_BASE_PORT}"
        excluded = {control_name, "openclaw-gateway", "ollama", "ollama-claw-agent-image-openclaw-1"}
        for c in all_containers():
            if is_managed(c):
                items.append(c)
                continue
            svc = (((getattr(c, "attrs", {}) or {}).get("Config", {}) or {}).get("Labels", {}) or {}).get("com.docker.compose.service") or ""
            if is_compose_member(c) and c.name not in excluded and svc != "agent-image-openclaw" and c.name.startswith("ollama-claw-agent-"):
                items.append(c)
        return sorted(items, key=lambda c: c.name)

    def container_host_port(container):
        bindings = ((getattr(container, "attrs", {}) or {}).get("HostConfig", {}) or {}).get("PortBindings", {}) or {}
        values = bindings.get(f"{SERVICE_PORT}/tcp") or []
        if not values:
            return None
        try:
            return int(values[0].get("HostPort"))
        except (TypeError, ValueError, AttributeError):
            return None

    FRPC_CONFIG_PATH = os.path.join(FRPC_PATH, "frpc.ini") if os.path.exists(FRPC_PATH) else None

    def add_frpc_rule(port):
        if not FRPC_CONFIG_PATH or not os.path.exists(FRPC_CONFIG_PATH):
            return
        section = f"mac{port}"
        entry = (
            f"\n[{section}]\n"
            f"type = tcp\n"
            f"local_ip = 0.0.0.0\n"
            f"local_port = {port}\n"
            f"remote_port = {port}\n"
        )
        try:
            with open(FRPC_CONFIG_PATH, "r", encoding="utf-8") as f:
                content = f.read()
            if f"[{section}]" in content:
                print(f"[frpc] port {port} already configured, skipping", flush=True, file=sys.stderr)
                return
            with open(FRPC_CONFIG_PATH, "a", encoding="utf-8") as f:
                f.write(entry)
            print(f"[frpc] added rule for port {port}, restarting frpc via docker-py...", flush=True, file=sys.stderr)
            try:
                client = docker_client_or_default()
                client.containers.get("frpc").restart()
                print(f"[frpc] frpc restarted successfully", flush=True, file=sys.stderr)
            except Exception as re:
                print(f"[frpc] WARNING: docker restart frpc failed: {re}", flush=True, file=sys.stderr)
        except Exception as e:
            print(f"[frpc] ERROR: {e}", flush=True, file=sys.stderr)

    def scp_rules_to_container(container_name, project_path):
        rules_dir = "/config/rules"
        if not os.path.exists(rules_dir):
            print(f"[scp] {rules_dir} does not exist, skipping", flush=True, file=sys.stderr)
            return
        files = [f for f in os.listdir(rules_dir) if os.path.isfile(os.path.join(rules_dir, f))]
        if not files:
            print(f"[scp] no files in {rules_dir}, skipping", flush=True, file=sys.stderr)
            return
        try:
            import paramiko, socket
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            print(f"[scp] waiting for SSH on {container_name}...", flush=True, file=sys.stderr)
            for attempt in range(1, 16):
                try:
                    ssh.connect(hostname=container_name, port=22, username="agent", password="agent", timeout=15, allow_agent=False, look_for_keys=False)
                    break
                except (socket.timeout, paramiko.ssh_exception.SSHException, OSError) as e:
                    print(f"[scp] attempt {attempt}/15 failed: {e}", flush=True, file=sys.stderr)
                    if attempt == 15:
                        raise
                    import time
                    time.sleep(3)
            sftp = ssh.open_sftp()
            for fname in files:
                src = os.path.join(rules_dir, fname)
                dst = os.path.join(project_path, fname)
                sftp.put(src, dst)
                print(f"[scp] copied {fname} -> {project_path}/", flush=True, file=sys.stderr)
            sftp.close()
            stdin, stdout, stderr = ssh.exec_command(f"chmod -R +x {project_path} 2>/dev/null || true")
            print(f"[scp] chmod -R +x {project_path}", flush=True, file=sys.stderr)
            ssh.close()
            print(f"[scp] done, {len(files)} files copied", flush=True, file=sys.stderr)
        except Exception as e:
            print(f"[scp] ERROR: {e}", flush=True, file=sys.stderr)

    def find_next_port():
        used = {p for p in [container_host_port(c) for c in managed_containers()] if p is not None}
        for port in range(START_HOST_PORT, END_HOST_PORT + 1):
            if port not in used:
                return port
        raise RuntimeError("No available host port in configured range")

    def project_path_for_agent_type(agent_type):
        return PROJECT_PATH

    def log_path_for_agent_type(agent_type):
        return LOG_PATH

    def openclaw_env(spec):
        env_vars = {
            "OPENCLAW_GATEWAY_HOST": os.environ.get("OPENCLAW_GATEWAY_HOST", "172.30.0.10"),
            "OPENCLAW_GATEWAY_PORT": os.environ.get("OPENCLAW_GATEWAY_PORT", "18790"),
        }
        config_root = app.config["CONFIG_ROOT"]
        openclaw_path = os.path.join(config_root, spec["config_subdir"], "openclaw.json")
        if os.path.exists(openclaw_path):
            try:
                with open(openclaw_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    token = data.get("gateway", {}).get("auth", {}).get("token")
                    if token:
                        env_vars["OPENCLAW_GATEWAY_TOKEN"] = str(token)
            except Exception:
                pass
        if not env_vars.get("OPENCLAW_GATEWAY_TOKEN"):
            token = os.environ.get("OPENCLAW_GATEWAY_TOKEN")
            if token:
                env_vars["OPENCLAW_GATEWAY_TOKEN"] = token
        return env_vars

    def split_openclaw_model_name(raw_model):
        model = (raw_model or "").strip()
        if not model:
            raise ValueError("model name is required")
        if "/" in model:
            provider, ollama_model = model.split("/", 1)
            if provider != "ollama":
                raise ValueError("Only ollama models are supported in this deployment")
            if not ollama_model.strip():
                raise ValueError("Ollama model name is required")
            return f"ollama/{ollama_model.strip()}", ollama_model.strip()
        return f"ollama/{model}", model

    def upsert_openclaw_ollama_model(model_name):
        primary_model, ollama_model = split_openclaw_model_name(model_name)
        openclaw_path = os.path.join(app.config["CONFIG_ROOT"], "openclaw", "openclaw.json")
        if not os.path.exists(openclaw_path):
            raise FileNotFoundError("OpenClaw config not found")
        with open(openclaw_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        data.setdefault("models", {}).setdefault("providers", {})
        provider = data["models"]["providers"].setdefault("ollama", {})
        provider["baseUrl"] = "http://ollama:11434/v1"
        provider["apiKey"] = provider.get("apiKey") or "ollama-local"
        provider["api"] = "openai-completions"

        existing = provider.get("models")
        if not isinstance(existing, list):
            existing = []
        existing_by_id = {m.get("id"): m for m in existing if isinstance(m, dict) and m.get("id")}
        model_def = existing_by_id.get(ollama_model, {})
        model_def.update({
            "id": ollama_model,
            "name": model_def.get("name") or ollama_model,
            "reasoning": bool(model_def.get("reasoning", False)),
            "input": model_def.get("input") or ["text"],
            "cost": model_def.get("cost") or {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
            "contextWindow": int(model_def.get("contextWindow") or 32768),
            "maxTokens": int(model_def.get("maxTokens") or 8192),
        })
        existing_by_id[ollama_model] = model_def
        provider["models"] = list(existing_by_id.values())

        data.setdefault("agents", {}).setdefault("defaults", {}).setdefault("model", {})
        data["agents"]["defaults"]["model"]["primary"] = primary_model
        data["agents"]["defaults"]["workspace"] = PROJECT_PATH

        gateway = data.setdefault("gateway", {})
        gateway["mode"] = "remote"
        gateway["port"] = int(os.environ.get("OPENCLAW_GATEWAY_PORT", "18790"))
        gateway.pop("bind", None)
        gateway.setdefault("auth", {}).setdefault("mode", "token")
        token = gateway.get("auth", {}).get("token") or os.environ.get("OPENCLAW_GATEWAY_TOKEN")
        if token:
            gateway["auth"]["token"] = token
        gateway.setdefault("remote", {})
        gateway["remote"]["url"] = f"ws://{os.environ.get('OPENCLAW_GATEWAY_HOST', '172.30.0.10')}:{os.environ.get('OPENCLAW_GATEWAY_PORT', '18790')}"
        if token:
            gateway["remote"]["token"] = token

        with open(openclaw_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        return {
            "config_path": openclaw_path,
            "primary_model": primary_model,
            "ollama_model": ollama_model,
        }

    def pull_ollama_model_async(ollama_model):
        started_at = now_iso()
        ollama_pull_jobs[ollama_model] = {"status": "pulling", "started_at": started_at, "error": "", "progress": 0, "total": None, "digest": ""}

        def run_pull():
            try:
                for chunk in ollama_stream_request("/api/pull", {"name": ollama_model, "stream": True}, timeout=60 * 60):
                    if "error" in chunk:
                        ollama_pull_jobs[ollama_model]["status"] = "error"
                        ollama_pull_jobs[ollama_model]["error"] = chunk["error"]
                        return
                    if "status" in chunk:
                        ollama_pull_jobs[ollama_model]["status_message"] = chunk["status"]
                    if "progress" in chunk:
                        ollama_pull_jobs[ollama_model]["progress"] = chunk["progress"]
                    if "total" in chunk:
                        ollama_pull_jobs[ollama_model]["total"] = chunk["total"]
                    if "digest" in chunk:
                        ollama_pull_jobs[ollama_model]["digest"] = chunk["digest"]
                    if "completed" in chunk:
                        ollama_pull_jobs[ollama_model]["completed"] = chunk["completed"]
                ollama_pull_jobs[ollama_model] = {
                    "status": "done",
                    "started_at": started_at,
                    "finished_at": now_iso(),
                    "error": "",
                }
            except Exception as e:
                ollama_pull_jobs[ollama_model] = {
                    "status": "error",
                    "started_at": started_at,
                    "finished_at": now_iso(),
                    "error": str(e),
                }

        threading.Thread(target=run_pull, name=f"ollama-pull-{ollama_model}", daemon=True).start()
        return {"method": "ollama_http_api", "base_urls": ollama_base_urls(), "model": ollama_model, "started_at": started_at}

    def restart_openclaw_gateway():
        gateway = docker_client_or_default().containers.get(os.environ.get(GATEWAY_CONTAINER_ENV, "openclaw-gateway"))
        gateway.restart()
        return gateway.name

    def recreate_managed_agents_after_model_change():
        recreated = []
        errors = {}
        gateway_token = ""
        for c in managed_containers():
            try:
                payload = recreate_agent(c.name)
                add_frpc_rule(payload["host_port"])
                scp_rules_to_container(payload["container_name"], PROJECT_PATH)
                recreated.append(payload)
                if not gateway_token:
                    gateway_token = openclaw_env(AGENT_SPECS[payload["agent_type"]]).get("OPENCLAW_GATEWAY_TOKEN", "")
            except Exception as e:
                errors[c.name] = str(e)
        if gateway_token:
            auto_pair_openclaw_client(gateway_token, timeout_seconds=20)
        return recreated, errors

    def auto_pair_openclaw_client(token, timeout_seconds=20):
        if not token:
            return False
        try:
            gateway = docker_client_or_default().containers.get(os.environ.get(GATEWAY_CONTAINER_ENV, "openclaw-gateway"))
        except Exception as e:
            print(f"[pairing] gateway container not found: {e}", flush=True, file=sys.stderr)
            return False
        script = r"""
const fs = require("fs");
const path = require("path");
const token = process.env.OPENCLAW_PAIR_TOKEN || "";
if (!token) process.exit(2);
const dir = path.join(process.env.HOME || "/home/agent", ".openclaw", "devices");
const pendingPath = path.join(dir, "pending.json");
const pairedPath = path.join(dir, "paired.json");
const readJson = (p) => {
  try { return JSON.parse(fs.readFileSync(p, "utf8")); } catch { return {}; }
};
const writeJson = (p, value) => {
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(value, null, 2));
  try { fs.chmodSync(p, 0o600); } catch {}
};
const pending = readJson(pendingPath);
const paired = readJson(pairedPath);
const now = Date.now();
let count = 0;
for (const [requestId, req] of Object.entries(pending)) {
  if (!req || !["gateway-client", "cli"].includes(req.clientId)) continue;
  const role = req.role || "operator";
  const scopes = Array.isArray(req.scopes) && req.scopes.length ? [...req.scopes].sort() : ["operator.admin"];
  const existing = paired[req.deviceId] || {};
  const tokens = existing.tokens ? { ...existing.tokens } : {};
  tokens[role] = {
    token,
    role,
    scopes,
    createdAtMs: tokens[role]?.createdAtMs || now,
    lastUsedAtMs: tokens[role]?.lastUsedAtMs
  };
  paired[req.deviceId] = {
    deviceId: req.deviceId,
    publicKey: req.publicKey,
    displayName: req.displayName,
    platform: req.platform,
    clientId: req.clientId,
    clientMode: req.clientMode,
    role,
    roles: Array.isArray(req.roles) && req.roles.length ? req.roles : [role],
    scopes,
    remoteIp: req.remoteIp,
    tokens,
    createdAtMs: existing.createdAtMs || now,
    approvedAtMs: now
  };
  delete pending[requestId];
  count++;
}
writeJson(pendingPath, pending);
writeJson(pairedPath, paired);
console.log(count);
"""
        import base64
        script_b64 = base64.b64encode(script.encode("utf-8")).decode("ascii")
        escaped_token = token.replace("'", "'\"'\"'")
        cmd = f"OPENCLAW_PAIR_TOKEN='{escaped_token}' node -e \"$(echo {script_b64} | base64 -d)\""
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                result = gateway.exec_run(["/bin/sh", "-lc", cmd], user=AGENT_RUNTIME_USER)
                output = result.output.decode("utf-8", errors="replace").strip() if isinstance(result.output, bytes) else str(result.output).strip()
                approved_count = 0
                if result.exit_code == 0 and output.splitlines():
                    try:
                        approved_count = int(output.splitlines()[-1])
                    except ValueError:
                        approved_count = 0
                if approved_count > 0:
                    print(f"[pairing] auto-approved {approved_count} openclaw client(s)", flush=True, file=sys.stderr)
                    return True
            except Exception as e:
                print(f"[pairing] auto-approve attempt failed: {e}", flush=True, file=sys.stderr)
            time.sleep(1)
        print("[pairing] no pending openclaw client found before timeout", flush=True, file=sys.stderr)
        return False

    def container_env(container):
        env = {}
        values = ((getattr(container, "attrs", {}) or {}).get("Config", {}) or {}).get("Env", []) or []
        for item in values:
            if "=" in item:
                k, v = item.split("=", 1)
                env[k] = v
        return env

    def send_openclaw_message(container, message):
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
node -e 'const fs=require("fs"); const p=process.env.HOME+"/.{agent_dir}/"+"{config_file}"; if(fs.existsSync(p)){{const j=JSON.parse(fs.readFileSync(p,"utf8")); j.gateway=j.gateway={{}}; j.gateway.mode="remote"; j.gateway.remote=j.gateway.remote={{}}; j.gateway.remote.url="ws://"+(process.env.OPENCLAW_GATEWAY_HOST||"172.30.0.10")+":"+(process.env.OPENCLAW_GATEWAY_PORT||"18790"); if(process.env.OPENCLAW_GATEWAY_TOKEN) j.gateway.remote.token=process.env.OPENCLAW_GATEWAY_TOKEN; delete j.gateway.bind; fs.writeFileSync(p,JSON.stringify(j,null,2)); fs.chmodSync(p,0o600);}}'
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
sed -e 's/\x1b\[[0-?]*[ -\/]*[@-~]//g' "$out_file" | tail -120 >> "{log_path}"
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

    def append_user_log(container, message):
        ts = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
        safe = (message or INITIAL_MESSAGE).replace("'", "'\"'\"'")
        container.exec_run(["/bin/sh", "-c", f"mkdir -p '{LOGS_PATH}' && echo '[{ts}] $ {safe}' >> '{LOG_PATH}'"], user=AGENT_RUNTIME_USER)

    def clean_log_text(text):
        cleaned = ANSI_ESCAPE_PATTERN.sub("", text or "")
        cleaned = cleaned.replace("\r", "\n")
        lines = []
        for line in cleaned.splitlines():
            line = line.strip()
            if line:
                lines.append(line)
        return "\n".join(lines)

    def ensure_host_agent_dirs(container_name):
        host_workspaces_root = app.config["HOST_WORKSPACES_ROOT"]
        host_logs_root = app.config.get("HOST_LOGS_ROOT") or os.path.join(os.path.dirname(host_workspaces_root), "logs")
        workspace_dir = f"{host_workspaces_root}/{container_name}"
        sessions_dir = f"{workspace_dir}/sessions"
        logs_dir = f"{host_logs_root}/{container_name}"
        os.makedirs(workspace_dir, exist_ok=True)
        os.makedirs(sessions_dir, exist_ok=True)
        os.makedirs(logs_dir, exist_ok=True)
        for path in (workspace_dir, sessions_dir, logs_dir):
            try:
                os.chown(path, 501, 20)
            except Exception:
                pass
        return workspace_dir, sessions_dir, logs_dir

    def derive_agent_basename(container_name):
        m = re.match(r"^\d+-(.+)$", container_name or "")
        if m:
            return m.group(1)
        return _safe_name_part(container_name)

    def _safe_name_part(raw):
        base = (raw or "").strip().lower()
        if not base:
            base = "agent"
        base = NAME_SANITIZE_PATTERN.sub("-", base)
        base = base.strip("-")
        return base or "agent"

    def _tail_logs(container, tail):
        labels = ((getattr(container, "attrs", {}) or {}).get("Config", {}) or {}).get("Labels", {}) or (getattr(container, "labels", {}) or {})
        agent_type = labels.get("hermit.agent_type", "")
        log_path = log_path_for_agent_type(agent_type)
        try:
            result = container.exec_run(["/bin/sh", "-lc", f"tail -{tail} '{log_path}' 2>/dev/null"], user=AGENT_RUNTIME_USER)
            if isinstance(result.output, bytes):
                return clean_log_text(result.output.decode("utf-8", errors="replace"))
            return clean_log_text(str(result.output))
        except Exception:
            return ""

    def _full_logs(container):
        labels = ((getattr(container, "attrs", {}) or {}).get("Config", {}) or {}).get("Labels", {}) or (getattr(container, "labels", {}) or {})
        agent_type = labels.get("hermit.agent_type", "")
        log_path = log_path_for_agent_type(agent_type)
        try:
            result = container.exec_run(["/bin/sh", "-lc", f"cat '{log_path}' 2>/dev/null"], user=AGENT_RUNTIME_USER)
            if isinstance(result.output, bytes):
                return clean_log_text(result.output.decode("utf-8", errors="replace"))
            return clean_log_text(str(result.output))
        except Exception:
            return ""

    def _copy_workspace_tree(src_dir, dst_dir):
        import subprocess, shutil
        if not os.path.isdir(src_dir):
            raise FileNotFoundError(f"Source workspace not found: {src_dir}")
        if os.path.exists(dst_dir):
            raise FileExistsError(f"目标工作空间已存在: {dst_dir}，请先删除再试")
        result = subprocess.run(["cp", "-a", src_dir, dst_dir], capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"copy failed: {result.stderr}")
        sessions_dir = os.path.join(dst_dir, "sessions")
        os.makedirs(sessions_dir, exist_ok=True)
        try:
            os.chown(dst_dir, 501, 20)
            os.chown(sessions_dir, 501, 20)
        except Exception:
            pass

    def create_agent(agent_type, custom_name, body=None):
        if agent_type not in AGENT_SPECS:
            raise ValueError("Unsupported agent type")
        spec = AGENT_SPECS[agent_type]
        host_port = find_next_port()
        normalized_name = _safe_name_part(custom_name)
        container_name = f"{host_port}-{normalized_name}"
        body = body or {}
        labels = {
            MANAGED_LABEL_KEY: MANAGED_LABEL_VALUE,
            "hermit.agent_type": agent_type,
            "hermit.host_port": str(host_port),
            "hermit.service_port": str(SERVICE_PORT),
        }
        host_config_root = app.config["HOST_CONFIG_ROOT"]
        host_workspaces_root = app.config["HOST_WORKSPACES_ROOT"]
        host_logs_root = app.config.get("HOST_LOGS_ROOT") or os.path.join(os.path.dirname(host_workspaces_root), "logs")
        ensure_host_agent_dirs(container_name)
        log_bind = LOGS_PATH
        volumes = {
            f"{host_config_root}/{spec['config_subdir']}": {"bind": "/agent-config", "mode": "ro"},
            f"{host_workspaces_root}/{container_name}": {"bind": PROJECT_PATH, "mode": "rw"},
            f"{host_workspaces_root}/{container_name}/sessions": {"bind": SESSIONS_PATH, "mode": "rw"},
            f"{host_logs_root}/{container_name}": {"bind": log_bind, "mode": "rw"},
            f"{host_config_root}/rules": {"bind": RULES_PATH, "mode": "ro"},
        }
        log_config = LogConfig(type=LogConfig.types.JSON, config={"max-size": "500m", "max-file": "2"})

        env_vars = openclaw_env(spec)
        gateway_token = env_vars.get("OPENCLAW_GATEWAY_TOKEN", "")

        container = docker_client_or_default().containers.run(
            spec["image"],
            name=container_name,
            detach=True,
            tty=True,
            stdin_open=True,
            user=AGENT_RUNTIME_USER,
            environment=env_vars,
            labels=labels,
            ports={f"{SERVICE_PORT}/tcp": host_port},
            volumes=volumes,
            restart_policy={"Name": "unless-stopped"},
            log_config=log_config,
            network="ollama-claw_ollama-claw-network",
            extra_hosts=["host.docker.internal:host-gateway"],
            mem_limit="16g",
            memswap_limit="16g",
            shm_size="8g",
        )

        if not body.get("skip_initial_message"):
            # 创建容器后发送初始消息
            time.sleep(3)
            auto_pair_openclaw_client(gateway_token)
            user_msg = (body.get("message") or "").strip()
            msg_to_send = user_msg or INITIAL_MESSAGE
            try:
                append_user_log(container, msg_to_send)
                send_openclaw_message(container, msg_to_send)
            except Exception as e:
                print(f"[send-message] initial send failed: {e}", flush=True, file=sys.stderr)

        else:
            time.sleep(3)
            auto_pair_openclaw_client(gateway_token)

        return {
            "container_name": container.name,
            "agent_type": agent_type,
            "host_port": host_port,
            "service_port": SERVICE_PORT,
            "created_at": now_iso(),
        }

    def recreate_agent(container_name):
        container = docker_client_or_default().containers.get(container_name)
        labels = ((getattr(container, "attrs", {}) or {}).get("Config", {}) or {}).get("Labels", {}) or (getattr(container, "labels", {}) or {})
        agent_type = labels.get("hermit.agent_type") or ""
        if agent_type not in AGENT_SPECS:
            raise ValueError("Unsupported agent type")
        host_port = container_host_port(container)
        if host_port is None:
            raise RuntimeError("Missing port binding")
        spec = AGENT_SPECS[agent_type]
        host_config_root = app.config["HOST_CONFIG_ROOT"]
        host_workspaces_root = app.config["HOST_WORKSPACES_ROOT"]
        host_logs_root = app.config.get("HOST_LOGS_ROOT") or os.path.join(os.path.dirname(host_workspaces_root), "logs")
        ensure_host_agent_dirs(container_name)
        log_bind = LOGS_PATH
        volumes = {
            f"{host_config_root}/{spec['config_subdir']}": {"bind": "/agent-config", "mode": "ro"},
            f"{host_workspaces_root}/{container_name}": {"bind": PROJECT_PATH, "mode": "rw"},
            f"{host_workspaces_root}/{container_name}/sessions": {"bind": SESSIONS_PATH, "mode": "rw"},
            f"{host_logs_root}/{container_name}": {"bind": log_bind, "mode": "rw"},
            f"{host_config_root}/rules": {"bind": RULES_PATH, "mode": "ro"},
        }
        log_config = LogConfig(type=LogConfig.types.JSON, config={"max-size": "500m", "max-file": "2"})
        container.remove(force=True)

        try:
            docker_client_or_default().images.pull(spec["image"])
        except Exception:
            pass

        env_vars = openclaw_env(spec)
        gateway_token = env_vars.get("OPENCLAW_GATEWAY_TOKEN", "")

        new_container = docker_client_or_default().containers.run(
            spec["image"],
            name=container_name,
            detach=True,
            tty=True,
            stdin_open=True,
            user=AGENT_RUNTIME_USER,
            environment=env_vars,
            labels={
                MANAGED_LABEL_KEY: MANAGED_LABEL_VALUE,
                "hermit.agent_type": agent_type,
                "hermit.host_port": str(host_port),
                "hermit.service_port": str(SERVICE_PORT),
            },
            ports={f"{SERVICE_PORT}/tcp": host_port},
            volumes=volumes,
            restart_policy={"Name": "unless-stopped"},
            log_config=log_config,
            network="ollama-claw_ollama-claw-network",
            extra_hosts=["host.docker.internal:host-gateway"],
        )
        time.sleep(3)
        auto_pair_openclaw_client(gateway_token)
        return {"container_name": new_container.name, "agent_type": agent_type, "host_port": host_port, "ssh_port": host_port - 10000, "service_port": SERVICE_PORT, "recreated_at": now_iso()}

    def fork_agent(container_name):
        import shutil, traceback
        debug_log = "/logs/hermit/debug.log"
        with open(debug_log, "a", encoding="utf-8") as f:
            f.write(f"\n=== FORK START: {container_name} ===\n")
        
        container = docker_client_or_default().containers.get(container_name)
        labels = ((getattr(container, "attrs", {}) or {}).get("Config", {}) or {}).get("Labels", {}) or (getattr(container, "labels", {}) or {})
        agent_type = labels.get("hermit.agent_type") or ""
        
        with open(debug_log, "a", encoding="utf-8") as f:
            f.write(f"agent_type: {agent_type}\n")
        
        if agent_type not in AGENT_SPECS:
            raise ValueError(f"Unsupported agent type: {agent_type}")

        new_host_port = find_next_port()
        base_name = derive_agent_basename(container_name)
        new_container_name = f"{new_host_port}-{base_name}"

        src_workspace = f"/workspaces/{container_name}"
        dst_workspace = f"/workspaces/{new_container_name}"
        dst_logs = f"/logs/{new_container_name}"

        with open(debug_log, "a", encoding="utf-8") as f:
            f.write(f"src_workspace: {src_workspace}\n")
            f.write(f"dst_workspace: {dst_workspace}\n")

        try:
            with open(debug_log, "a", encoding="utf-8") as f:
                f.write("Step 1: _copy_workspace_tree\n")
            _copy_workspace_tree(src_workspace, dst_workspace)
            
            with open(debug_log, "a", encoding="utf-8") as f:
                f.write("Step 2: makedirs dst_logs\n")
            os.makedirs(dst_logs, exist_ok=True)
            try:
                os.chown(dst_logs, 501, 20)
            except Exception:
                pass

            with open(debug_log, "a", encoding="utf-8") as f:
                f.write("Step 3: create_agent\n")
            body = {"message": ""}  # 不跳过初始消息
            payload = create_agent(agent_type, base_name, body=body)
            
            with open(debug_log, "a", encoding="utf-8") as f:
                f.write(f"created payload: {payload}\n")
            
            created_name = payload["container_name"]
            if created_name != new_container_name:
                created_container = docker_client_or_default().containers.get(created_name)
                created_container.remove(force=True)
                raise RuntimeError(f"Fork expected {new_container_name}, got {created_name}")

            with open(debug_log, "a", encoding="utf-8") as f:
                f.write("Step 4: add_frpc_rule\n")
            add_frpc_rule(payload["host_port"])
            
            with open(debug_log, "a", encoding="utf-8") as f:
                f.write("Step 5: sleep 5\n")
            project_path = project_path_for_agent_type(agent_type)
            import time
            time.sleep(5)
            
            with open(debug_log, "a", encoding="utf-8") as f:
                f.write("Step 6: scp_rules_to_container\n")
            scp_rules_to_container(payload["container_name"], project_path)
            
            with open(debug_log, "a", encoding="utf-8") as f:
                f.write(f"FORK SUCCESS: {payload}\n")
            return payload
        except FileExistsError as e:
            with open(debug_log, "a", encoding="utf-8") as f:
                f.write(f"FORK ERROR: {str(e)}\n")
            raise ValueError(str(e))
        except Exception as e:
            with open(debug_log, "a", encoding="utf-8") as f:
                f.write(f"FORK ERROR: {str(e)}\n")
                f.write(traceback.format_exc())
            shutil.rmtree(dst_workspace, ignore_errors=True)
            shutil.rmtree(dst_logs, ignore_errors=True)
            raise

    def format_item(container, tail):
        port = container_host_port(container)
        labels = ((getattr(container, "attrs", {}) or {}).get("Config", {}) or {}).get("Labels", {}) or (getattr(container, "labels", {}) or {})
        agent_type = labels.get("hermit.agent_type", "")
        if not agent_type:
            svc = labels.get("com.docker.compose.service") or ""
            if svc:
                agent_type = f"compose/{svc}"
            else:
                agent_type = "unknown"
        item = {
            "container_name": container.name,
            "agent_type": agent_type,
            "status": getattr(container, "status", "unknown"),
            "host_port": port,
            "ssh_port": port - 10000 if port else None,
            "service_port": SERVICE_PORT,
            "managed": is_managed(container),
            "logs": _tail_logs(container, tail=200),
        }
        return item

    @app.get("/api/agents/<path:name>/ssh-info")
    def api_agent_ssh_info(name):
        try:
            container = docker_client_or_default().containers.get(name)
            return jsonify({
                "host": "localhost",
                "port": 22,
                "user": "agent",
                "password": "agent",
                "container": container.name,
            })
        except docker.errors.NotFound:
            return jsonify({"error": "Container not found"}), 404

    @app.get("/api/agents/<path:name>/ssh-terminal")
    def api_agent_ssh_terminal(name):
        try:
            container = docker_client_or_default().containers.get(name)
            container_name = container.name
            html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Terminal - {name}</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/xterm@5.3.0/css/xterm.css"/>
  <script src="https://cdn.jsdelivr.net/npm/xterm@5.3.0/lib/xterm.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/xterm-addon-fit@0.8.0/lib/xterm-addon-fit.js"></script>
  <style>
    body {{ margin: 0; padding: 4px; background: #1e1e1e; overflow: hidden; }}
    #terminal {{ width: 100%; height: 100vh; }}
  </style>
</head>
<body>
  <div id="terminal"></div>
  <script>
    const term = new Terminal({{ cursorBlink: true, fontSize: 14, fontFamily: 'Menlo, Monaco, "Courier New", monospace' }});
    const fitAddon = new FitAddon.FitAddon();
    term.loadAddon(fitAddon);
    term.open(document.getElementById('terminal'));
    fitAddon.fit();

    const wsProtocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = wsProtocol + '//' + location.host + '/ws/ssh?container={container_name}';
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {{
      term.write('\\x1b[32mConnected to {container_name} via SSH\\x1b[0m\\r\\n');
      term.onData(data => ws.send(data));
    }};

    ws.onmessage = (event) => {{
      term.write(event.data);
    }};

    ws.onclose = () => {{
      term.write('\\r\\n\\x1b[31m[Connection Closed]\\x1b[0m\\r\\n');
    }};

    ws.onerror = (err) => {{
      term.write('\\r\\n\\x1b[31m[WebSocket Error]\\x1b[0m\\r\\n');
    }};

    window.addEventListener('resize', () => fitAddon.fit());
  </script>
</body>
</html>"""
            return html, 200, {"Content-Type": "text/html"}
        except docker.errors.NotFound:
            return "Container not found", 404

    @sock.route("/ws/ssh")
    def ws_ssh(ws):
        import threading
        container_name = request.args.get("container")
        if not container_name:
            ws.close()
            return

        try:
            client = docker_client_or_default()
            try:
                container = client.containers.get(container_name)
            except Exception:
                ws.close()
                return
            labels = ((container.attrs or {}).get("Config", {}) or {}).get("Labels", {}) or {}
            agent_type = labels.get("hermit.agent_type", "")
            project_path = PROJECT_PATH

            import paramiko
        except ImportError:
            ws.send("paramiko not installed\r\n")
            ws.close()
            return

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            ssh.connect(
                hostname=container_name,
                port=22,
                username="agent",
                password="agent",
                timeout=10,
                allow_agent=False,
                look_for_keys=False,
            )
            transport = ssh.get_transport()
            if not transport:
                ws.close()
                return
            transport.set_keepalive(10)

            chan = ssh.invoke_shell(term="xterm-256color", width=80, height=24)
            chan.settimeout(0.1)

            chan.send(f"cd {project_path}\r")
            chan.send("clear\r")

            def pump():
                try:
                    while True:
                        if chan.exit_status_ready():
                            break
                        try:
                            data = chan.recv(65536)
                            if data:
                                ws.send(data.decode('utf-8', errors='replace'))
                            else:
                                break
                        except Exception:
                            pass
                except Exception:
                    pass
                finally:
                    try:
                        chan.close()
                    except Exception:
                        pass
                    ws.close()
                    ssh.close()

            t = threading.Thread(target=pump, daemon=True)
            t.start()

            while True:
                try:
                    msg = ws.receive(timeout=0.05)
                    if msg:
                        chan.send(msg)
                except Exception:
                    break

        except Exception as e:
            try:
                ws.send(f"\r\n[SSH Error: {e}]\r\n")
            except Exception:
                pass
            ws.close()
        finally:
            try:
                ssh.close()
            except Exception:
                pass

    @app.get("/api/agent-types")
    def api_agent_types():
        return jsonify({"items": [{"value": k, "label": k} for k in AGENT_SPECS]})

    @app.get("/api/health")
    def api_health():
        token_configured = False
        try:
            token_configured = bool(openclaw_env(AGENT_SPECS["openclaw@2026.2.9"]).get("OPENCLAW_GATEWAY_TOKEN"))
        except Exception:
            token_configured = False
        return jsonify({
            "status": "ok",
            "time": now_iso(),
            "agent_types": list(AGENT_SPECS.keys()),
            "gateway": {
                "host": os.environ.get("OPENCLAW_GATEWAY_HOST", "172.30.0.10"),
                "port": os.environ.get("OPENCLAW_GATEWAY_PORT", "18790"),
                "token_configured": token_configured,
            },
        })

    @app.get("/api/agents")
    def api_agents():
        try:
            tail = int(request.args.get("tail", DEFAULT_TAIL_LINES))
        except ValueError:
            tail = DEFAULT_TAIL_LINES
        tail = max(1, min(200, tail))
        items = [format_item(c, tail) for c in display_containers()]
        return jsonify({"generated_at": now_iso(), "items": items})

    @app.post("/api/agents")
    def api_create_agent():
        body = request.get_json(silent=True) or {}
        agent_type = (body.get("type") or "").strip()
        name = body.get("name") or ""
        try:
            payload = create_agent(agent_type, name, body)
            add_frpc_rule(payload["host_port"])
            scp_rules_to_container(payload["container_name"], PROJECT_PATH)
            return jsonify(payload), 201
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except docker.errors.ImageNotFound:
            return jsonify({"error": "Agent image missing. Please run: docker compose build"}), 400
        except docker.errors.APIError as e:
            return jsonify({"error": f"Docker API error: {str(e)}"}), 500
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 409

    def _require_managed(name):
        container = docker_client_or_default().containers.get(name)
        if not is_managed(container) and not is_compose_member(container):
            raise PermissionError("Container is not managed by this control plane")
        return container

    @app.get("/api/agents/<path:name>/logs")
    def api_logs(name):
        try:
            tail = int(request.args.get("tail", DEFAULT_TAIL_LINES))
        except ValueError:
            tail = DEFAULT_TAIL_LINES
        tail = max(1, min(1000, tail))
        try:
            container = _require_managed(name)
            return jsonify({"container_name": name, "logs": _tail_logs(container, tail)})
        except PermissionError as e:
            return jsonify({"error": str(e)}), 403
        except docker.errors.NotFound:
            return jsonify({"error": "Container not found"}), 404

    @app.get("/api/agents/<path:name>/logs/download")
    def api_logs_download(name):
        try:
            container = _require_managed(name)
            data = _full_logs(container).encode("utf-8")
            return send_file(
                BytesIO(data),
                mimetype="text/plain; charset=utf-8",
                as_attachment=True,
                download_name=f"{name}.log",
            )
        except PermissionError as e:
            return jsonify({"error": str(e)}), 403
        except docker.errors.NotFound:
            return jsonify({"error": "Container not found"}), 404

    @app.post("/api/agents/<path:name>/command")
    def api_command(name):
        body = request.get_json(silent=True) or {}
        command = (body.get("command") or "").strip()
        if not command:
            return jsonify({"error": "command is required"}), 400
        try:
            container = _require_managed(name)
            result = container.exec_run(["/bin/sh", "-lc", command], user=AGENT_RUNTIME_USER)
            output = result.output.decode("utf-8", errors="replace") if isinstance(result.output, bytes) else str(result.output)
            return jsonify({"exit_code": result.exit_code, "output": output})
        except PermissionError as e:
            return jsonify({"error": str(e)}), 403
        except docker.errors.NotFound:
            return jsonify({"error": "Container not found"}), 404
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.post("/api/agents/<path:name>/send-message")
    def api_send_message(name):
        body = request.get_json(silent=True) or {}
        message = (body.get("message") or "").strip()
        try:
            container = _require_managed(name)
            labels = ((getattr(container, "attrs", {}) or {}).get("Config", {}) or {}).get("Labels", {}) or (getattr(container, "labels", {}) or {})
            agent_type = labels.get("hermit.agent_type", "")
            msg_to_send = message or INITIAL_MESSAGE
            try:
                append_user_log(container, msg_to_send)
                send_openclaw_message(container, msg_to_send)
            except Exception as e:
                return jsonify({"error": str(e)}), 500
            return jsonify({"ok": True, "container_name": name, "message": message, "agent_type": agent_type, "sent_at": now_iso()})
        except PermissionError as e:
            return jsonify({"error": str(e)}), 403
        except docker.errors.NotFound:
            return jsonify({"error": "Container not found"}), 404
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.post("/api/agents/<path:name>/restart")
    def api_restart_agent(name):
        try:
            container = _require_managed(name)
            container.restart()
            return jsonify({"ok": True, "container_name": name, "restarted_at": now_iso()})
        except PermissionError as e:
            return jsonify({"error": str(e)}), 403
        except docker.errors.NotFound:
            return jsonify({"error": "Container not found"}), 404
        except docker.errors.APIError as e:
            return jsonify({"error": f"Docker API error: {str(e)}"}), 500

    @app.delete("/api/agents/<path:name>")
    def api_delete_agent(name):
        try:
            container = _require_managed(name)
            if not is_managed(container):
                return jsonify({"error": "Only managed agents can be deleted"}), 400
            container.remove(force=True)
            return jsonify({"ok": True, "container_name": name, "deleted_at": now_iso()})
        except PermissionError as e:
            return jsonify({"error": str(e)}), 403
        except docker.errors.NotFound:
            return jsonify({"error": "Container not found"}), 404
        except docker.errors.APIError as e:
            return jsonify({"error": f"Docker API error: {str(e)}"}), 500

    @app.post("/api/agents/<path:name>/cleanup-context")
    def api_cleanup_context(name):
        try:
            container = _require_managed(name)
            labels = ((container.attrs or {}).get("Config", {}) or {}).get("Labels", {}) or {}
            agent_type = labels.get("hermit.agent_type", "")
            cmd = "rm -f ~/.openclaw/projects/*/*.jsonl 2>/dev/null; echo done"
            result = container.exec_run(["/bin/sh", "-lc", cmd], user=AGENT_RUNTIME_USER)
            output = result.output.decode("utf-8", errors="replace").strip()
            return jsonify({"ok": True, "container_name": name, "output": output})
        except PermissionError as e:
            return jsonify({"error": str(e)}), 403
        except docker.errors.NotFound:
            return jsonify({"error": "Container not found"}), 404
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.get("/api/agents/<path:name>/git-commits")
    def api_git_commits(name):
        try:
            container = _require_managed(name)
            labels = ((container.attrs or {}).get("Config", {}) or {}).get("Labels", {}) or {}
            agent_type = labels.get("hermit.agent_type", "")
            project_path = project_path_for_agent_type(agent_type)
            cmd = f'cd {project_path} && git -c safe.directory=* rev-parse --short HEAD && git -c safe.directory=* log --format="%h %ad %s" --date=short -20'
            result = container.exec_run(["/bin/sh", "-lc", cmd], user=AGENT_RUNTIME_USER)
            output = result.output.decode("utf-8", errors="replace").strip()
            
            debug_log = "/logs/hermit/debug.log"
            with open(debug_log, "a", encoding="utf-8") as f:
                f.write(f"\n=== GIT COMMITS DEBUG ===\n")
                f.write(f"container: {name}\n")
                f.write(f"cmd: {cmd}\n")
                f.write(f"exit_code: {result.exit_code}\n")
                f.write(f"output:\n{output}\n")

            if result.exit_code != 0:
                return jsonify({"error": "项目不是 git 仓库"})
            
            lines = output.split("\n")
            current_commit = lines[0].strip()
            log_lines = lines[1:]
            
            commits = [{
                "hash": "__FORK__",
                "message": "****FORK****",
                "is_current": "",
            }]
            for line in log_lines:
                if line.strip() and len(line) >= 10:
                    parts = line.split(" ", 2)
                    if len(parts) >= 2:
                        commit_hash = parts[0]
                        date_str = parts[1]
                        message = parts[2] if len(parts) > 2 else ""
                        is_current = "✓" if commit_hash == current_commit else ""
                        commits.append({
                            "hash": commit_hash, 
                            "message": f"[{date_str}] {message}", 
                            "is_current": is_current
                        })
            return jsonify({"commits": commits})
        except PermissionError as e:
            return jsonify({"error": str(e)}), 403
        except docker.errors.NotFound:
            return jsonify({"error": "Container not found"}), 404
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.post("/api/agents/<path:name>/git-reset")
    def api_git_reset(name):
        try:
            container = _require_managed(name)
            data = request.get_json() or {}
            commit_hash = data.get("commit_hash", "")
            hard_reset = bool(data.get("hard"))
            if not commit_hash:
                return jsonify({"error": "commit_hash is required"}), 400
            labels = ((container.attrs or {}).get("Config", {}) or {}).get("Labels", {}) or {}
            agent_type = labels.get("hermit.agent_type", "")
            project_path = project_path_for_agent_type(agent_type)

            if commit_hash == "__FORK__":
                try:
                    payload = fork_agent(name)
                except ValueError as e:
                    return jsonify({"error": str(e)}), 400
                return jsonify({
                    "ok": True,
                    "mode": "fork",
                    "container_name": name,
                    "new_container": payload["container_name"],
                    "host_port": payload["host_port"],
                })

            if not COMMIT_HASH_PATTERN.fullmatch(commit_hash):
                return jsonify({"error": "invalid commit hash"}), 400

            git_action = "reset --hard" if hard_reset else "checkout"
            cmd = f"cd {project_path} && git -c safe.directory=* {git_action} {commit_hash} 2>&1 && sleep 5"
            result = container.exec_run(["/bin/sh", "-lc", cmd], user=AGENT_RUNTIME_USER)
            output = result.output.decode("utf-8", errors="replace").strip()
            if result.exit_code != 0:
                return jsonify({"error": output or f"git {git_action} failed"}), 400
            payload = recreate_agent(name)
            add_frpc_rule(payload["host_port"])
            scp_rules_to_container(payload["container_name"], project_path)
            return jsonify({
                "ok": True,
                "mode": "hard_reset" if hard_reset else "checkout",
                "container_name": name,
                "commit_hash": commit_hash,
                "git_output": output,
                "new_container": payload["container_name"],
            })
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except PermissionError as e:
            return jsonify({"error": str(e)}), 403
        except docker.errors.NotFound:
            return jsonify({"error": "Container not found"}), 404
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.post("/api/agents/<path:name>/recreate")
    def api_recreate_agent(name):
        try:
            container = docker_client_or_default().containers.get(name)
            if not is_managed(container):
                return jsonify({"error": "Only managed agents can be recreated"}), 400
            labels = ((container.attrs or {}).get("Config", {}) or {}).get("Labels", {}) or {}
            agent_type = labels.get("hermit.agent_type", "")
            payload = recreate_agent(name)
            add_frpc_rule(payload["host_port"])
            import time
            time.sleep(8)
            scp_rules_to_container(payload["container_name"], PROJECT_PATH)
            default_msg = INITIAL_MESSAGE
            try:
                container_new = docker_client_or_default().containers.get(payload["container_name"])
                append_user_log(container_new, default_msg)
                send_openclaw_message(container_new, default_msg)
            except Exception as e:
                print(f"[recreate] send initial message failed: {e}", flush=True, file=sys.stderr)
            return jsonify(payload)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except docker.errors.NotFound:
            return jsonify({"error": "Container not found"}), 404
        except docker.errors.APIError as e:
            return jsonify({"error": f"Docker API error: {str(e)}"}), 500
        except RuntimeError as e:
            return jsonify({"error": str(e)}), 409

    @app.post("/api/agents/restart")
    def api_restart_all_agents():
        restarted = []
        errors = {}
        for c in managed_containers():
            try:
                c.restart()
                restarted.append(c.name)
            except Exception as e:
                errors[c.name] = str(e)
        return jsonify({"ok": True, "restarted": restarted, "errors": errors, "restarted_at": now_iso()})

    @app.post("/api/agents/recreate")
    def api_recreate_all_agents():
        recreated = []
        errors = {}
        for c in managed_containers():
            try:
                labels = ((c.attrs or {}).get("Config", {}) or {}).get("Labels", {}) or {}
                agent_type = labels.get("hermit.agent_type", "")
                payload = recreate_agent(c.name)
                add_frpc_rule(payload["host_port"])
                scp_rules_to_container(payload["container_name"], PROJECT_PATH)
                recreated.append(payload)
            except Exception as e:
                errors[c.name] = str(e)
        return jsonify({"ok": True, "recreated": recreated, "errors": errors, "recreated_at": now_iso()})

    @app.get("/api/ollama/models")
    def api_ollama_models():
        """获取 Ollama 中已安装的模型列表"""
        try:
            models = list_ollama_models()
            return jsonify({
                "models": [
                    {
                        "name": m.get("name", ""),
                        "size": m.get("size", 0),
                        "modified_at": m.get("modified_at", ""),
                    }
                    for m in models
                ]
            })
        except Exception as e:
            return jsonify({"error": str(e), "models": []}), 500

    @app.get("/api/openclaw/model")
    def api_openclaw_model():
        """获取当前 OpenClaw 配置的默认模型"""
        try:
            config_root = app.config["CONFIG_ROOT"]
            openclaw_path = os.path.join(config_root, "openclaw", "openclaw.json")
            if not os.path.exists(openclaw_path):
                return jsonify({"error": "OpenClaw config not found"}), 404
            with open(openclaw_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            primary_model = data.get("agents", {}).get("defaults", {}).get("model", {}).get("primary", "")
            return jsonify({
                "model": primary_model,
                "config_path": openclaw_path,
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.post("/api/openclaw/model")
    def api_update_openclaw_model():
        """更新 OpenClaw 默认模型配置，触发 Ollama 拉取，并重建运行中的 agent 容器"""
        body = request.get_json(silent=True) or {}
        model_name = (body.get("model") or "").strip()
        try:
            model_info = upsert_openclaw_ollama_model(model_name)
            pull_info = pull_ollama_model_async(model_info["ollama_model"])
            restarted_gateway = restart_openclaw_gateway()
            # Give the gateway a moment to reload config before agents reconnect.
            time.sleep(3)
            recreated_agents, errors = recreate_managed_agents_after_model_change()

            return jsonify({
                "ok": True,
                "model": model_info["primary_model"],
                "ollama_model": model_info["ollama_model"],
                "config_path": model_info["config_path"],
                "ollama_pull": pull_info,
                "restarted_gateway": restarted_gateway,
                "recreated_agents": recreated_agents,
                "recreation_errors": errors,
                "updated_at": now_iso(),
            })
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except FileNotFoundError as e:
            return jsonify({"error": str(e)}), 404
        except docker.errors.NotFound as e:
            return jsonify({"error": str(e)}), 404
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.post("/api/openclaw/model/deploy")
    def api_deploy_openclaw_model():
        return api_update_openclaw_model()

    @app.post("/api/ollama/models/pull")
    def api_ollama_pull_model():
        """下载模型到 Ollama"""
        body = request.get_json(silent=True) or {}
        model_name = (body.get("model") or "").strip()
        try:
            _, ollama_model = split_openclaw_model_name(model_name)
            pull_info = pull_ollama_model_async(ollama_model)

            return jsonify({
                "ok": True,
                "model": ollama_model,
                "message": f"Started pulling model '{ollama_model}' via Ollama HTTP API.",
                "ollama_pull": pull_info,
            })
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except docker.errors.NotFound:
            return jsonify({"error": "Ollama container not found"}), 404
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.get("/api/ollama/models/pull/status")
    def api_ollama_pull_status():
        """获取 Ollama pull 任务状态"""
        try:
            models = list_ollama_models()
            installed = [m.get("name", "") for m in models]
            pulling = any(job.get("status") == "pulling" for job in ollama_pull_jobs.values())
            return jsonify({
                "pulling": pulling,
                "installed": installed,
                "jobs": ollama_pull_jobs,
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.get("/api/ollama/models/pull/logs")
    def api_ollama_pull_logs():
        """获取 Ollama pull 日志"""
        try:
            return jsonify({
                "logs": json.dumps(ollama_pull_jobs, ensure_ascii=False, indent=2),
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.get("/")
    def index():
        poll_ms = 5000
        preview_base = app.config["PUBLIC_PREVIEW_BASE_URL"]
        html = f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Hermit Control {CONTROL_BASE_PORT}</title>
    <style>
      :root {{
        --bg: #070A10;
        --panel: rgba(255,255,255,0.06);
        --line: rgba(255,255,255,0.14);
        --text: rgba(255,255,255,0.92);
        --muted: rgba(255,255,255,0.62);
        --ok: #3AE374;
        --warn: #FFC048;
        --bad: #FF4D4D;
        --shadow: 0 24px 60px rgba(0, 0, 0, 0.55);
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        color: var(--text);
        background:
          radial-gradient(1200px 700px at 20% -10%, rgba(58, 227, 116, 0.10), transparent 60%),
          radial-gradient(900px 600px at 110% 10%, rgba(255, 192, 72, 0.10), transparent 55%),
          radial-gradient(900px 700px at 55% 120%, rgba(124, 92, 255, 0.13), transparent 55%),
          var(--bg);
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
      }}
      header {{
        position: sticky;
        top: 0;
        z-index: 10;
        background: linear-gradient(to bottom, rgba(7,10,16,0.92), rgba(7,10,16,0.55));
        backdrop-filter: blur(14px);
        border-bottom: 1px solid var(--line);
      }}
      .wrap {{ padding: 16px 18px; max-width: 1440px; margin: 0 auto; }}
      h1 {{ margin: 0; font-size: 18px; }}
      .sub {{ margin-top: 8px; color: var(--muted); font-size: 12px; }}
      .panel {{
        margin-top: 14px;
        border: 1px solid rgba(255,255,255,0.13);
        border-radius: 14px;
        background: linear-gradient(180deg, rgba(255,255,255,0.08), rgba(255,255,255,0.03));
        box-shadow: var(--shadow);
        padding: 14px;
      }}
      .row {{ display:flex; gap:10px; flex-wrap:wrap; align-items:center; }}
      select, input, button {{
        border-radius: 10px;
        border: 1px solid rgba(255,255,255,0.16);
        background: rgba(0,0,0,0.30);
        color: var(--text);
        padding: 10px 12px;
        font-size: 12px;
        font-family: inherit;
      }}
      input {{ min-width: 220px; }}
      button {{ cursor: pointer; background: rgba(255,255,255,0.08); }}
      button:hover {{ background: rgba(255,255,255,0.12); }}
      .grid {{
        margin-top: 16px;
        display: flex;
        flex-direction: column;
        gap: 14px;
      }}
      .card {{
        border: 1px solid rgba(255,255,255,0.13);
        border-radius: 14px;
        overflow: hidden;
        background: linear-gradient(180deg, rgba(255,255,255,0.08), rgba(255,255,255,0.03));
        box-shadow: var(--shadow);
        transition: border-color 0.2s, box-shadow 0.2s;
      }}
      .card:focus-within,
      .card.tab-selected {{
        border-color: #3AE374;
        box-shadow: 0 0 0 2px rgba(58, 227, 116, 0.3), var(--shadow);
        outline: none;
      }}
      .card.collapsed .card-body {{ display: none; }}
      .collapse-btn {{ background: none; border: none; color: #888; cursor: pointer; font-size: 12px; padding: 4px; }}
      .card-head {{
        display: flex;
        justify-content: space-between;
        gap: 10px;
        align-items: center;
        padding: 12px;
        border-bottom: 1px solid rgba(255,255,255,0.11);
      }}
      .meta {{ color: var(--muted); font-size: 11px; }}
      .git-tools {{
        display: none;
        align-items: center;
        gap: 6px;
        flex-wrap: wrap;
        margin-left: 0;
      }}
      .actions {{ display:flex; gap:8px; padding: 10px 12px; border-bottom: 1px solid rgba(255,255,255,0.08); }}
      .cmd-bar {{
        display: flex;
        gap: 8px;
        padding: 10px 12px;
        border-bottom: 1px solid rgba(255,255,255,0.08);
      }}
      .cmd-mode {{
        width: 110px;
      }}
      .cmd-input {{
        flex: 1;
        min-width: 120px;
      }}
      pre {{
        margin: 0;
        padding: 12px;
        height: calc(20 * 1.35em);
        overflow: auto;
        font-size: 12px;
        line-height: 1.35;
        white-space: pre-wrap;
        word-break: break-word;
      }}
      .status-running {{ color: var(--ok); }}
      .status-other {{ color: var(--warn); }}
      .small {{ color: var(--muted); font-size: 11px; margin-left: 8px; }}
      .model-panel {{
        margin-top: 14px;
        border: 1px solid rgba(255,255,255,0.13);
        border-radius: 14px;
        background: linear-gradient(180deg, rgba(255,255,255,0.08), rgba(255,255,255,0.03));
        box-shadow: var(--shadow);
        padding: 14px;
      }}
      .model-section {{
        margin-bottom: 12px;
      }}
      .model-section-title {{
        font-size: 13px;
        font-weight: 600;
        color: #3AE374;
        margin-bottom: 8px;
      }}
      .model-section-title a {{
        color: #3AE374;
        text-decoration: none;
      }}
      .model-section-title a:hover {{
        text-decoration: underline;
      }}
      .model-info {{
        background: rgba(0,0,0,0.3);
        border-radius: 8px;
        padding: 10px;
        margin-bottom: 10px;
      }}
      .model-row {{
        display: flex;
        gap: 8px;
        align-items: center;
        flex-wrap: wrap;
      }}
      .model-status {{
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 11px;
        background: rgba(58, 227, 116, 0.2);
        color: #3AE374;
      }}
      .model-status.error {{
        background: rgba(255, 77, 77, 0.2);
        color: #FF4D4D;
      }}
      .model-status.pulling {{
        background: rgba(255, 192, 72, 0.2);
        color: #FFC048;
      }}
      #modelList {{
        max-height: 150px;
        overflow-y: auto;
        margin-top: 8px;
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 8px;
        background: rgba(0,0,0,0.3);
        padding: 8px;
      }}
      .model-item {{
        padding: 4px 8px;
        border-radius: 4px;
        cursor: pointer;
        margin-bottom: 2px;
      }}
      .model-item:hover {{
        background: rgba(255,255,255,0.1);
      }}
      .model-item.selected {{
        background: rgba(58, 227, 116, 0.2);
        color: #3AE374;
      }}
      #pullLogs {{
        max-height: 100px;
        overflow-y: auto;
        background: rgba(0,0,0,0.4);
        border-radius: 8px;
        padding: 8px;
        font-size: 11px;
        white-space: pre-wrap;
        margin-top: 8px;
        display: none;
      }}
    </style>
  </head>
  <body>
    <header>
      <div class="wrap">
        <div style="display:flex;align-items:center;gap:20px;margin-bottom:12px;">
          <h1 style="margin:0;">OLLAMA CLAW</h1>
        </div>
        <div class="sub">创建类型：openclaw@2026.2.9；端口从 {CONTROL_BASE_PORT + 1} 递增，容器名格式：端口号-容器名称。</div>
        <div class="panel">
          <div class="row">
            <select id="agentType"></select>
            <input id="agentName" placeholder="输入容器名称（例如 writer）" />
            <button id="createBtn">一键创建</button>
            <span class="small" id="notice"></span>
          </div>
        </div>
        <div class="model-panel">
          <div class="model-section">
            <div class="model-section-title"><a href="https://ollama.com/library" target="_blank" class="model-link-btn" title="浏览 Ollama 模型库 (opens in new tab)">🤖 模型管理 🌐</a></div>
            <div class="model-info">
              <div style="margin-bottom: 8px;">
                <span style="color: var(--muted);">当前 OpenClaw 模型：</span>
                <span id="currentModel" style="color: #3AE374; font-weight: 600;">加载中...</span>
                <span id="modelStatus" class="model-status"></span>
              </div>
              <div id="downloadProgressContainer" style="display: none; margin: 10px 0; padding: 10px; background: #1a1a2e; border-radius: 8px;">
                <div style="margin-bottom: 5px; color: #fff; font-size: 12px;">
                  <span id="downloadStatus">准备下载...</span>
                </div>
                <div style="background: #333; border-radius: 4px; height: 20px; overflow: hidden;">
                  <div id="downloadProgressBar" style="background: linear-gradient(90deg, #3AE374, #00D9FF); height: 100%; width: 0%; transition: width 0.3s ease; border-radius: 4px;"></div>
                </div>
                <div id="downloadDetails" style="margin-top: 5px; color: #888; font-size: 11px;"></div>
              </div>
              <div class="model-row">
                <input id="modelName" placeholder="输入模型名称（如 qwen2.5:0.5b）" style="min-width: 240px;" />
                <button id="deployModelBtn" style="background: #3AE374; color: #000;">提交并部署</button>
                <button id="pullModelBtn" style="background: #2196F3; color: #fff;">下载模型到 Ollama</button>
                <button id="refreshModelsBtn">刷新模型列表</button>
              </div>
            </div>
            <div id="modelList"></div>
            <div id="pullLogs"></div>
          </div>
        </div>
      </div>
    </header>
    <main class="wrap">
      <div id="cards" class="grid"></div>
    </main>
    <script>
      const cards = document.getElementById("cards");
      const agentType = document.getElementById("agentType");
      const agentName = document.getElementById("agentName");
      const createBtn = document.getElementById("createBtn");
      const notice = document.getElementById("notice");
      const tail = 20;
      const previewBase = "{preview_base}";

      function showModal(title, content) {{
        const overlay = document.createElement("div");
        overlay.style.cssText = "position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.75);z-index:1000;display:flex;align-items:center;justify-content:center;";
        const box = document.createElement("div");
        box.style.cssText = "background:#1a1a2e;border:1px solid rgba(255,255,255,0.2);border-radius:12px;padding:24px;max-width:700px;width:90%;max-height:80vh;display:flex;flex-direction:column;";
        const header = document.createElement("div");
        header.style.cssText = "display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;";
        const titleSpan = document.createElement("span");
        titleSpan.style.cssText = "font-size:18px;font-weight:bold;color:#fff;";
        titleSpan.textContent = title;
        const copyBtn = document.createElement("button");
        copyBtn.style.cssText = "padding:6px 12px;background:#3AE374;color:#000;border:none;border-radius:4px;cursor:pointer;font-weight:600;font-size:12px;";
        copyBtn.textContent = "复制";
        copyBtn.onclick = () => {{
          navigator.clipboard.writeText(content).then(() => {{
            copyBtn.textContent = "已复制!";
            copyBtn.style.background = "#666";
            setTimeout(() => {{ copyBtn.textContent = "复制"; copyBtn.style.background = "#3AE374"; }}, 1500);
          }});
        }};
        header.appendChild(titleSpan);
        header.appendChild(copyBtn);
        const contentDiv = document.createElement("div");
        contentDiv.style.cssText = "flex:1;overflow:auto;padding:16px;background:#0d0d1a;border-radius:8px;border:1px solid rgba(255,255,255,0.1);white-space:pre-wrap;word-break:break-word;max-height:60vh;font-size:13px;line-height:1.5;color:#e0e0e0;";
        contentDiv.textContent = content;
        box.appendChild(header);
        box.appendChild(contentDiv);
        overlay.appendChild(box);
        document.body.appendChild(overlay);
        overlay.onclick = (e) => {{ if (e.target === overlay) overlay.remove(); }};
      }};

      async function loadTypes() {{
        const res = await fetch("/api/agent-types", {{ cache: "no-store" }});
        const data = await res.json();
        agentType.innerHTML = "";
        for (const item of data.items || []) {{
          const op = document.createElement("option");
          op.value = item.value;
          op.textContent = item.label;
          agentType.appendChild(op);
        }}
      }}

      async function loadCurrentModel() {{
        try {{
          const res = await fetch("/api/openclaw/model", {{ cache: "no-store" }});
          const data = await res.json();
          document.getElementById("currentModel").textContent = data.model || "未设置";
          document.getElementById("modelName").value = data.model || "";
        }} catch (e) {{
          document.getElementById("currentModel").textContent = "加载失败";
        }}
      }}

      async function loadOllamaModels() {{
        try {{
          const res = await fetch("/api/ollama/models", {{ cache: "no-store" }});
          const data = await res.json();
          const modelList = document.getElementById("modelList");
          if (data.error) {{
            modelList.innerHTML = `<div style="color: #FF4D4D;">错误: ${{data.error}}</div>`;
            return;
          }}
          if (!data.models || data.models.length === 0) {{
            modelList.innerHTML = '<div style="color: #FFC048;">Ollama 中没有已安装的模型</div>';
            return;
          }}
          const currentModel = document.getElementById("currentModel").textContent;
          modelList.innerHTML = data.models.map(m => `
            <div class="model-item ${{m.name === currentModel ? 'selected' : ''}}"
                 data-model="${{m.name}}"
                 onclick="selectModel('${{m.name}}')">
              ${{m.name}} <span style="color: var(--muted);">(${{formatSize(m.size)}})</span>
            </div>
          `).join('');
        }} catch (e) {{
          document.getElementById("modelList").innerHTML = `<div style="color: #FF4D4D;">错误: ${{e.message}}</div>`;
        }}
      }}

      function formatSize(bytes) {{
        if (!bytes) return "0 B";
        const units = ["B", "KB", "MB", "GB", "TB"];
        let i = 0;
        let size = bytes;
        while (size >= 1024 && i < units.length - 1) {{
          size /= 1024;
          i++;
        }}
        return size.toFixed(1) + " " + units[i];
      }}

      function selectModel(modelName) {{
        document.getElementById("modelName").value = modelName;
        document.querySelectorAll(".model-item").forEach(el => {{
          el.classList.remove("selected");
          if (el.dataset.model === modelName) {{
            el.classList.add("selected");
          }}
        }});
      }}

      async function deployModel() {{
        const selectedModel = document.querySelector(".model-item.selected");
        if (!selectedModel) {{
          alert("请从列表中选择模型");
          return;
        }}
        const modelName = selectedModel.dataset.model;
        const status = document.getElementById("modelStatus");
        const pullLogs = document.getElementById("pullLogs");
        status.textContent = "提交中...";
        status.className = "model-status pulling";
        pullLogs.style.display = "block";
        pullLogs.textContent = `提交模型部署: ${{modelName}}\n- 更新 OpenClaw 配置\n- 向 Ollama 发送下载指令\n- 重启 gateway\n- 重建 agent 容器\n`;
        try {{
          const res = await fetch("/api/openclaw/model/deploy", {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{ model: modelName }}),
          }});
          const data = await res.json();
          if (!res.ok) {{
            status.textContent = "错误: " + (data.error || "未知错误");
            status.className = "model-status error";
            pullLogs.textContent += "错误: " + (data.error || "未知错误") + "\\n";
            return;
          }}
          status.textContent = "✓ 已提交部署";
          status.className = "model-status";
          document.getElementById("currentModel").textContent = data.model || modelName;
          pullLogs.textContent += `已写入配置: ${{data.model}}\n`;
          pullLogs.textContent += `Ollama 下载: ${{data.ollama_model}}\n`;
          pullLogs.textContent += `已重启 gateway: ${{data.restarted_gateway}}\n`;
          pullLogs.textContent += `已重建 agent: ${{(data.recreated_agents || []).map(x => x.container_name || x).join(", ") || "无"}}\n`;
          if (data.recreation_errors && Object.keys(data.recreation_errors).length) {{
            pullLogs.textContent += `重建错误: ${{JSON.stringify(data.recreation_errors)}}\n`;
          }}
          await refreshCards();
          await loadOllamaModels();
          setTimeout(checkPullStatus, 5000);
          setTimeout(() => {{
            status.textContent = "";
          }}, 5000);
        }} catch (e) {{
          status.textContent = "错误: " + e.message;
          status.className = "model-status error";
          pullLogs.textContent += "错误: " + e.message + "\\n";
        }}
      }}

      async function pullModel() {{
        const modelName = document.getElementById("modelName").value.trim();
        if (!modelName) {{
          alert("请输入模型名称");
          return;
        }}
        const status = document.getElementById("modelStatus");
        const pullLogs = document.getElementById("pullLogs");
        const progressContainer = document.getElementById("downloadProgressContainer");
        const progressBar = document.getElementById("downloadProgressBar");
        const downloadStatus = document.getElementById("downloadStatus");
        const downloadDetails = document.getElementById("downloadDetails");
        
        status.textContent = "下载中...";
        status.className = "model-status pulling";
        pullLogs.style.display = "block";
        pullLogs.textContent = `开始下载模型: ${{modelName}}\n`;
        
        progressContainer.style.display = "block";
        progressBar.style.width = "0%";
        downloadStatus.textContent = `正在下载: ${{modelName}}`;
        downloadDetails.textContent = "初始化中...";
        
        try {{
          const res = await fetch("/api/ollama/models/pull", {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{ model: modelName }}),
          }});
          const data = await res.json();
          if (!res.ok) {{
            status.textContent = "错误: " + (data.error || "未知错误");
            status.className = "model-status error";
            pullLogs.textContent += "错误: " + (data.error || "未知错误") + "\\n";
            downloadStatus.textContent = "下载失败";
            progressBar.style.background = "#FF4D4D";
            downloadDetails.textContent = data.error || "未知错误";
            return;
          }}
          pullLogs.textContent += data.message + "\\n";
          status.textContent = "下载已启动";
          downloadStatus.textContent = `正在下载: ${{modelName}}`;
          downloadDetails.textContent = "正在获取进度...";
          setTimeout(checkPullStatus, 1000);
        }} catch (e) {{
          status.textContent = "错误: " + e.message;
          status.className = "model-status error";
          pullLogs.textContent += "错误: " + e.message + "\\n";
          downloadStatus.textContent = "下载失败";
          progressBar.style.background = "#FF4D4D";
          downloadDetails.textContent = e.message;
        }}
      }}

      async function checkPullStatus() {{
        try {{
          const res = await fetch("/api/ollama/models/pull/status");
          const data = await res.json();
          const status = document.getElementById("modelStatus");
          const pullLogs = document.getElementById("pullLogs");
          const progressBar = document.getElementById("downloadProgressBar");
          const downloadStatus = document.getElementById("downloadStatus");
          const downloadDetails = document.getElementById("downloadDetails");
          const progressContainer = document.getElementById("downloadProgressContainer");
          
          if (data.pulling) {{
            const jobs = data.jobs || {{}};
            const jobKeys = Object.keys(jobs);
            if (jobKeys.length > 0) {{
              const job = jobs[jobKeys[0]];
              let statusText = "下载中";
              if (job.status_message) {{
                statusText += ": " + job.status_message;
              }}
              if (job.progress !== undefined) {{
                statusText += " (" + Math.round(job.progress) + "%)";
                progressBar.style.width = Math.round(job.progress) + "%";
              }}
              status.textContent = statusText;
              downloadStatus.textContent = statusText;
              downloadDetails.textContent = job.status_message || "下载中";
              if (pullLogs) {{
                pullLogs.textContent = (job.status_message || "下载中") + "\\n";
              }}
            }} else {{
              status.textContent = "下载中...";
              downloadStatus.textContent = "下载中...";
            }}
            status.className = "model-status pulling";
            setTimeout(checkPullStatus, 1000);
          }} else {{
            status.textContent = "✓ 下载完成";
            status.className = "model-status";
            downloadStatus.textContent = "✓ 下载完成";
            progressBar.style.width = "100%";
            progressBar.style.background = "linear-gradient(90deg, #3AE374, #00D9FF)";
            downloadDetails.textContent = "模型下载完成";
            progressContainer.style.display = "none";
            if (pullLogs) {{
              pullLogs.textContent = "✓ 下载完成\\n";
            }}
            await loadOllamaModels();
          }}
        }} catch (e) {{
          console.error("Check pull status error:", e);
          downloadDetails.textContent = "检查状态失败: " + e.message;
          setTimeout(checkPullStatus, 2000);
        }}
      }}

      // 初始化时立即检查状态
      checkPullStatus();

      document.getElementById("deployModelBtn").onclick = deployModel;
      document.getElementById("pullModelBtn").onclick = pullModel;
      document.getElementById("refreshModelsBtn").onclick = async () => {{
        await loadCurrentModel();
        await loadOllamaModels();
      }};

      (async () => {{
        await loadTypes();
        await loadCurrentModel();
        await loadOllamaModels();
        await refreshCards();
        setInterval(refreshCards, {poll_ms});
      }})();

      function makeCard(item) {{
        const div = document.createElement("div");
        div.className = "card collapsed";
        div.dataset.name = item.container_name;
        div.setAttribute("tabindex", "-1");
        const stCls = item.status === "running" ? "status-running" : "status-other";
        const managed = !!item.managed;
        const sshPort = item.ssh_port;
        div.innerHTML = `
          <div class="card-head">
            <div style="display:flex;align-items:center;gap:8px;">
              <button class="collapse-btn" data-action="collapse">▶</button>
              <div style="display:flex;flex-direction:column;gap:2px;">
                <div style="display:flex;align-items:center;gap:8px;">
                  <span class="card-title" data-action="git-dropdown" style="cursor:pointer;color:#2196F3;font-weight:500;">${{item.container_name}}</span>
                  <div class="git-tools">
                    <select class="git-mode-select" data-action="git-mode" style="padding:2px 4px;font-size:11px;max-width:120px;">
                      <option value="checkout">git checkout</option>
                      <option value="reset-hard">git reset --hard</option>
                    </select>
                    <select class="git-select" data-action="git-select" style="padding:2px 4px;font-size:11px;max-width:220px;">
                      <option value="">加载中...</option>
                    </select>
                  </div>
                </div>
                <div class="meta">${{item.agent_type}} · ${{item.host_port}}:{SERVICE_PORT} · SSH:${{item.ssh_port}}</div>
              </div>
            </div>
            <div class="meta ${{stCls}}" data-status="${{item.status}}" data-port="${{item.host_port}}">${{item.status}}</div>
          </div>
          <div class="card-body">
          <div class="actions">
            <button data-action="ssh">SSH终端</button>
            <button data-action="refresh">刷新日志</button>
            <button data-action="download">下载日志</button>
            <button data-action="recreate">重建</button>
            <button data-action="cleanup-context">清理上下文</button>
            <button data-action="init">发送初始消息</button>
          </div>
          <div class="cmd-bar">
            <textarea class="cmd-input" data-role="cmd-input" placeholder="输入对话内容" style="flex:1; resize:vertical; min-height:60px;"></textarea>
            <button data-action="send">发送</button>
          </div>
          <pre id="log-${{item.container_name}}" class="log-view">${{item.logs || ""}}</pre>
          <iframe id="ssh-${{item.container_name}}" class="ssh-view" style="display:none; width:100%; height:400px; border:1px solid #ccc;" src="" allow="fullscreen"></iframe>
          </div>
        `;
        const collapseBtn = div.querySelector('.collapse-btn');
        const cardBody = div.querySelector('.card-body');
        collapseBtn.onclick = () => {{
          div.classList.toggle("collapsed");
          collapseBtn.textContent = div.classList.contains("collapsed") ? "▶" : "▼";
        }};
        const logBox = div.querySelector("pre");
        const sshIframe = div.querySelector("iframe");
        const sshBtn = div.querySelector('button[data-action="ssh"]');
        const cmdInput = div.querySelector('[data-role="cmd-input"]');
        let sshActive = false;
        let lastEnterTime = 0;
        cmdInput.addEventListener('keydown', (e) => {{
          if (e.key === 'Enter') {{
            const now = Date.now();
            if (now - lastEnterTime < 600) {{
              e.preventDefault();
              sendMessage();
              lastEnterTime = 0;
            }} else {{
              lastEnterTime = now;
            }}
          }}
        }});
        sshBtn.onclick = () => {{
          sshActive = !sshActive;
          sshBtn.style.fontWeight = sshActive ? "bold" : "";
          sshBtn.style.background = sshActive ? "#4caf50" : "";
          console.log('SSH button clicked, active:', sshActive, 'container:', item.container_name);
          if (sshActive) {{
            const url = `/api/agents/${{encodeURIComponent(item.container_name)}}/ssh-terminal`;
            console.log('Setting iframe src to:', url);
            sshIframe.style.display = "block";
            sshIframe.style.visibility = "visible";
            sshIframe.src = url;
            logBox.style.display = "none";
          }} else {{
            sshIframe.src = "";
            sshIframe.style.display = "none";
            sshIframe.style.visibility = "hidden";
            logBox.style.display = "block";
          }}
        }};
        div.querySelector('button[data-action="refresh"]').onclick = async () => {{
          const r = await fetch(`/api/agents/${{encodeURIComponent(item.container_name)}}/logs?tail=200`, {{ cache: "no-store" }});
          const d = await r.json();
          logBox.textContent = d.logs || d.error || "";
          logBox.scrollTop = logBox.scrollHeight;
        }};
        div.querySelector('button[data-action="download"]').onclick = () => {{
          window.open(`/api/agents/${{encodeURIComponent(item.container_name)}}/logs/download?tail=500`, "_blank");
        }};
        div.querySelector('button[data-action="recreate"]').onclick = async () => {{
          if (!managed) return;
          const r = await fetch(`/api/agents/${{encodeURIComponent(item.container_name)}}/recreate`, {{ method: "POST" }});
          const d = await r.json();
          if (!r.ok) {{
            logBox.textContent += `\\nERROR: ${{d.error || `HTTP ${{r.status}}`}}\\n`;
            return;
          }}
          logBox.textContent += `\\n(recreated) ${{d.container_name}}\\n`;
          await refreshCards();
        }};
        div.querySelector('button[data-action="init"]').onclick = async () => {{
          const r = await fetch(`/api/agents/${{encodeURIComponent(item.container_name)}}/send-message`, {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{ message: "" }}),
          }});
          if (!r.ok) {{
            const d = await r.json();
            logBox.textContent += `\\nERROR: ${{d.error || `HTTP ${{r.status}}`}}\\n`;
            return;
          }}
          logBox.textContent += `\n(已发送初始消息)\n`;
        }};
        div.querySelector('button[data-action="cleanup-context"]').onclick = async () => {{
          const r = await fetch(`/api/agents/${{encodeURIComponent(item.container_name)}}/cleanup-context`, {{ method: "POST" }});
          if (!r.ok) {{
            const d = await r.json();
            logBox.textContent += `\nERROR: ${{d.error || `HTTP ${{r.status}}`}}\n`;
            return;
          }}
          const d = await r.json();
          logBox.textContent += `\n(上下文已清理) ${{d.output || ""}}\n`;
        }};
        
        const cardTitle = div.querySelector('.card-title');
        const gitSelect = div.querySelector('.git-select');
        const gitTools = div.querySelector('.git-tools');
        const gitModeSelect = div.querySelector('.git-mode-select');
        const loadGitCommits = async () => {{
          try {{
            const r = await fetch(`/api/agents/${{encodeURIComponent(item.container_name)}}/git-commits`);
            const d = await r.json();
            if (d.error) {{
              gitSelect.innerHTML = '<option value="">非Git项目</option>';
              return;
            }}
            gitSelect.innerHTML = '<option value="">选择版本...</option>';
            (d.commits || []).forEach(c => {{
              const opt = document.createElement("option");
              opt.value = c.hash;
              opt.textContent = (c.is_current ? "✓ " : "") + c.message;
              gitSelect.appendChild(opt);
            }});
          }} catch(e) {{
            console.error("Failed to load git commits:", e);
          }}
        }};
        
        cardTitle.onclick = () => {{
          if (gitTools.style.display === "none" || !gitTools.style.display) {{
            gitTools.style.display = "inline-flex";
            if (gitSelect.options.length <= 1) loadGitCommits();
          }} else {{
            gitTools.style.display = "none";
          }}
        }};
        
        gitSelect.onchange = async () => {{
          const hash = gitSelect.value;
          if (!hash) return;
          gitTools.style.display = "none";
          const isFork = hash === "__FORK__";
          const gitMode = gitModeSelect ? gitModeSelect.value : "checkout";
          const opLabel = isFork ? "fork" : (gitMode === "reset-hard" ? "git reset --hard" : "git checkout");
          const targetLabel = isFork ? item.container_name : hash.substring(0,7);
          logBox.textContent += `\n[${{opLabel}} ${{targetLabel}}] 执行中...\n`;
          const r = await fetch(`/api/agents/${{encodeURIComponent(item.container_name)}}/git-reset`, {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{ commit_hash: hash, hard: gitMode === "reset-hard" }}),
          }});
          const d = await r.json();
          if (!r.ok) {{
            logBox.textContent += `ERROR: ${{d.error || `HTTP ${{r.status}}`}}\n`;
            gitSelect.value = "";
            return;
          }}
          if (d.mode === "fork") {{
            logBox.textContent += `[fork 完成] 新容器: ${{d.new_container}}\n`;
          }} else {{
            const doneLabel = d.mode === "hard_reset" ? "git reset --hard 完成" : "git checkout 完成";
            logBox.textContent += `[${{doneLabel}}] ${{d.git_output || ""}}\n[容器重建中] ${{d.new_container}}\n`;
          }}
          gitSelect.value = "";
          await refreshCards();
        }};
        
        div.querySelector('button[data-action="send"]').onclick = () => sendMessage();
        
        const cardKey = `card_${{item.container_name}}`;
        if (!window.cardStates) window.cardStates = {{}};
        
        const formatTime = () => {{
          const d = new Date();
          return d.getFullYear() + "-" + String(d.getMonth()+1).padStart(2,"0") + "-" + String(d.getDate()).padStart(2,"0") + " " + String(d.getHours()).padStart(2,"0") + ":" + String(d.getMinutes()).padStart(2,"0") + ":" + String(d.getSeconds()).padStart(2,"0");
        }};
        
        const sendMessage = async () => {{
          const msg = (cmdInput.value || "").trim();
          if (!msg) return;
          window.cardStates[item.container_name] = logBox.textContent;
          window.cardStates[item.container_name] += "\\n" + formatTime() + " $ " + msg + "\\n";
          logBox.textContent = window.cardStates[item.container_name];
          logBox.scrollTop = logBox.scrollHeight;
          cmdInput.value = "";
          
          const r = await fetch(`/api/agents/${{encodeURIComponent(item.container_name)}}/send-message`, {{
            method: "POST",
            headers: {{ "Content-Type": "application/json" }},
            body: JSON.stringify({{ message: msg }}),
          }});
          if (!r.ok) {{
            const d = await r.json();
            window.cardStates[item.container_name] += `ERROR: ${{d.error || `HTTP ${{r.status}}`}}\\n`;
          }}
          logBox.textContent = window.cardStates[item.container_name];
          logBox.scrollTop = logBox.scrollHeight;
          
          await new Promise(resolve => setTimeout(resolve, 3000));
          const logResp = await fetch(`/api/agents/${{encodeURIComponent(item.container_name)}}/logs?tail=500`, {{ cache: "no-store" }});
          if (logResp.ok) {{
            const logData = await logResp.json();
            if (logData.logs) {{
              window.cardStates[item.container_name] = logData.logs;
              logBox.textContent = window.cardStates[item.container_name];
              logBox.scrollTop = logBox.scrollHeight;
            }}
          }}
        }};
        if (!managed) {{
          cmdInput.disabled = true;
          cmdInput.placeholder = "该容器非{CONTROL_BASE_PORT}创建（compose成员），默认只读显示";
          div.querySelector('button[data-action="recreate"]').disabled = true;
        }}
        return div;
      }}

      async function refreshCards() {{
        const res = await fetch(`/api/agents?tail=${{tail}}`, {{ cache: "no-store" }});
        const data = await res.json();
        
        // 避免粗暴清空重绘导致焦点丢失，我们采用替换卡片内容或只追加新卡片
        const existingNames = new Set(Array.from(cards.children).map(c => c.dataset.name));
        const newNames = new Set();

        for (const item of data.items || []) {{
          newNames.add(item.container_name);
          let card = document.querySelector(`.card[data-name="${{item.container_name}}"]`);
          if (!card) {{
            card = makeCard(item);
            card.dataset.name = item.container_name;
            cards.appendChild(card);
            const stDiv = card.querySelector('.meta[data-status]');
            if (stDiv && stDiv.dataset.status === 'running') {{
                const port = stDiv.dataset.port;
                stDiv.innerHTML = `<a href="${{previewBase}}:${{port}}" target="_blank" style="color:inherit;text-decoration:underline;" onclick="event.stopPropagation()">running</a>`;
            }}
          }} else {{
            // 只更新状态和原始日志(如果用户还没交互过)
            const st = card.querySelector('.meta[data-status]') || card.querySelector('.meta.status-running, .meta.status-other');
            if (st) {{
               st.className = `meta status-${{item.status === 'running' ? 'running' : 'other'}}`;
               st.textContent = item.status;
               if (item.status === 'running') {{
                   st.innerHTML = `<a href="${{previewBase}}:${{item.host_port}}" target="_blank" style="color:inherit;text-decoration:underline;" onclick="event.stopPropagation()">running</a>`;
               }}
            }}
            if (!window.cardStates || !window.cardStates[item.container_name]) {{
               const logBox = card.querySelector('pre');
               if (logBox) logBox.textContent = item.logs || "";
            }}
          }}
        }}
        
        // 移除已经不存在的容器
        for (const name of existingNames) {{
           if (!newNames.has(name)) {{
              const card = document.querySelector(`.card[data-name="${{name}}"]`);
              if (card) card.remove();
           }}
        }}
      }}

      createBtn.onclick = async () => {{
        notice.textContent = "创建中...";
        const payload = {{
          type: agentType.value,
          name: agentName.value,
        }};
        const res = await fetch("/api/agents", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(payload),
        }});
        const data = await res.json();
        if (!res.ok) {{
          notice.textContent = data.error || `HTTP ${{res.status}}`;
          return;
        }}
        notice.textContent = `已创建 ${{data.container_name}}`;
        agentName.value = "";
        await refreshCards();
      }};

      (async () => {{
        await loadTypes();
        await refreshCards();
        setInterval(refreshCards, {poll_ms});
        document.addEventListener('keydown', (e) => {{
          if (e.key === 'Tab') {{
            e.preventDefault();
            const cardEls = Array.from(document.querySelectorAll('.card[data-name]'));
            if (!cardEls.length) return;
            
            const nextIndex = (tabIndex + 1) % cardEls.length;
            
            cardEls.forEach((card, i) => {{
              if (i !== nextIndex) {{
                card.classList.add('collapsed');
                card.classList.remove('tab-selected');
                const btn = card.querySelector('.collapse-btn');
                if (btn) btn.textContent = '▶';
              }}
            }});
            
            tabIndex = nextIndex;
            const selected = cardEls[tabIndex];
            selected.classList.remove('collapsed');
            selected.classList.add('tab-selected');
            const btn = selected.querySelector('.collapse-btn');
            if (btn) btn.textContent = '▼';
            
            setTimeout(() => {{
              const msgInput = selected.querySelector('.cmd-input');
              if (msgInput) {{
                msgInput.focus();
                msgInput.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
              }}
            }}, 100);
          }}
        }});
        document.addEventListener('click', (e) => {{
          const card = e.target.closest('.card[data-name]');
          if (!card) return;
          card.classList.remove('collapsed');
        }});
      }})();
    </script>
  </body>
</html>"""
        return make_response(html)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
