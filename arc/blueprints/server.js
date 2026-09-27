'use strict';
// Generic web entry (Express). Put application routes in backend/routes/*.js.
const express = require('express');
const http = require('http');
const fs = require('fs');
const path = require('path');
const arc = require('./lib/arc');
const app = express();
const dist = path.resolve(__dirname, '../frontend/dist');
const routes = path.join(__dirname, 'routes');
const frontendManifest = path.resolve(__dirname, '../frontend/package.json');
const spa = fs.existsSync(frontendManifest) && JSON.parse(fs.readFileSync(frontendManifest, 'utf8')).arc?.spa === true;
// Declared business document routes can legitimately end in .js/.png/etc.
// A missing static asset must still return 404 instead of the application shell.
let documentRoutes = [];
const designRoutes = path.resolve(__dirname, '../design/routes.json');
if (fs.existsSync(designRoutes)) {
  documentRoutes = (JSON.parse(fs.readFileSync(designRoutes, 'utf8')).pages || []).map(page => page.path);
}
function declaredDocument(url) {
  const actual = url.split('/').filter(Boolean);
  return documentRoutes.some(route => {
    if (typeof route !== 'string') return false;
    const parts = route.split('/').filter(Boolean);
    return parts.every((part, i) => part === '*' || (actual[i] !== undefined &&
      (part.startsWith(':') || part === actual[i]))) &&
      (parts.length === actual.length || parts.at(-1) === '*');
  });
}

app.disable('x-powered-by');
app.use(express.json({limit: '1mb'}));
app.use(express.urlencoded({extended: false}));
arc.mountTestHooks(app);
arc.trackRoutes(app);
if (fs.existsSync(routes)) {
  for (const name of fs.readdirSync(routes).filter(n => n.endsWith('.js')).sort()) {
    const register = require(path.join(routes, name));
    if (typeof register !== 'function') throw new TypeError(`${name} must export a route registration function`);
    register(app);
  }
}
arc.finishRegistration();
app.use('/api', (req, res) => res.status(404).json({error: 'not found'}));
// Existing assets and multi-page documents take precedence over SPA routing.
app.use(express.static(dist, {extensions: ['html']}));
if (spa) app.use((req, res, next) => {
  if (!['GET', 'HEAD'].includes(req.method) || req.path.startsWith('/api/') || req.path === '/api' ||
      !/text\/html/i.test(req.get('accept') || '') ||
      /^\/(?:assets|static)\//.test(req.path) ||
      (/\.(?:m?js|cjs|css|map|woff2?|ttf|ico|png|jpe?g|gif|webp|svg)$/i.test(req.path) &&
       !declaredDocument(req.path))) return next();
  const html = path.resolve(dist, '.' + req.path + '.html');
  const nested = path.resolve(dist, '.' + req.path, 'index.html');
  if ((html.startsWith(dist + path.sep) && fs.existsSync(html)) ||
      (nested.startsWith(dist + path.sep) && fs.existsSync(nested))) return next();
  fs.readFile(path.join(dist, 'index.html'), (error, body) => {
    if (error) return next(error);
    res.type('html').send(body);
  });
});
app.use((req, res) => res.status(404).send('not found'));
app.use((error, req, res, next) => {
  if (res.headersSent) return next(error);
  const status = error.status >= 400 && error.status < 500 ? error.status : 500;
  if (status === 500) console.error(error);
  res.status(status).json({error: status === 500 ? 'internal error' : error.message});
});

const ports = [Number(process.env.PORT || __ARC_DEFAULT_PORT__)];
if (process.env.ARC_EXTRA_PORTS !== '0') ports.push(...__ARC_EXTRA_PORTS__);
for (const port of new Set(ports)) http.createServer(app).listen(port);
