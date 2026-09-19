'use strict';
// Optional record collection: domain fields and lifecycle rules belong to the task.
const {randomUUID} = require('crypto');
const store = require('./store');

function collection(name, {idKey = 'id', initial = []} = {}) {
  const fallback = {items: initial};
  const same = (item, id) => String(item[idKey]) === String(id);
  const all = () => {
    const data = store.read(name, fallback);
    if (!Array.isArray(data.items)) throw new Error('collection data must contain items array');
    return data.items;
  };
  const get = id => all().find(item => same(item, id)) || null;
  const list = predicate => predicate ? all().filter(predicate) : all();
  const create = fields => {
    const item = {...fields, [idKey]: fields[idKey] ?? randomUUID()};
    store.update(name, fallback, data => {
      if (!Array.isArray(data.items)) throw new Error('collection data must contain items array');
      if (data.items.some(other => same(other, item[idKey]))) throw new Error('duplicate id');
      data.items.push(item);
    });
    return item;
  };
  const patch = (id, fields) => {
    let changed = null;
    store.update(name, fallback, data => {
      if (!Array.isArray(data.items)) throw new Error('collection data must contain items array');
      const index = data.items.findIndex(item => same(item, id));
      if (index >= 0) changed = data.items[index] = {...data.items[index], ...fields, [idKey]: data.items[index][idKey]};
    });
    return changed;
  };
  const remove = id => {
    let removed = false;
    store.update(name, fallback, data => {
      if (!Array.isArray(data.items)) throw new Error('collection data must contain items array');
      const before = data.items.length;
      data.items = data.items.filter(item => !same(item, id));
      removed = data.items.length !== before;
    });
    return removed;
  };
  return {all, list, get, create, patch, remove};
}

module.exports = {collection};
