import {useState} from 'react';
import {Link, useNavigate} from 'react-router';
import {requestJson} from '../shared/request.js';
import {useSession} from '../session.jsx';

const fieldStyle = {display: 'block', width: '100%', marginBottom: '0.25rem'};

export default function CreateOrganization() {
  const {account} = useSession();
  const [name, setName] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [errors, setErrors] = useState({});
  const [pending, setPending] = useState(false);
  const navigate = useNavigate();

  if (!account) {
    return <main style={{padding: '2rem'}}>
      <h1>New organization</h1>
      <p><Link to="/signin">Sign in</Link></p>
    </main>;
  }

  async function submit(event) {
    event.preventDefault();
    setPending(true);
    try {
      const record = await requestJson('/api/organizations', {
        method: 'POST',
        headers: {'x-session-id': account.sessionId},
        body: {name, display_name: displayName}
      });
      navigate('/orgs/' + encodeURIComponent(record.identifier));
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
    <h1>New organization</h1>
    <form onSubmit={submit} noValidate>
      <label style={fieldStyle}>
        Organization name
        <input value={name} onChange={e => setName(e.target.value)} />
      </label>
      {error('name')}
      <label style={fieldStyle}>
        Display name
        <input value={displayName} onChange={e => setDisplayName(e.target.value)} />
      </label>
      {error('display_name')}
      <button type="submit" disabled={pending}>Create organization</button>
    </form>
  </main>;
}
