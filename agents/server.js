const http = require('http');

const HOST = process.env.SERVER_HOST || process.env.HOST || '0.0.0.0';
const PORT = Number(process.env.SERVER_PORT || process.env.PORT || 8082);
const ASK_UPSTREAM_HOST = process.env.ASK_UPSTREAM_HOST || '127.0.0.1';
const ASK_UPSTREAM_PORT = Number(process.env.ASK_UPSTREAM_PORT || 8081);

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
    const chunks = [];
    req.on('data', (chunk) => {
      chunks.push(chunk);
      const total = chunks.reduce((sum, item) => sum + item.length, 0);
      if (total > 1024 * 1024) {
        reject(new Error('request body too large'));
        req.destroy();
      }
    });
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });
}

function forwardAsk(body, contentType) {
  return new Promise((resolve, reject) => {
    const req = http.request({
      hostname: ASK_UPSTREAM_HOST,
      port: ASK_UPSTREAM_PORT,
      path: '/ask',
      method: 'POST',
      headers: {
        'content-type': contentType || 'application/json',
        'content-length': body.length,
      },
      timeout: Number(process.env.ASK_FORWARD_TIMEOUT_MS || 125000),
    }, (resp) => {
      const chunks = [];
      resp.on('data', (chunk) => chunks.push(chunk));
      resp.on('end', () => {
        resolve({
          statusCode: resp.statusCode || 502,
          headers: resp.headers,
          body: Buffer.concat(chunks),
        });
      });
    });
    req.on('timeout', () => req.destroy(new Error('ask upstream timeout')));
    req.on('error', reject);
    req.end(body);
  });
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  if (req.method === 'GET' && (url.pathname === '/health' || url.pathname === '/ask/health')) {
    sendJson(res, 200, {
      ok: true,
      service: 'server',
      ask_upstream: `http://${ASK_UPSTREAM_HOST}:${ASK_UPSTREAM_PORT}/ask`,
    });
    return;
  }
  if (req.method === 'POST' && url.pathname === '/ask') {
    try {
      const body = await readBody(req);
      const upstream = await forwardAsk(body, req.headers['content-type']);
      res.writeHead(upstream.statusCode, {
        'content-type': upstream.headers['content-type'] || 'application/json; charset=utf-8',
        'content-length': upstream.body.length,
      });
      res.end(upstream.body);
    } catch (error) {
      sendJson(res, 502, { ok: false, error: error.message });
    }
    return;
  }
  sendJson(res, 404, { ok: false, error: 'not found' });
});

server.listen(PORT, HOST, () => {
  console.log(`[server] listening on ${HOST}:${PORT}, forwarding /ask to ${ASK_UPSTREAM_HOST}:${ASK_UPSTREAM_PORT}`);
});
