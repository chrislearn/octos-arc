import {useState} from 'react';
import {Link, useNavigate} from 'react-router';
import {useSession} from '../session.jsx';

export default function Home() {
  const {account} = useSession();
  const [query, setQuery] = useState('');
  const navigate = useNavigate();
  return <main style={{padding: '2rem'}}>
    <h1>GitHub Collaboration</h1>
    <form onSubmit={event => {
      event.preventDefault();
      navigate('/search?q=' + encodeURIComponent(query));
    }}>
      <input type="search" aria-label="Search" value={query}
        onChange={e => setQuery(e.target.value)}
        style={{display: 'block', width: '100%', maxWidth: 480, marginBottom: '0.5rem'}} />
    </form>
    {account
      ? <p>Signed in as {account.username}</p>
      : <p><Link to="/signin">Sign in</Link> <Link to="/recover">Forgot password</Link></p>}
  </main>;
}
