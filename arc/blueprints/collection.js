'use strict';
// Optional record collection: domain fields and lifecycle rules belong to the task.
const {randomUUID} = require('crypto');
const store = require('./store');

function collection(name, {idKey = 'id', initial = [], migrations = [], normalize = item => item} = {}) {
  if (!Array.isArray(initial)) throw new TypeError('collection initial must be an array of records, not {items: [...]}');
  if (typeof normalize !== 'function') throw new TypeError('normalize must be a function');
  const fallback = {items: initial};
  if (migrations.length) store.migrate(name, fallback, migrations);
  const same = (item, id) => String(item[idKey]) === String(id);
  const shaped = item => {
    if (!item || typeof item !== 'object' || Array.isArray(item)) throw new TypeError('record must be an object');
    const result = normalize({...item});
    if (result && typeof result.then === 'function') {
      Promise.resolve(result).catch(() => {});
      throw new TypeError('normalize must return a record synchronously');
    }
    if (!result || typeof result !== 'object' || Array.isArray(result)) {
      throw new TypeError('normalize must return a record synchronously');
    }
    if (!Object.is(result[idKey], item[idKey])) throw new Error('normalize must preserve the record id');
    return result;
  };
  const itemsIn = data => {
    if (!Array.isArray(data.items)) throw new Error('collection data must contain items array');
    return data.items;
  };
  const all = () => {
    const data = store.read(name, fallback);
    return itemsIn(data).map(shaped);
  };
  const get = id => all().find(item => same(item, id)) || null;
  const list = predicate => predicate ? all().filter(predicate) : all();
  const create = fields => {
    const item = shaped({...fields, [idKey]: fields[idKey] ?? randomUUID()});
    store.update(name, fallback, data => {
      const items = itemsIn(data);
      if (items.some(other => same(other, item[idKey]))) throw new Error('duplicate id');
      items.push(item);
    });
    return item;
  };
  const patch = (id, fields) => {
    let changed = null;
    store.update(name, fallback, data => {
      const items = itemsIn(data);
      const index = items.findIndex(item => same(item, id));
      if (index >= 0) changed = items[index] = shaped({...items[index], ...fields, [idKey]: items[index][idKey]});
    });
    return changed;
  };
  const remove = id => {
    let removed = false;
    store.update(name, fallback, data => {
      const before = itemsIn(data).length;
      data.items = data.items.filter(item => !same(item, id));
      removed = data.items.length !== before;
    });
    return removed;
  };
  // One synchronous read-modify-write for commands affecting multiple records.
  // The caller defines every domain rule; this is not a cross-store transaction.
  const transact = change => {
    if (typeof change !== 'function') throw new TypeError('transact requires a function');
    let result;
    store.update(name, fallback, data => {
      data.items = itemsIn(data).map(shaped);
      result = change(data.items);
      if (result && typeof result.then === 'function') {
        Promise.resolve(result).catch(() => {});
        throw new Error('transact callback must be synchronous');
      }
      data.items = itemsIn(data).map(shaped);
      const ids = new Set(data.items.map(item => String(item[idKey])));
      if (ids.size !== data.items.length || data.items.some(item => item[idKey] == null)) {
        throw new Error('transaction records need unique ids');
      }
    });
    return result;
  };
  return {all, list, get, create, patch, remove, transact};
}

module.exports = {collection};
