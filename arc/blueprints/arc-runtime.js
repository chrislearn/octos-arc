'use strict';
// Task-neutral harness runtime for the generic entry: a route registry and
// opt-in test hooks. Do not edit; register application routes in backend/routes/*.js.
const fs = require('fs');
const path = require('path');

const BACKEND = path.resolve(__dirname, '..');
const METHODS = ['get', 'post', 'put', 'patch', 'delete', 'all'];
const routes = [];
const conflicts = [];

// Express 5 syntax: ":id" parameters, "*name" wildcards, "{...}" optional groups.
function segments(route) {
  return route.split('/').filter(Boolean).map(piece =>
    piece.startsWith(':') ? ':' : piece.startsWith('*') ? '*' : piece.includes('{') ? '?' : piece);
}

function canonical(route) {
  return '/' + segments(route).join('/');
}

// A literal path is unreachable when an earlier route of the same method
// already matches every request for it.
function covers(earlier, later) {
  const a = segments(earlier), b = segments(later);
  if (a.includes('?') || b.includes('?')) return false;
  for (let i = 0; i < a.length; i += 1) {
    if (a[i] === '*') return b.length > i;
    if (i >= b.length || (a[i] !== ':' && a[i] !== b[i]) || (a[i] === ':' && b[i] === '*')) return false;
  }
  return a.length === b.length;
}

function callerSite() {
  const frames = (new Error().stack || '').split('\n').slice(1);
  let fallback = null;
  for (const frame of frames) {
    const match = frame.match(/\(?((?:[A-Za-z]:)?[^\s()]+?):(\d+):\d+\)?\s*$/);
    if (!match || match[1] === __filename || match[1].includes(`${path.sep}node_modules${path.sep}`)) continue;
    const file = path.resolve(match[1]);
    if (!file.startsWith(BACKEND + path.sep)) continue;
    const site = {file: 'backend/' + path.relative(BACKEND, file).split(path.sep).join('/'), line: Number(match[2])};
    if (site.file.startsWith('backend/routes/')) return site;
    fallback = fallback || site;
  }
  return fallback || {file: '?', line: 0};
}

function record(method, route) {
  const site = callerSite();
  const verb = method.toUpperCase();
  const entry = {method: verb, path: route, ...site};
  for (const prior of routes) {
    if (prior.method !== verb && prior.method !== 'ALL' && verb !== 'ALL') continue;
    const where = `${site.file}:${site.line}`;
    const owner = `${prior.file}:${prior.line}`;
    if (canonical(prior.path) === canonical(route)) {
      conflicts.push({kind: 'duplicate', method: verb, path: route, file: site.file, line: site.line,
        owner_file: prior.file, owner_line: prior.line,
        message: `${verb} ${route} (${where}) is already registered as ${prior.method} ${prior.path} at ${owner}; ` +
          `Express only runs the first handler. Keep one handler and change it in ${prior.file}.`});
      break;
    }
    if (covers(prior.path, route)) {
      conflicts.push({kind: 'shadowed', method: verb, path: route, file: site.file, line: site.line,
        owner_file: prior.file, owner_line: prior.line,
        message: `${verb} ${route} (${where}) never runs: ${prior.method} ${prior.path} at ${owner} matches it first; ` +
          `register it before that route.`});
      break;
    }
  }
  routes.push(entry);
}

function trackRoutes(app) {
  for (const method of METHODS) {
    const original = app[method];
    if (typeof original !== 'function') continue;
    app[method] = function (route, ...handlers) {
      // app.get('setting') is Express's settings getter, not a route.
      if (typeof route === 'string' && handlers.length) record(method, route);
      return original.call(this, route, ...handlers);
    };
  }
  return app;
}

function routeReport() {
  return {routes: routes.map(route => ({...route})), conflicts: conflicts.map(conflict => ({...conflict}))};
}

// Harness-only endpoints: never mounted unless ARC_TEST_HOOKS=1 (the grader does not set it).
function mountTestHooks(app) {
  if (process.env.ARC_TEST_HOOKS !== '1') return;
  app.post('/__arc/reset', (req, res) => {
    require('./store').reset();
    res.status(204).end();
  });
  app.get('/__arc/routes', (req, res) => res.json(routeReport()));
}

// ARC_ROUTE_DUMP=<file>: write the route table and exit before listening.
// Otherwise conflicts are warnings; they never stop the server.
function finishRegistration() {
  const target = process.env.ARC_ROUTE_DUMP;
  if (target) {
    fs.writeFileSync(target, JSON.stringify(routeReport()));
    process.exit(0);
  }
  for (const conflict of conflicts) console.warn(`[routes] ${conflict.message}`);
}

module.exports = {trackRoutes, routeReport, mountTestHooks, finishRegistration};
