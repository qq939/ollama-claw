// Hook to log all WebSocket sends containing "connect"
const origSend = WebSocket.prototype.send;
WebSocket.prototype.send = function (data) {
  try {
    const parsed = JSON.parse(data);
    if (parsed.method === "connect") {
      const p = parsed.params || {};
      const tok = p.auth && p.auth.token;
      console.log("[ws_tap] connect sent, token=" + JSON.stringify(tok) + " len=" + (tok ? tok.length : 0));
    }
  } catch (_) {}
  return origSend.apply(this, arguments);
};
