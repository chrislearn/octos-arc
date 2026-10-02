import {useState} from 'react';
import {useNavigate} from 'react-router';
import {requestJson} from '../shared/request.js';

const fieldStyle = {display: 'block', width: '100%', marginBottom: '0.25rem'};

export default function Register() {
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [terms, setTerms] = useState(false);
  const [errors, setErrors] = useState({});
  const [pending, setPending] = useState(false);
  const navigate = useNavigate();

  async function submit(event) {
    event.preventDefault();
    setPending(true);
    try {
      await requestJson('/api/accounts', {
        method: 'POST',
        body: {username, email, password, confirm, terms}
      });
      navigate('/signin');
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
    <h1>Create your account</h1>
    <form onSubmit={submit} noValidate>
      <label style={fieldStyle}>
        Username
        <input value={username} onChange={e => setUsername(e.target.value)} />
      </label>
      {error('username')}
      <label style={fieldStyle}>
        Email
        <input type="email" value={email} onChange={e => setEmail(e.target.value)} />
      </label>
      {error('email')}
      <label style={fieldStyle}>
        Password
        <input type="password" value={password} onChange={e => setPassword(e.target.value)} />
      </label>
      {error('password')}
      <label style={fieldStyle}>
        Confirm password
        <input type="password" value={confirm} onChange={e => setConfirm(e.target.value)} />
      </label>
      {error('confirm')}
      <label style={{display: 'block', margin: '0.5rem 0'}}>
        <input type="checkbox" checked={terms} onChange={e => setTerms(e.target.checked)} />
        {' '}Agree to the terms
      </label>
      {error('terms')}
      <button type="submit" disabled={pending}>Create account</button>
    </form>
  </main>;
}
