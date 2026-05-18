# OpenClaw 8082 Web App Skill

Use this skill when maintaining the web app inside `/home/agent/.openclaw/workspace/project`.

## Required First Checks

1. Read `systemreadme.md` for platform conventions.
2. Check whether a web app exists in the project root.
3. Ensure `user_start.sh` exists, is executable, and writes startup output to `logs/start.log`.
4. Ensure the app listens on `0.0.0.0:8082`.

## Startup Convention

The project-level startup script is `user_start.sh`. It should:

- `cd /home/agent/.openclaw/workspace/project`
- `mkdir -p logs`
- append all output to `logs/start.log`
- start the detected web app on port `8082`

## Logging Convention

- `logs/start.log`: startup script output
- `logs/run.log`: optional application runtime log
- `logs/agent_tui.log`: OpenClaw message/TUI log

## Documentation Convention

After each meaningful change:

1. Update `README.md` with structure, run steps, and behavior changes.
2. Update this `SKILL.md` when workflow or project-specific operating rules change.
3. Summarize recent `logs/agent_tui.log` findings in the README when requested.

## Current State

The workspace currently contains the OpenClaw scaffold and no concrete web app entrypoint. The startup script is prepared for Node, Python, or static HTML apps and will log a clear message when no entrypoint exists.
