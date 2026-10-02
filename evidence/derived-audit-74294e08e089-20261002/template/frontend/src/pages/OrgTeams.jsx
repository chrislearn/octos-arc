import {useEffect, useState} from 'react';
import {Link, useParams} from 'react-router';
import {requestJson} from '../shared/request.js';
import {useSession} from '../session.jsx';

export default function OrgTeams() {
  const {identifier} = useParams();
  const {account} = useSession();
  const [org, setOrg] = useState(null);
  const [teams, setTeams] = useState(null);

  useEffect(() => {
    let stale = false;
    const headers = account?.sessionId ? {'x-session-id': account.sessionId} : {};
    requestJson('/api/organizations/' + encodeURIComponent(identifier), {headers})
      .then(record => { if (!stale) setOrg(record); })
      .catch(() => { if (!stale) setOrg({identifier, display_name: identifier, is_owner: false}); });
    requestJson('/api/organizations/' + encodeURIComponent(identifier) + '/teams')
      .then(items => { if (!stale) setTeams(items); })
      .catch(() => { if (!stale) setTeams([]); });
    return () => { stale = true; };
  }, [identifier]);

  const byId = new Map((teams || []).map(t => [t.id, t]));
  return <main style={{padding: '2rem'}}>
    <h1>{org ? org.display_name : identifier} teams</h1>
    <p><Link to={'/orgs/' + encodeURIComponent(identifier)}>Back to organization</Link></p>
    {org && org.is_owner
      ? <p><Link to={'/orgs/' + encodeURIComponent(identifier) + '/teams/new'}>New team</Link></p>
      : null}
    {teams === null ? <p>Loading…</p> : (
      <ul style={{listStyle: 'none', padding: 0}}>
        {teams.map(team => (
          <li key={team.id} style={{padding: '0.5rem 0', borderBottom: '1px solid #eee'}}>
            <Link to={'/orgs/' + encodeURIComponent(identifier) + '/teams/' + encodeURIComponent(team.name)}>{team.name}</Link>
            {team.parent_id && byId.get(team.parent_id)
              ? <span style={{color: '#666'}}> — child of {byId.get(team.parent_id).name}</span>
              : null}
          </li>
        ))}
        {teams.length === 0 ? <li>No teams</li> : null}
      </ul>
    )}
  </main>;
}
