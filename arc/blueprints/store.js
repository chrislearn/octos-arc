'use strict';
// Optional domain-neutral JSON persistence. Call update with a synchronous function.
// ARC_DATA_DIR relocates the data (the harness keeps test data out of the worktree).
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const directory = process.env.ARC_DATA_DIR ? path.resolve(process.env.ARC_DATA_DIR) : path.join(__dirname, '..', 'data');
const migrated = new Map();
const resetHooks = [];

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

// Opt-in migrations for object stores. The ledger and data share ONE atomic
// write. Initial/fallback data alone cannot evolve an already persisted store.
// Single Node process only: rename is not a multi-process or multi-store lock.
function migrate(name, fallback, migrations) {
  const key = '__arcMigrations';
  if (!Array.isArray(migrations)) throw new Error('migrations must be an array');
  const ids = new Set();
  for (const migration of migrations) {
    if (!migration || typeof migration.id !== 'string' || !migration.id.trim()
        || typeof migration.up !== 'function' || migration.up.constructor.name === 'AsyncFunction'
        || ids.has(migration.id)) {
      throw new Error('migration requires a unique nonempty id and synchronous up function');
    }
    ids.add(migration.id);
  }
  migrated.set(name, {fallback, migrations});
  const data = read(name, fallback);
  if (!data || Array.isArray(data) || typeof data !== 'object') throw new Error('migration store must be an object');
  const ledger = data[key] === undefined ? [] : data[key];
  if (!Array.isArray(ledger) || ledger.some(id => typeof id !== 'string')
      || new Set(ledger).size !== ledger.length) throw new Error('invalid migration ledger');
  const applied = new Set(ledger);
  let changed = false;
  for (const {id, up} of migrations) {
    if (applied.has(id)) continue;
    const result = up(data);
    if (result && typeof result.then === 'function') Promise.resolve(result).catch(() => {});
    if (result !== undefined) throw new Error('migration must synchronously mutate data and return undefined');
    applied.add(id);
    changed = true;
  }
  if (changed) {
    data[key] = [...applied];
    write(name, data);
  }
  return data;
}

// Keep in-memory state (undo stacks, caches) consistent with a reset:
// onReset(() => stacks.clear()).
function onReset(hook) {
  if (typeof hook !== 'function') throw new TypeError('onReset requires a function');
  resetHooks.push(hook);
}

// Back to the seeds: drop every persisted store, replay registered migrations
// on their initial data, then run the reset hooks.
function reset() {
  let names = [];
  try { names = fs.readdirSync(directory); }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
  for (const name of names) {
    if (name.endsWith('.json') || name.endsWith('.tmp')) fs.rmSync(path.join(directory, name), {force: true});
  }
  for (const [name, {fallback, migrations}] of [...migrated]) migrate(name, fallback, migrations);
  for (const hook of resetHooks) hook();
}

module.exports = {read, write, update, migrate, onReset, reset};
