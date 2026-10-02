import {useEffect, useState} from 'react';
import {Link, useLocation, useParams} from 'react-router';
import {requestJson} from '../shared/request.js';
import {useSession} from '../session.jsx';

export default function TeamPage() {
  const {identifier, team: teamName} = useParams();
  const {account} = useSession();
  const location = useLocation();
  const tab = location.pathname.endsWith('/settings') ? 'settings' : 'members';
  const [org, setOrg] = useState(null);
  const [team, setTeam] = useState(null);
  const [teams, setTeams] = useState([]);
  const [missing, setMissing] = useState(false);
  const [parentId, setParentId] = useState('');
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);
  const [pending, setPending] = useState(false);
  const [adding, setAdding] = useState(false);
  const [newMember, setNewMember] = useState('');
  const [memberError, setMemberError] = useState('');
  const [memberPending, setMemberPending] = useState(false);

  useEffect(() => {
    let stale = false;
    setMissing(false);
    const base = '/api/organizations/' + encodeURIComponent(identifier);
    requestJson(base).then(record => { if (!stale) setOrg(record); })
      .catch(() => { if (!stale) setMissing(true); });
    requestJson(base + '/teams').then(items => { if (!stale) setTeams(items); })
      .catch(() => {});
    requestJson(base + '/teams/' + encodeURIComponent(teamName))
      .then(record => {
        if (stale) return;
        setTeam(record);
        setParentId(record.parent_id || '');
      })
      .catch(() => { if (!stale) setMissing(true); });
    return () => { stale = true; };
  }, [identifier, teamName]);

  if (missing) {
    return <main style={{padding: '2rem'}}>
      <h1>Team not found</h1>
      <p><Link to={'/orgs/' + encodeURIComponent(identifier) + '/teams'}>Back to teams</Link></p>
    </main>;
  }
  if (!org || !team) return <main style={{padding: '2rem'}}><p>Loading…</p></main>;

  const base = '/orgs/' + encodeURIComponent(identifier) + '/teams/' + encodeURIComponent(team.name);
  const descendants = new Set([team.id]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const t of teams) {
      if (t.parent_id && descendants.has(t.parent_id) && !descendants.has(t.id)) {
        descendants.add(t.id);
        grew = true;
      }
    }
  }
  const parentChoices = teams.filter(t => t.id !== team.id);

  async function refreshTeam() {
    const record = await requestJson('/api/organizations/' + encodeURIComponent(identifier) +
      '/teams/' + encodeURIComponent(teamName));
    setTeam(record);
  }

  async function addMember(event) {
    event.preventDefault();
    setMemberPending(true);
    setMemberError('');
    try {
      await requestJson('/api/organizations/' + encodeURIComponent(identifier) +
        '/teams/' + encodeURIComponent(team.name) + '/members', {
        method: 'POST',
        headers: {'x-session-id': account?.sessionId},
        body: {username: newMember}
      });
      await refreshTeam();
      setAdding(false);
      setNewMember('');
    } catch (err) {
      setMemberError((err.body && err.body.errors && err.body.errors.username) ||
        err.message || 'Could not add the member');
    } finally {
      setMemberPending(false);
    }
  }

  async function removeMember(username) {
    setMemberPending(true);
    setMemberError('');
    try {
      await requestJson('/api/organizations/' + encodeURIComponent(identifier) +
        '/teams/' + encodeURIComponent(team.name) + '/members/' + encodeURIComponent(username), {
        method: 'DELETE',
        headers: {'x-session-id': account?.sessionId}
      });
      await refreshTeam();
    } catch (err) {
      setMemberError(err.message || 'Could not remove the member');
    } finally {
      setMemberPending(false);
    }
  }

  async function saveParent(event) {
    event.preventDefault();
    setPending(true);
    setError('');
    setSaved(false);
    try {
      const record = await requestJson('/api/organizations/' + encodeURIComponent(identifier) +
        '/teams/' + encodeURIComponent(team.name), {
        method: 'PATCH',
        headers: {'x-session-id': account?.sessionId},
        body: {parent_id: parentId || null}
      });
      setTeam({...team, parent_id: record.parent_id});
      setSaved(true);
    } catch (err) {
      setParentId(team.parent_id || '');
      setError(err.message || 'Could not update the parent team');
    } finally {
      setPending(false);
    }
  }

  const parentName = team.parent_id
    ? ((teams.find(t => t.id === team.parent_id) || {}).name || null)
    : null;

  return <main style={{padding: '2rem'}}>
    <h1>{org.display_name}/{team.name}</h1>
    {team.description ? <p>{team.description}</p> : null}
    <p><Link to={'/orgs/' + encodeURIComponent(identifier) + '/teams'}>Back to teams</Link></p>
    <nav style={{display: 'flex', gap: '1rem', borderBottom: '1px solid #ddd', paddingBottom: '0.5rem'}}>
      <Link to={base}>Members</Link>
      <Link to={base + '/settings'}>Settings</Link>
    </nav>
    {tab === 'members' ? (
      <div style={{marginTop: '1rem'}}>
        {adding ? (
          <form onSubmit={addMember} noValidate style={{marginBottom: '1rem', maxWidth: 360}}>
            <label style={{display: 'block', marginBottom: '0.5rem'}}>
              Username
              <input style={{display: 'block', width: '100%'}} value={newMember}
                onChange={e => setNewMember(e.target.value)} />
            </label>
            {memberError ? <p role="alert" style={{color: 'red'}}>{memberError}</p> : null}
            <button type="submit" disabled={memberPending}>Add member</button>
          </form>
        ) : (
          <button type="button" onClick={() => { setAdding(true); setMemberError(''); }}>Add member</button>
        )}
        <ul style={{listStyle: 'none', padding: 0}}>
          {team.members.map(member => (
            <li key={member.username} style={{padding: '0.5rem 0', borderBottom: '1px solid #eee'}}>
              {member.username}
              <button type="button" style={{marginLeft: '0.75rem'}} disabled={memberPending}
                onClick={() => removeMember(member.username)}>Remove {member.username}</button>
            </li>
          ))}
          {team.members.length === 0 ? <li>No members</li> : null}
        </ul>
        {!adding && memberError ? <p role="alert" style={{color: 'red'}}>{memberError}</p> : null}
      </div>
    ) : (
      <form onSubmit={saveParent} noValidate style={{marginTop: '1rem', maxWidth: 360}}>
        <p>Parent team: {parentName || 'none'}</p>
        <label htmlFor="parent-team-select" style={{display: 'block', marginBottom: '0.5rem'}}>
          Parent team
        </label>
        <select id="parent-team-select" value={parentId} onChange={e => { setParentId(e.target.value); setSaved(false); }}>
          <option value="">No parent</option>
          {parentChoices.map(t => (
            <option key={t.id} value={t.id}>{t.name}</option>
          ))}
        </select>
        {error ? <p role="alert" style={{color: 'red'}}>{error}</p> : null}
        {saved ? <p role="status">Parent team updated</p> : null}
        <button type="submit" disabled={pending}>Save</button>
      </form>
    )}
  </main>;
}
