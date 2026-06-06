import threading
import time
import docker
client = docker.from_env()
g = client.containers.get("openclaw-gateway")
script = r'''
const token = "2ac145e2572b9b2fb44717b520c22588858403a75d4a6ea2";
const ws = new WebSocket("ws://127.0.0.1:18790");
let id = 0;
const inflight = new Map();
const send = (m, p) => new Promise((r) => { const i = String(++id); inflight.set(i, {r}); ws.send(JSON.stringify({type:"req",id:i,method:m,params:p})); });
ws.addEventListener("open", async () => {
  try {
    const h = await send("connect", { minProtocol: 3, maxProtocol: 3, client: {id:"cli",displayName:"t",mode:"cli",version:"1",platform:"linux"}, auth: { token } });
    console.log("h:" + h.ok);
    const l = await send("device.pair.list", {});
    console.log("l:" + l.ok + " p:" + (l.payload && l.payload.pending ? l.payload.pending.length : 0));
    for (const r of (l.payload && l.payload.pending || [])) {
      const a = await send("device.pair.approve", { requestId: r.requestId });
      console.log("a:" + a.ok);
    }
  } catch (e) { console.log("e:" + e.message); }
  ws.close();
});
ws.addEventListener("message", (e) => { const m = JSON.parse(e.data); if (m.type==="res" && inflight.has(m.id)) { inflight.get(m.id).r(m); inflight.delete(m.id); }});
ws.addEventListener("close", () => process.exit(0));
ws.addEventListener("error", () => process.exit(1));
'''
import base64
script_b64 = base64.b64encode(script.encode()).decode()
cmd = f"node -e \"$(echo {script_b64} | base64 -d)\""
print("CMD:", cmd[:100])
r = g.exec_run(["/bin/sh", "-lc", cmd], user="agent")
print("exit_code:", r.exit_code)
print("output:", r.output.decode("utf-8", errors="replace") if isinstance(r.output, bytes) else r.output)
