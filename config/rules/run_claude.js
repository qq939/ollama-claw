const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const TIMEOUT_MS = 3600 * 1000;
const HOME = process.env.HOME || '/home/agent';
const LOG_FILE = path.join(HOME, '.claude/workspace/project/logs/agent_tui.log');

function readJson(file) {
  for (const encoding of ['utf8', 'utf16le']) {
    try {
      return JSON.parse(fs.readFileSync(file, encoding).replace(/^\uFEFF/, ''));
    } catch (_) {}
  }
  return {};
}

function loadClaudeEnv() {
  const env = {};
  const settings = readJson(path.join(HOME, '.claude/settings.json'));
  if (settings.env && typeof settings.env === 'object') {
    Object.assign(env, settings.env);
  }

  const config = readJson(path.join(HOME, '.claude/config.json'));
  const current = config.claude && config.claude.current;
  const providers = (config.claude && config.claude.providers) || {};
  const provider = (current && providers[current]) || Object.values(providers)[0];
  const providerEnv = provider && provider.settingsConfig && provider.settingsConfig.env;
  if (providerEnv && typeof providerEnv === 'object') {
    Object.assign(env, providerEnv);
  }

  if (env.ANTHROPIC_AUTH_TOKEN && !env.ANTHROPIC_API_KEY) {
    env.ANTHROPIC_API_KEY = env.ANTHROPIC_AUTH_TOKEN;
  }
  return env;
}

const CLAUDE_MSG = process.env.CLAUDE_MSG;
if (!CLAUDE_MSG) {
  console.error('[ERROR] CLAUDE_MSG environment variable is required');
  process.exit(1);
}

const message = Buffer.from(CLAUDE_MSG, 'base64').toString('utf8');
const childEnv = {
  ...process.env,
  ...loadClaudeEnv(),
  ANTHROPIC_DISABLE_PREFLIGHT: '1',
  CLAUDE_CODE_TRUST_ALL: 'true',
  CLAUDE_CODE_SKIP_ONBOARDING: 'true',
  CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: '1',
};

try {
  fs.mkdirSync(path.dirname(LOG_FILE), { recursive: true });
} catch (_) {}

const args = ['--dangerously-skip-permissions', '--continue', '--print'];
const child = spawn('claude', args, {
  stdio: ['pipe', 'pipe', 'pipe'],
  shell: false,
  env: childEnv,
});

const timeout = setTimeout(() => {
  console.error('[TIMEOUT] Claude process killed after 60 minutes');
  child.kill('SIGTERM');
  setTimeout(() => child.kill('SIGKILL'), 5000);
}, TIMEOUT_MS);

function append(data) {
  try {
    fs.appendFileSync(LOG_FILE, data.toString());
  } catch (_) {}
}

child.stdout.on('data', append);
child.stderr.on('data', append);

child.on('close', (code) => {
  clearTimeout(timeout);
  process.exit(code);
});

child.on('error', (err) => {
  clearTimeout(timeout);
  console.error('[ERROR]', err.message);
  process.exit(1);
});

child.stdin.end(message);
