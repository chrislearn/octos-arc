import {Link} from 'react-router';
import {useSession} from '../session.jsx';

export default function Settings() {
  const {account} = useSession();
  if (!account) {
    return <main style={{padding: '2rem'}}>
      <h1>Settings</h1>
      <p><Link to="/signin">Sign in</Link></p>
    </main>;
  }
  return <main style={{padding: '2rem'}}>
    <h1>Settings</h1>
    <p>Signed in as {account.username}</p>
    <p><Link to="/settings/password">Password and authentication</Link></p>
  </main>;
}
