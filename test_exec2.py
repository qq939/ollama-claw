import docker, base64
client = docker.from_env()
g = client.containers.get("openclaw-gateway")
script = """
const token = process.env.OPENCLAW_PAIR_TOKEN || "";
console.log("STDOUT start token=" + token.length);
console.error("STDERR start");
const ws = new WebSocket("ws://127.0.0.1:18790");
ws.addEventListener("open", () => {
  console.log("ws open");
  ws.close();
});
ws.addEventListener("close", () => process.exit(0));
"""
b = base64.b64encode(script.encode()).decode()
cmd = 'OPENCLAW_PAIR_TOKEN=2ac145e2572b9b2fb44717b520c22588858403a75d4a6ea2 node -e "$(echo ' + b + ' | base64 -d)"'
r = g.exec_run(["/bin/sh", "-lc", cmd], user="agent")
print("exit:", r.exit_code)
out = r.output
print("out type:", type(out).__name__)
if hasattr(out, "__len__"):
    print("out len:", len(out))
print("out repr:", repr(out)[:500])
