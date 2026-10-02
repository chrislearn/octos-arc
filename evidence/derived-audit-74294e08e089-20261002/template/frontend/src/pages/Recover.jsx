import {useState} from 'react';
import {Link} from 'react-router';
import {requestJson} from '../shared/request.js';

const fieldStyle = {display: 'block', width: '100%', marginBottom: '0.25rem'};

export default function Recover() {
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [errors, setErrors] = useState({});
  const [step, setStep] = useState(1);
  const [done, setDone] = useState(false);
  const [pending, setPending] = useState(false);

  function sendLink(event) {
    event.preventDefault();
    setErrors({});
    setStep(2);
  }

  async function reset(event) {
    event.preventDefault();
    setPending(true);
    try {
      await requestJson('/api/recovery/reset', {
        method: 'POST',
        body: {email, code, password, confirm}
      });
      setErrors({});
      setDone(true);
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

  if (done) {
    return <main style={{padding: '2rem', maxWidth: 360}}>
      <h1>Reset password</h1>
      <p>Password updated</p>
      <p><Link to="/signin">Sign in</Link></p>
    </main>;
  }

  if (step === 1) {
    return <main style={{padding: '2rem', maxWidth: 360}}>
      <h1>Reset password</h1>
      <form onSubmit={sendLink} noValidate>
        <label style={fieldStyle}>
          Email
          <input type="email" value={email} onChange={e => setEmail(e.target.value)} />
        </label>
        {error('email')}
        <button type="submit">Send reset link</button>
      </form>
      <p><Link to="/signin">Sign in</Link></p>
    </main>;
  }

  return <main style={{padding: '2rem', maxWidth: 360}}>
    <h1>Reset password</h1>
    <p>Verification code: <strong>123456</strong></p>
    <form onSubmit={reset} noValidate>
      <label style={fieldStyle}>
        Verification code
        <input value={code} onChange={e => setCode(e.target.value)} />
      </label>
      {error('code')}
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
      <button type="submit" disabled={pending}>Reset password</button>
    </form>
  </main>;
}
