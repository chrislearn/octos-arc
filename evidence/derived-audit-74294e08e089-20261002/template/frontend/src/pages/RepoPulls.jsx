import {Link, useParams} from 'react-router';

export default function RepoPulls() {
  const {owner, name} = useParams();
  const base = '/repos/' + encodeURIComponent(owner) + '/' + encodeURIComponent(name);
  return <main style={{padding: '2rem'}}>
    <h1>Pull requests</h1>
    <p><Link to={base}>{owner}/{name}</Link></p>
  </main>;
}
