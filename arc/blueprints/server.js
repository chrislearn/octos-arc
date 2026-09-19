'use strict';
// Generic web entry (Express). Put application routes in backend/routes/*.js.
const express = require('express');
const http = require('http');
const fs = require('fs');
const path = require('path');
const app = express();
const dist = path.resolve(__dirname, '../frontend/dist');
const routes = path.join(__dirname, 'routes');

app.disable('x-powered-by');
app.use(express.json({limit: '1mb'}));
app.use(express.urlencoded({extended: false}));
if (fs.existsSync(routes)) {
  for (const name of fs.readdirSync(routes).filter(n => n.endsWith('.js')).sort()) {
    const register = require(path.join(routes, name));
    if (typeof register !== 'function') throw new TypeError(`${name} must export a route registration function`);
    register(app);
  }
}
app.use('/api', (req, res) => res.status(404).json({error: 'not found'}));
app.use(express.static(dist, {extensions: ['html']}));
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
