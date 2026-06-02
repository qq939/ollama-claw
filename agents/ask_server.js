const http = require('http');
const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const PORT = Number(process.env.ASK_PORT || 8081);
const HOST = process.env.ASK_HOST || '0.0.0.0';
const AGENT_KIND = process.env.AGENT_KIND || 'openclaw';
const PROJECT_PATH = process.env.PROJECT_PATH || `/home/agent/.${AGENT_KIND}/workspace/project`;
const LOG_PATH = process.env.LOG_PATH || path.join(PROJECT_PATH, 'logs/agent_tui.log');
const TIMEOUT_MS = Number(process.env.ASK_TIMEOUT_MS || 120000);

function sendJson(res, status, data) {
  const body = JSON.stringify(data);
  res.writeHead(status, {
    'content-type': 'application/json; charset=utf-8',
    'content-length': Buffer.byteLength(body),
  });
  res.end(body);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let raw = '';
    req.setEncoding('utf8');
    req.on('data', (chunk) => {
      raw += chunk;
      if (raw.length > 1024 * 1024) {
        reject(new Error('request body too large'));
        req.destroy();
      }
    });
    req.on('end', () => {
      if (!raw.trim()) {
        resolve({});
        return;
      }
      try {
        resolve(JSON.parse(raw));
      } catch (error) {
        reject(new Error(`invalid JSON: ${error.message}`));
      }
    });
    req.on('error', reject);
  });
}

function appendLog(text) {
  try {
    fs.mkdirSync(path.dirname(LOG_PATH), { recursive: true });
    fs.appendFileSync(LOG_PATH, text);
  } catch (_) {}
}

function logSize() {
  try {
    return fs.statSync(LOG_PATH).size;
  } catch (_) {
    return 0;
  }
}

function readLogFrom(offset) {
  try {
    const size = logSize();
    if (size <= offset) {
      return '';
    }
    const fd = fs.openSync(LOG_PATH, 'r');
    const buffer = Buffer.alloc(size - offset);
    fs.readSync(fd, buffer, 0, buffer.length, offset);
    fs.closeSync(fd);
    return buffer.toString('utf8');
  } catch (_) {
    return '';
  }
}

function stripAnsi(text) {
  return String(text || '').replace(/\x1b\[[0-?]*[ -/]*[@-~]/g, '');
}

function run(command, args, options = {}) {
  return new Promise((resolve) => {
    const child = spawn(command, args, {
      cwd: PROJECT_PATH,
      shell: false,
      env: { ...process.env, ...(options.env || {}) },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    let stdout = '';
    let stderr = '';
    const timeout = setTimeout(() => {
      child.kill('SIGTERM');
      setTimeout(() => child.kill('SIGKILL'), 5000);
    }, TIMEOUT_MS);
    child.stdout.on('data', (chunk) => {
      stdout += chunk.toString();
    });
    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString();
    });
    child.on('error', (error) => {
      clearTimeout(timeout);
      resolve({ code: 127, stdout, stderr: `${stderr}${error.message}` });
    });
    child.on('close', (code) => {
      clearTimeout(timeout);
      resolve({ code: code == null ? 1 : code, stdout, stderr });
    });
    if (options.stdin) {
      child.stdin.end(options.stdin);
    } else {
      child.stdin.end();
    }
  });
}

async function askClaude(message) {
  const runner = path.join(PROJECT_PATH, 'run_claude.js');
  if (!fs.existsSync(runner)) {
    return { code: 127, stdout: '', stderr: `missing runner: ${runner}` };
  }
  return run('node', [runner], {
    env: { CLAUDE_MSG: Buffer.from(message, 'utf8').toString('base64') },
  });
}

async function askOpenClaw(message) {
  return run('openclaw', ['agent', '--agent', 'main', '--message', message, '--timeout', '90']);
}

function defaultTarget() {
  return AGENT_KIND === 'openclaw' ? 'openclaw' : 'claude';
}

async function handleAsk(req, res, target = defaultTarget()) {
  let body;
  try {
    body = await readBody(req);
  } catch (error) {
    sendJson(res, 400, { ok: false, error: error.message });
    return;
  }
  const message = String(body.message || body.prompt || body.text || '').trim();
  if (!message) {
    sendJson(res, 400, { ok: false, error: 'message is required' });
    return;
  }
  const timestamp = new Date().toISOString().replace('T', ' ').slice(0, 19);
  appendLog(`\n[${timestamp}] $ ${message}\n[ask/${target}] ${timestamp}\n`);
  const beforeLog = logSize();
  const result = target === 'openclaw' ? await askOpenClaw(message) : await askClaude(message);
  const processOutput = stripAnsi(`${result.stdout || ''}${result.stderr || ''}`);
  const logOutput = stripAnsi(readLogFrom(beforeLog));
  const output = processOutput || logOutput;
  if (processOutput) {
    appendLog(`${processOutput.split('\n').slice(-120).join('\n')}\n`);
  }
  appendLog(`[ask/${target}-exit] ${result.code}\n`);
  sendJson(res, result.code === 0 ? 200 : 500, {
    ok: result.code === 0,
    agent: AGENT_KIND,
    target,
    exit_code: result.code,
    output,
  });
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  if (req.method === 'GET' && (url.pathname === '/health' || url.pathname === '/ask/health')) {
    sendJson(res, 200, { ok: true, agent: AGENT_KIND, project_path: PROJECT_PATH });
    return;
  }
  if (req.method === 'POST' && url.pathname === '/ask') {
    await handleAsk(req, res);
    return;
  }
  sendJson(res, 404, { ok: false, error: 'not found' });
});

server.listen(PORT, HOST, () => {
  appendLog(`[ask-server] listening on ${HOST}:${PORT} for ${AGENT_KIND}\n`);
});
