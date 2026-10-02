import {createContext, useContext, useEffect, useMemo, useState} from 'react';
import {requestJson} from './shared/request.js';

const SessionContext = createContext(null);

export function SessionProvider({children}) {
  const [account, setAccount] = useState(() => {
    try { return JSON.parse(localStorage.getItem('arcSession')) || null; } catch { return null; }
  });
  const value = useMemo(() => ({
    account,
    signIn(record) {
      localStorage.setItem('arcSession', JSON.stringify(record));
      setAccount(record);
    },
    async signOut() {
      try {
        if (account?.sessionId) {
          await requestJson('/api/session', {method: 'DELETE',
            headers: {'x-session-id': account.sessionId}});
        }
      } catch { /* Clear the local session regardless. */ }
      localStorage.removeItem('arcSession');
      setAccount(null);
    }
  }), [account]);

  // A stale or invalidated session must not survive a reload or direct entry.
  useEffect(() => {
    if (!account?.sessionId) return;
    let stale = false;
    requestJson('/api/session', {headers: {'x-session-id': account.sessionId}})
      .catch(() => { if (!stale) { localStorage.removeItem('arcSession'); setAccount(null); } });
    return () => { stale = true; };
  }, []);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession() {
  return useContext(SessionContext);
}
