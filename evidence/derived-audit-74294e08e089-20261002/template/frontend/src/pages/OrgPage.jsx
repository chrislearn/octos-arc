import {useEffect, useMemo, useState} from 'react';
import {Link, useLocation, useParams} from 'react-router';
import {requestJson} from '../shared/request.js';
import {useSession} from '../session.jsx';

export default function OrgPage() {
  const {identifier} = useParams();
  const {account} = useSession();
  const [org, setOrg] = useState(null);
  const [repos, setRepos] = useState([]);
  const [missing, setMissing] = useState(false);
  const [filter, setFilter] = useState('');
  const [visibility, setVisibility] = useState('all');
  const [members, setMembers] = useState([]);
  const [adding, setAdding] = useState(false);
  const [newMember, setNewMember] = useState('');
  const [newRole, setNewRole] = useState('Member');
  const [memberError, setMemberError] = useState('');
  const [memberPending, setMemberPending] = useState(false);
  const location = useLocation();
  const tab = location.pathname.endsWith('/people') ? 'people'
    : location.pathname.endsWith('/teams') ? 'teams' : 'repositories';

  useEffect(() => {
    let stale = false;
    setOrg(null);
    setMissing(false);
    setFilter('');
    setVisibility('all');
    requestJson('/api/organizations/' + encodeURIComponent(identifier))
      .then(record => { if (!stale) setOrg(record); })
      .catch(() => { if (!stale) setMissing(true); });
    requestJson('/api/organizations/' + encodeURIComponent(identifier) + '/repositories')
      .then(items => { if (!stale) setRepos(items); })
      .catch(() => { if (!stale) setRepos([]); });
    requestJson('/api/organizations/' + encodeURIComponent(identifier) + '/members')
      .then(items => { if (!stale) setMembers(items); })
      .catch(() => { if (!stale) setMembers([]); });
    return () => { stale = true; };
  }, [identifier]);

  async function addMember(event) {
    event.preventDefault();
    setMemberPending(true);
    setMemberError('');
    try {
      await requestJson('/api/organizations/' + encodeURIComponent(identifier) + '/members', {
        method: 'POST',
        headers: {'x-session-id': account?.sessionId},
        body: {username: newMember, role: newRole}
      });
      const items = await requestJson('/api/organizations/' + encodeURIComponent(identifier) + '/members');
      setMembers(items);
      setAdding(false);
      setNewMember('');
      setNewRole('Member');
    } catch (err) {
      setMemberError((err.body && err.body.errors && err.body.errors.username) ||
        err.message || 'Could not add the member');
    } finally {
      setMemberPending(false);
    }
  }

  const visible = useMemo(() => repos.filter(r =>
    (!filter || r.name.toLowerCase().includes(filter.trim().toLowerCase())) &&
    (visibility === 'all' || r.visibility === visibility)
  ), [repos, filter, visibility]);

  if (missing) {
    return <main style={{padding: '2rem'}}>
      <h1>Organization not found</h1>
      <p>This organization does not exist.</p>
    </main>;
  }
  if (!org) return <main style={{padding: '2rem'}}><p>Loading…</p></main>;
  return <main style={{padding: '2rem'}}>
    <h1>{org.display_name} ({org.identifier})</h1>
    <nav style={{display: 'flex', gap: '1rem', borderBottom: '1px solid #ddd', paddingBottom: '0.5rem'}}>
      <Link to={'/orgs/' + encodeURIComponent(identifier)}>Repositories</Link>
      <Link to={'/orgs/' + encodeURIComponent(identifier) + '/people'}>People</Link>
      <Link to={'/orgs/' + encodeURIComponent(identifier) + '/teams'}>Teams</Link>
    </nav>
    <div style={{display: 'flex', gap: '1rem', margin: '1rem 0', alignItems: 'center'}}>
      <label>
        Find a repository
        <input type="text" value={filter}
          onChange={event => setFilter(event.target.value)} />
      </label>
      <label>
        Visibility
        <select value={visibility} onChange={event => setVisibility(event.target.value)}>
          <option value="all">All</option>
          <option value="Public">Public</option>
          <option value="Private">Private</option>
        </select>
      </label>
    </div>
    {tab === 'people' ? (
      <div>
        {org.is_owner && !adding
          ? <button type="button" style={{marginBottom: '1rem'}}
              onClick={() => { setAdding(true); setMemberError(''); }}>Add member</button>
          : null}
        {org.is_owner && adding
          ? <form onSubmit={addMember} noValidate style={{marginBottom: '1rem', maxWidth: 360}}>
              <label style={{display: 'block', marginBottom: '0.5rem'}}>
                Username or email
                <input style={{display: 'block', width: '100%'}} value={newMember}
                  onChange={e => setNewMember(e.target.value)} />
              </label>
              <label style={{display: 'block', marginBottom: '0.5rem'}}>
                Role
                <select value={newRole} onChange={e => setNewRole(e.target.value)}>
                  <option value="Member">Member</option>
                  <option value="Owner">Owner</option>
                </select>
              </label>
              {memberError ? <p role="alert" style={{color: 'red'}}>{memberError}</p> : null}
              <button type="submit" disabled={memberPending}>Add member</button>
            </form>
          : null}
        <ul style={{listStyle: 'none', padding: 0}}>
        {members.map(member => (
          <li key={member.username} style={{padding: '0.75rem 0', borderBottom: '1px solid #eee'}}>
            <div>{member.username}</div>
            <div style={{color: '#666'}}>{member.role}</div>
          </li>
        ))}
        {members.length === 0 ? <li>No members</li> : null}
        </ul>
      </div>
    ) : <ul style={{listStyle: 'none', padding: 0}}>
      {visible.map(repo => (
        <li key={repo.name} style={{padding: '0.75rem 0', borderBottom: '1px solid #eee'}}>
          <div>
            <Link to={'/repos/' + encodeURIComponent(identifier) + '/' + encodeURIComponent(repo.name)}>{repo.name}</Link>
          </div>
          <div style={{color: '#666'}}>{repo.visibility}</div>
          {repo.description ? <div>{repo.description}</div> : null}
          {repo.updated_at ? <div style={{color: '#999'}}>Updated {repo.updated_at.slice(0, 10)}</div> : null}
        </li>
      ))}
      {visible.length === 0 ? <li>No results</li> : null}
    </ul>}
  </main>;
}
