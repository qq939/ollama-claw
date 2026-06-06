const token = process.env.OPENCLAW_PAIR_TOKEN || "";
console.log("script start, token len=" + token.length);
const ws = new WebSocket("ws://127.0.0.1:18790");
console.log("ws created");
let id = 0;
const inflight = new Map();
const send = (method, params) => new Promise((resolve, reject) => {
  const reqId = String(++id);
  inflight.set(reqId, { resolve, reject });
  ws.send(JSON.stringify({ type: "req", id: reqId, method, params }));
});
ws.addEventListener("open", async () => {
  console.log("ws open");
  try {
    const hello = await send("connect", {
      minProtocol: 3,
      maxProtocol: 3,
      client: { id: "cli", displayName: "test", mode: "cli", version: "1", platform: "linux" },
      auth: { token }
    });
    console.log("hello: " + JSON.stringify(hello).slice(0, 200));
    if (!hello.ok) { ws.close(); return; }
    const list = await send("device.pair.list", {});
    console.log("list: " + JSON.stringify(list).slice(0, 200));
    const pending = (list.payload && list.payload.pending) || [];
    console.log("pending count: " + pending.length);
    for (const req of pending) {
      const res = await send("device.pair.approve", { requestId: req.requestId });
      console.log("approved " + req.requestId + " ok=" + res.ok);
    }
  } catch (e) {
    console.log("error: " + e.message);
  }
  ws.close();
});
ws.addEventListener("message", (ev) => {
  let msg; try { msg = JSON.parse(ev.data); } catch (_) { return; }
  if (msg.type === "res" && inflight.has(msg.id)) {
    const { resolve } = inflight.get(msg.id);
    inflight.delete(msg.id);
    resolve(msg);
  }
});
ws.addEventListener("close", () => { console.log("ws close"); process.exit(0); });
ws.addEventListener("error", (e) => { console.log("ws err: " + (e && e.message || "")); process.exit(1); });
