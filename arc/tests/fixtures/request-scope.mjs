import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';

const source = await readFile(process.argv[2], 'utf8');
const {createRequestScope} = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
};
const scope = createRequestScope();
const state = {data: null, error: null, pending: false};
async function load(result) {
  const ticket = scope.begin();
  state.pending = true;
  try {
    // Intentionally ignores abort: e.g. a parsed/cached response or an adapter
    // that cannot cancel. The publication guard must still work.
    const data = await result.promise;
    if (ticket.isCurrent()) state.data = data;
  } catch (error) {
    if (ticket.isCurrent()) state.error = error.message;
  } finally {
    if (ticket.isCurrent()) state.pending = false;
  }
}

const old = deferred(), newer = deferred();
const oldLoad = load(old), newLoad = load(newer);
old.reject(new Error('old anonymous request failed'));
await oldLoad;
assert.deepEqual(state, {data: null, error: null, pending: true}, 'stale catch/finally must not clear the latest pending state');
newer.resolve('account B'); await newLoad;
assert.equal(state.data, 'account B');

const slow = deferred(), fast = deferred();
const slowLoad = load(slow), fastLoad = load(fast);
fast.resolve('latest'); await fastLoad;
slow.resolve('obsolete'); await slowLoad;
assert.equal(state.data, 'latest', 'late success must not overwrite a newer result');

for (const outcome of ['success', 'failure']) {
  const pending = deferred();
  const running = load(pending);
  scope.cancel(); // logout/unmount may have no next request
  state.data = null; state.error = null; state.pending = false;
  if (outcome === 'success') pending.resolve('signed out user');
  else pending.reject(new Error('stale error'));
  await running;
  assert.deepEqual(state, {data: null, error: null, pending: false});
}

const first = scope.begin(), next = scope.begin();
assert.equal(first.signal.aborted, true);
assert.equal(first.isCurrent(), false);
assert.equal(next.isCurrent(), true);
const independent = createRequestScope().begin();
scope.cancel(); scope.cancel();
assert.equal(next.signal.aborted, true);
assert.equal(next.isCurrent(), false);
assert.equal(independent.isCurrent(), true, 'independent reads must not cancel each other');
assert.equal(scope.begin().isCurrent(), true, 'cleanup must allow a subsequent effect setup');

// Publish invalidation before invoking synchronous abort listeners.
const reentrant = createRequestScope();
const prior = reentrant.begin();
let nested;
prior.signal.addEventListener('abort', () => { nested = reentrant.begin(); });
const superseded = reentrant.begin();
assert.equal(superseded.isCurrent(), false);
assert.equal(nested.isCurrent(), true);
console.log('request scope: stale success/error/finally, cancellation, isolation and reentry passed');
