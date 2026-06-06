import WebSocket from "/usr/local/lib/node_modules/openclaw/node_modules/ws/wrapper.mjs";
const ws = new WebSocket("ws://127.0.0.1:18790");
let nonce = null;

function send(method, params) {
  ws.send(JSON.stringify({
    type: "req",
    id: Math.random().toString(36).slice(2),
    method,
    params
  }));
}

ws.on("open", () => console.log("opened"));
ws.on("message", (data) => {
  const msg = JSON.parse(data.toString());
  console.log("msg:", JSON.stringify(msg).slice(0, 400));
  if (msg.event === "connect.challenge") {
    nonce = msg.payload.nonce;
    send("connect", {
      minProtocol: 3,
      maxProtocol: 3,
      client: { id: "cli", displayName: "auto-pair-cli", mode: "cli", version: "test", platform: "linux" },
      auth: { token: "2ac145e2572b9b2fb44717b520c22588858403a75d4a6ea2" }
    });
  } else if (msg.id === "1" && msg.ok) {
    // connected, list pending devices
    send("device.pair.list", {});
  }
});
ws.on("close", (code, reason) => {
  console.log("closed:", code, reason.toString());
  process.exit(0);
});
ws.on("error", (e) => console.log("err:", e.message));
