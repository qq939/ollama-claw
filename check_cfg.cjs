const m = require("/usr/local/lib/node_modules/openclaw/dist/config-CuE2AFLW.js");
const keys = Object.keys(m).filter(k => k.toLowerCase().includes("load") || k.toLowerCase().includes("config"));
console.log("keys:", keys);
if (m.loadConfig) {
  const cfg = m.loadConfig();
  console.log("auth:", JSON.stringify(cfg.gateway.auth));
  console.log("remote:", JSON.stringify(cfg.gateway.remote));
} else {
  console.log("no loadConfig");
}
