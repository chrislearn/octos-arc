import {useState} from 'react';
import {Link, useNavigate} from 'react-router';
import {requestJson} from '../shared/request.js';
import {useSession} from '../session.jsx';

export default function SignIn() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  const {signIn} = useSession();
  const navigate = useNavigate();

  async function submit(event) {
    event.preventDefault();
    setPending(true);
    setError('');
    try {
      const record = await requestJson('/api/session', {
        method: 'POST',
        body: {username, password}
      });
      signIn(record);
      navigate('/');
    } catch (err) {
      setError(err.message || 'Invalid credentials');
      setPassword('');
    } finally {
      setPending(false);
    }
  }

  return <main style={{padding: '2rem', maxWidth: 360}}>
    <h1>Sign in</h1>
    <form onSubmit={submit} noValidate>
      <label style={{display: 'block', marginBottom: '0.75rem'}}>
        Username or email
        <input style={{display: 'block', width: '100%'}} value={username}
          onChange={e => setUsername(e.target.value)} />
      </label>
      <label style={{display: 'block', marginBottom: '0.75rem'}}>
        Password
        <input type="password" style={{display: 'block', width: '100%'}} value={password}
          onChange={e => setPassword(e.target.value)} />
      </label>
      {error && <p role="alert" style={{color: 'red'}}>{error}</p>}
      <button type="submit" disabled={pending}>Sign in</button>
    </form>
    <p><Link to="/register">Create an account</Link></p>
    <p><Link to="/recover">Forgot password</Link></p>
  </main>;
}
