# OpenClaw 8082 Project

This workspace is the project root for the OpenClaw agent container.

## Runtime

- Container project path: `/home/agent/.openclaw/workspace/project`
- Web app port inside container: `8082`
- Startup script: `user_start.sh`
- Startup log: `logs/start.log`
- Agent conversation log: `logs/agent_tui.log`

`user_start.sh` now creates `logs/` and writes startup output to `logs/start.log`. It auto-detects common web app entrypoints in this order:

1. `package.json` with `start` or `dev`
2. `app.py`
3. `main.py`
4. `index.html`

If no web app exists yet, it logs that no entrypoint was found and exits cleanly.

## Current Project Structure

The current directory is mostly an OpenClaw workspace scaffold rather than an application implementation. Key files:

- `systemreadme.md`: platform conventions, fixed paths, port rules, logging rules, and required end-of-session documentation.
- `AGENTS.md`, `SOUL.md`, `USER.md`, `TOOLS.md`: agent identity and workspace operating instructions.
- `start.sh`: platform-level startup hook that runs `user_start.sh` when present.
- `user_start.sh`: project-level web app startup script.
- `logs/agent_tui.log`: OpenClaw TUI/message log.

## Agent Log Summary

The recent `logs/agent_tui.log` entries show these main events:

- The user requested full web app 8082 ownership: develop, test, find bugs, maintain startup scripts, summarize logs, and update `README.md` and `SKILL.md`.
- Two earlier send attempts failed because the control plane tried to run `/tmp/send_msg.sh`, which did not exist.
- Later validation exposed additional integration issues: local loopback gateway usage, too-small model context, unsupported `--url` for `openclaw agent`, and a missing OpenClaw API provider value.
- The latest send path reached the OpenClaw gateway, paired the `openclaw-tui` client, and selected `ollama/qwen2.5:0.5b`.

## Last Three Conversation Rounds

1. User asked the agent to verify or create `user_start.sh`, send logs to `logs/start.log`, summarize `logs/agent_tui.log`, and update project documentation.
2. A quick test message (`123`) still failed because the old temporary send script path was missing.
3. Follow-up validation messages tested the fixed OpenClaw gateway path and Ollama model connection.

## Notes

This workspace does not currently contain a concrete web app source tree. Add the app files under this directory and keep the app listening on port `8082`.
