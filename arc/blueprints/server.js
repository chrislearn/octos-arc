'use strict';
// Generic web entry. Put application behavior in backend/routes/*.js.
const http = require('http');
const fs = require('fs');
const path = require('path');
const dist = path.resolve(__dirname, '../frontend/dist');
const routes = path.join(__dirname, 'routes');

function json(res, status, value) {
  res.writeHead(status, {'Content-Type': 'application/json; charset=utf-8'});
  res.end(JSON.stringify(value));
}

function readJson(req, limit = 1048576) {
  return new Promise((resolve, reject) => {
    let text = '';
    req.on('data', chunk => {
      text += chunk;
      if (text.length > limit) {
        const error = new Error('request body too large'); error.status = 413;
        reject(error); req.removeAllListeners('data'); req.resume();
      }
    });
    req.on('end', () => {
      try { resolve(text ? JSON.parse(text) : {}); }
      catch (error) { error.status = 400; reject(error); }
    });
    req.on('error', reject);
  });
}

async function handler(req, res) {
  try {
    const url = new URL(req.url, 'http://localhost');
    if (fs.existsSync(routes)) {
      for (const name of fs.readdirSync(routes).filter(n => n.endsWith('.js')).sort()) {
        const route = require(path.join(routes, name));
        const run = typeof route === 'function' ? route : route.handle;
        if (typeof run === 'function' && (await run(req, res, {url, json, readJson}) || res.headersSent)) return;
      }
    }
    if (url.pathname.startsWith('/api/')) return json(res, 404, {error: 'not found'});
    if (req.method !== 'GET' && req.method !== 'HEAD') return json(res, 405, {error: 'method not allowed'});
    let requested = decodeURIComponent(url.pathname);
    if (requested === '/') requested = '/index.html';
    else if (!path.extname(requested)) requested += '.html';
    const file = path.resolve(dist, '.' + requested);
    if (file !== dist && !file.startsWith(dist + path.sep)) return json(res, 403, {error: 'forbidden'});
    const type = {'.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json',
      '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.ico': 'image/x-icon'}[path.extname(file)] || 'application/octet-stream';
    fs.readFile(file, (error, bytes) => {
      if (error) return json(res, error.code === 'ENOENT' ? 404 : 500, {error: 'file unavailable'});
      res.writeHead(200, {'Content-Type': type + (type.startsWith('text/') || type === 'application/json' ? '; charset=utf-8' : '')});
      res.end(req.method === 'HEAD' ? undefined : bytes);
    });
  } catch (error) {
    if (!res.headersSent) json(res, error.status || 500, {error: error.status ? error.message : 'internal error'});
    else res.end();
  }
}

const ports = [Number(process.env.PORT || __ARC_DEFAULT_PORT__)];
if (process.env.ARC_EXTRA_PORTS !== '0') ports.push(...__ARC_EXTRA_PORTS__);
for (const port of new Set(ports)) http.createServer(handler).listen(port);
