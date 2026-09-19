'use strict';
// Optional domain-neutral JSON persistence. Call update with a synchronous function.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const directory = path.join(__dirname, '..', 'data');

function fileFor(name) {
  if (!/^[A-Za-z0-9_-]+$/.test(name)) throw new Error('invalid store name');
  return path.join(directory, name + '.json');
}

function read(name, fallback = {}) {
  try { return JSON.parse(fs.readFileSync(fileFor(name), 'utf8')); }
  catch (error) {
    if (error.code === 'ENOENT') return structuredClone(fallback);
    throw error;
  }
}

function write(name, value) {
  fs.mkdirSync(directory, {recursive: true});
  const target = fileFor(name);
  const temporary = target + '.' + process.pid + '.' + crypto.randomBytes(6).toString('hex') + '.tmp';
  try {
    fs.writeFileSync(temporary, JSON.stringify(value));
    fs.renameSync(temporary, target);
  } finally {
    if (fs.existsSync(temporary)) fs.unlinkSync(temporary);
  }
  return value;
}

function update(name, fallback, change) {
  const current = read(name, fallback);
  const next = change(current);
  if (next && typeof next.then === 'function') throw new Error('update callback must be synchronous');
  return write(name, next === undefined ? current : next);
}

module.exports = {read, write, update};
