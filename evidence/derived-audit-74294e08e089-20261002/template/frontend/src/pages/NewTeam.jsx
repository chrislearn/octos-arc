import {useEffect, useState} from 'react';
import {Link, useNavigate, useParams} from 'react-router';
import {requestJson} from '../shared/request.js';
import {useSession} from '../session.jsx';

const fieldStyle = {display: 'block', width: '100%', marginBottom: '0.25rem'};

export default function NewTeam() {
  const {identifier} = useParams();
  const {account} = useSession();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [parentId, setParentId] = useState('');
  const [teams, setTeams] = useState([]);
  const [errors, setErrors] = useState({});
  const [pending, setPending] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    let stale = false;
    requestJson('/api/organizations/' + encodeURIComponent(identifier) + '/teams')
      .then(items => { if (!stale) setTeams(items); })
      .catch(() => {});
    return () => { stale = true; };
  }, [identifier]);

  if (!account) {
    return <main style={{padding: '2rem'}}>
      <h1>New team</h1>
      <p><Link to="/signin">Sign in</Link></p>
    </main>;
  }

  async function submit(event) {
    event.preventDefault();
    setPending(true);
    try {
      await requestJson('/api/organizations/' + encodeURIComponent(identifier) + '/teams', {
        method: 'POST',
        headers: {'x-session-id': account.sessionId},
        body: {name, description, parent_id: parentId || null}
      });
      navigate('/orgs/' + encodeURIComponent(identifier) + '/teams/' +
        encodeURIComponent(name.trim()));
    } catch (err) {
      setErrors((err.body && err.body.errors) || {});
    } finally {
      setPending(false);
    }
  }

  const error = key => errors[key]
    ? <p role="alert" style={{color: 'red', margin: '0 0 0.5rem'}}>{errors[key]}</p>
    : null;

  return <main style={{padding: '2rem', maxWidth: 360}}>
    <h1>New team</h1>
    <form onSubmit={submit} noValidate>
      <label style={fieldStyle}>
        Team name
        <input value={name} onChange={e => setName(e.target.value)} />
      </label>
      {error('name')}
      <label style={fieldStyle}>
        Description
        <input value={description} onChange={e => setDescription(e.target.value)} />
      </label>
      {error('description')}
      <label style={fieldStyle}>
        Parent team
        <select value={parentId} onChange={e => setParentId(e.target.value)}>
          <option value="">No parent</option>
          {teams.map(team => (
            <option key={team.id} value={team.id}>{team.name}</option>
          ))}
        </select>
      </label>
      {error('parent_id')}
      <button type="submit" disabled={pending}>Create team</button>
    </form>
  </main>;
}
