// Integration fixture only. Business apps choose their own auth/loading policy.
// A deferred adapter deliberately ignores abort, as already-parsed/cached work
// can do. Tests release or reject each read explicitly, without timed sleeps.
import {useCallback, useEffect, useRef, useState} from 'react';
import {Link, Route, Routes, useLocation} from 'react-router';
import {createRequestScope} from './shared/request-scope.js';

const fault = new URLSearchParams(location.search).get('fault');
const reads = [];
window.readHarness = {
  pending: () => reads.filter(read => !read.done).map(({id, owner}) => ({id, owner})),
  settle(id, value, failure = false) {
    const read = reads.find(read => read.id === id);
    if (!read || read.done) throw new Error(`No pending read ${id}`);
    read.done = true;
    if (failure) read.reject(Object.assign(new Error(value.message), {status: value.status}));
    else read.resolve(value);
  },
};
function deferredRead(owner) {
  return new Promise((resolve, reject) => reads.push({id: reads.length + 1, owner, resolve, reject, done: false}));
}

function ResourcePage() {
  const [scope] = useState(createRequestScope);
  const [items, setItems] = useState(null);
  useEffect(() => {
    const ticket = scope.begin();
    deferredRead('documents').then(value => {
      if (ticket.isCurrent()) setItems(value);
    });
    return () => scope.cancel();
  }, [scope]);
  return <section>
    <nav aria-label="Documents"><Link to="/documents">List</Link><Link to="/settings">Settings</Link></nav>
    <h1>Documents</h1>
    {items === null ? <p role="status">Loading documents</p> : <p>{items.join(', ')}</p>}
  </section>;
}

export default function App() {
  const [scope] = useState(createRequestScope);
  const [owner, setOwner] = useState('alpha');
  const ownerRef = useRef(owner);
  const [user, setUser] = useState(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);
  const location = useLocation();

  const refresh = useCallback(async () => {
    if (!owner) return;
    const ticket = scope.begin();
    const current = () => fault === 'stale' || (ticket.isCurrent() && ownerRef.current === owner);
    setPending(true); setError(null);
    if (fault === 'blank-refresh') setUser(null);
    try {
      const result = await deferredRead(owner);
      if (current()) setUser(result);
    } catch (failure) {
      if (current()) {
        setError(failure.message);
        if (failure.status === 401) setUser(null);
      }
    } finally {
      if (current()) setPending(false);
    }
  }, [owner, scope]);

  useEffect(() => {
    refresh();
    return () => scope.cancel();
  }, [refresh, location.pathname, scope]);

  function changeOwner(next) {
    scope.cancel();
    ownerRef.current = next;
    setUser(null); setError(null); setPending(false); setOwner(next);
  }

  return <>
    <header>
      <nav aria-label="Primary"><Link to="/">Home</Link><Link to="/documents">Documents</Link></nav>
      <button onClick={() => changeOwner('alpha')}>Use alpha</button>
      <button onClick={() => changeOwner('beta')}>Use beta</button>
      <button onClick={() => changeOwner(null)}>Sign out</button>
      <button onClick={refresh}>Refresh identity</button>
      <output aria-label="Identity">{user?.name || 'Anonymous'}</output>
      <output aria-label="Refresh pending">{String(pending)}</output>
      {error && <p role="alert">{error}</p>}
    </header>
    {user ? <main>
      <nav aria-label="Account"><Link to="/settings">Account settings</Link></nav>
      <Routes>
        <Route path="/" element={<h1>Home</h1>} />
        <Route path="/settings" element={<section><h1>Settings</h1><label>Draft<input /></label></section>} />
        <Route path="/documents" element={<ResourcePage />} />
      </Routes>
    </main> : <main><p>{pending ? 'Verifying identity' : 'Sign in required'}</p></main>}
  </>;
}
