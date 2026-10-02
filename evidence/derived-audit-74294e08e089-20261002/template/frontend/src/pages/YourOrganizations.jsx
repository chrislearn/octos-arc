import {useEffect, useState} from 'react';
import {Link} from 'react-router';
import {requestJson} from '../shared/request.js';
import {useSession} from '../session.jsx';

export default function YourOrganizations() {
  const {account} = useSession();
  const [orgs, setOrgs] = useState(null);

  useEffect(() => {
    let stale = false;
    requestJson('/api/organizations', {
      headers: account?.sessionId ? {'x-session-id': account.sessionId} : {}
    })
      .then(items => { if (!stale) setOrgs(items); })
      .catch(() => { if (!stale) setOrgs([]); });
    return () => { stale = true; };
  }, [account?.sessionId]);

  return <main style={{padding: '2rem'}}>
    <h1>Your organizations</h1>
    <p><Link to="/organizations/new">New organization</Link></p>
    {orgs === null ? <p>Loading…</p> : (
      <ul style={{listStyle: 'none', padding: 0}}>
        {orgs.map(org => (
          <li key={org.identifier} style={{padding: '0.5rem 0', borderBottom: '1px solid #eee'}}>
            <Link to={'/orgs/' + encodeURIComponent(org.identifier)}>{org.display_name}</Link>
          </li>
        ))}
        {orgs.length === 0 ? <li>No organizations</li> : null}
      </ul>
    )}
  </main>;
}
