#!/bin/sh
set -eu
mkdir -p "/home/agent/.openclaw/workspace/project/logs"
node -e 'const fs=require("fs"); const p=process.env.HOME+"/.openclaw/openclaw.json"; const j=JSON.parse(fs.readFileSync(p,"utf8")); j.gateway=j.gateway||{}; j.gateway.mode="remote"; j.gateway.remote=j.gateway.remote||{}; j.gateway.remote.url="ws://"+(process.env.OPENCLAW_GATEWAY_HOST||"172.30.0.10")+":"+(process.env.OPENCLAW_GATEWAY_PORT||"18790"); if(process.env.OPENCLAW_GATEWAY_TOKEN) j.gateway.remote.token=process.env.OPENCLAW_GATEWAY_TOKEN; delete j.gateway.bind; fs.writeFileSync(p,JSON.stringify(j,null,2)); fs.chmodSync(p,0o600);'
msg_file="$(mktemp /tmp/openclaw-message.XXXXXX)"
out_file="$(mktemp /tmp/openclaw-output.XXXXXX)"
trap 'rm -f "$msg_file" "$out_file"' EXIT
printf '%s' '5L2g6LSf6LSj55qE5piv5a6M5pW055qE5byA5Y+R44CB5rWL6K+V44CB5Y+R546wYnVn44CB5Y+Y5pu055qE5rWB56iL77yM6aG555uu5pivd2ViIGFwcCA4MDgy77yI56uv5Y+j5Y+377yJ77yMd2ViIGFwcCA4MDgy5omA5Zyo55qE55uu5b2V5pivL2hvbWUvYWdlbnQvLm9wZW5jbGF3L3dvcmtzcGFjZS9wcm9qZWN077yM5aaC5p6ccHJvamVjdOaWh+S7tuWkueaciXdlYiBhcHDvvIzor7fmn6XnnIvlkK/liqjohJrmnKzmmK/lkKblrZjlnKjvvIwvaG9tZS9hZ2VudC8ub3BlbmNsYXcvd29ya3NwYWNlL3Byb2plY3QvdXNlcl9zdGFydC5zaOOAguWmguaenOS4jeWtmOWcqOWQr+WKqOiEmuacrO+8jOivt+eri+WNs+WGmeWlveWQr+WKqOiEmuacrHVzZXJfc3RhcnQuc2jvvIzovpPlh7rml6Xlv5fliLDlvZPliY3nm67lvZXkuIvnmoRsb2dzL3N0YXJ0LmxvZ+OAguW5tuS4lOaVtOeQhuaXpeW/l+aWh+S7tmxvZ3MvYWdlbnRfdHVpLmxvZ+mHjOeahOS4u+imgeWGheWuue+8jOais+eQhuWHuumhueebruaehOW7uueahOe7k+aehOWSjOe7huiKgu+8jOaAu+e7k+acgOWQjjPova7lr7nor53nmoTlhoXlrrnjgILpobnnm67miYDmnInmg6/kvovkv6Hmga/pg73lnKhzeXN0ZW1yZWFkbWUubWTkuK3orrDovb3vvIzmnIDlkI7mm7TmlrDpobnnm65SRUFETUUubWTlkozpobnnm65TS0lMTC5tZA==' | base64 -d > "$msg_file"
printf '\n[openclaw-agent] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" >> "/home/agent/.openclaw/workspace/project/logs/agent_tui.log"
if timeout 120 openclaw agent --agent main --message "$(cat "$msg_file")" --timeout 90 > "$out_file" 2>&1; then
  printf '[openclaw-agent-exit] 0\n' >> "/home/agent/.openclaw/workspace/project/logs/agent_tui.log"
else
  code="$?"
  printf '[openclaw-agent-exit] %s\n' "$code" >> "/home/agent/.openclaw/workspace/project/logs/agent_tui.log"
fi
sed -e 's/\[[0-?]*[ -\/]*[@-~]//g' "$out_file" | tail -120 >> "/home/agent/.openclaw/workspace/project/logs/agent_tui.log"
