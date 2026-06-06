const Module = require("module");
const orig = Module.prototype.require;
Module.prototype.require = function (id) {
  if (id === "ws") {
    const WS = orig.call(this, id);
    const origSend = WS.prototype.send;
    WS.prototype.send = function (data) {
      try {
        const p = JSON.parse(data);
        if (p && p.method === "connect") {
          console.error("[ws_tap] FULL CONNECT:", JSON.stringify(p));
        }
      } catch (_) {}
      return origSend.apply(this, arguments);
    };
    return WS;
  }
  return orig.call(this, id);
};
