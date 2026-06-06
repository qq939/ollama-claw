const WebSocket = globalThis.WebSocket || require("/usr/local/lib/node_modules/openclaw/node_modules/ws/wrapper.mjs").default;
const ws = new WebSocket("ws://172.31.0.10:18790");
ws.addEventListener("open", () => {
  // intercept the next message which should be the connect challenge
});
ws.addEventListener("message", (ev) => {
  const msg = JSON.parse(ev.data);
  if (msg.event === "connect.challenge") {
    // Send a manual connect frame using the gateway's known token
    ws.send(JSON.stringify({
      type: "req",
      id: "test1",
      method: "connect",
      params: {
        minProtocol: 3,
        maxProtocol: 3,
        client: { id: "cli", displayName: "test", mode: "cli", version: "1", platform: "linux" },
        auth: { token: "2ac145e2572b9b2fb44717b520c22588858403a75d4a6ea2" }
      }
    }));
  } else if (msg.id === "test1") {
    console.log("connect result:", JSON.stringify(msg).slice(0, 300));
    ws.close();
    process.exit(0);
  }
});
ws.addEventListener("error", (e) => console.log("err:", e.message));
