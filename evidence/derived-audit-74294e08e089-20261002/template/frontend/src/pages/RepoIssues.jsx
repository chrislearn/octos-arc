import {Link, useParams} from 'react-router';

export default function RepoIssues() {
  const {owner, name} = useParams();
  const base = '/repos/' + encodeURIComponent(owner) + '/' + encodeURIComponent(name);
  return <main style={{padding: '2rem'}}>
    <h1>Issues</h1>
    <p><Link to={base}>{owner}/{name}</Link></p>
  </main>;
}
