import {useState} from 'react';
import {Link} from 'react-router';
import {requestJson} from '../shared/request.js';
import {useSession} from '../session.jsx';

const fieldStyle = {display: 'block', width: '100%', marginBottom: '0.25rem'};

export default function PasswordSettings() {
  const {account} = useSession();
  const [current, setCurrent] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [errors, setErrors] = useState({});
  const [done, setDone] = useState(false);
  const [pending, setPending] = useState(false);

  if (!account) {
    return <main style={{padding: '2rem'}}>
      <h1>Password and authentication</h1>
      <p><Link to="/signin">Sign in</Link></p>
    </main>;
  }

  async function submit(event) {
    event.preventDefault();
    setPending(true);
    try {
      await requestJson('/api/password', {
        method: 'POST',
        headers: {'x-session-id': account.sessionId},
        body: {current, password, confirm}
      });
      setErrors({});
      setDone(true);
      setCurrent('');
      setPassword('');
      setConfirm('');
    } catch (err) {
      setErrors((err.body && err.body.errors) || {});
      setPassword('');
      setConfirm('');
    } finally {
      setPending(false);
    }
  }

  const error = key => errors[key]
    ? <p role="alert" style={{color: 'red', margin: '0 0 0.5rem'}}>{errors[key]}</p>
    : null;

  return <main style={{padding: '2rem', maxWidth: 360}}>
    <h1>Password and authentication</h1>
    {done && <p role="status">Password updated</p>}
    <form onSubmit={submit} noValidate>
      <label style={fieldStyle}>
        Current password
        <input type="password" value={current} onChange={e => setCurrent(e.target.value)} />
      </label>
      {error('current')}
      <label style={fieldStyle}>
        New password
        <input type="password" value={password} onChange={e => setPassword(e.target.value)} />
      </label>
      {error('password')}
      <label style={fieldStyle}>
        Confirm password
        <input type="password" value={confirm} onChange={e => setConfirm(e.target.value)} />
      </label>
      {error('confirm')}
      <button type="submit" disabled={pending}>Update password</button>
    </form>
  </main>;
}
