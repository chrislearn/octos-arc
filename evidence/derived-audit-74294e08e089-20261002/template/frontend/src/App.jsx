import {Link, Outlet, Route, Routes} from 'react-router';
import {SessionProvider, useSession} from './session.jsx';
import Home from './pages/Home.jsx';
import SignIn from './pages/SignIn.jsx';
import Register from './pages/Register.jsx';
import Settings from './pages/Settings.jsx';
import Recover from './pages/Recover.jsx';
import PasswordSettings from './pages/PasswordSettings.jsx';
import AccountMenu from './AccountMenu.jsx';
import Search from './pages/Search.jsx';
import Repository from './pages/Repository.jsx';
import FileContent from './pages/FileContent.jsx';
import RepoIssues from './pages/RepoIssues.jsx';
import RepoPulls from './pages/RepoPulls.jsx';
import OrgPage from './pages/OrgPage.jsx';
import OrgTeams from './pages/OrgTeams.jsx';
import NewTeam from './pages/NewTeam.jsx';
import TeamPage from './pages/TeamPage.jsx';
import YourOrganizations from './pages/YourOrganizations.jsx';
import CreateOrganization from './pages/CreateOrganization.jsx';

function Layout() {
  const {account} = useSession();
  return <div>
    <header style={{display: 'flex', gap: '1rem', alignItems: 'center',
      padding: '0.75rem 2rem', borderBottom: '1px solid #ddd'}}>
      <Link to="/">Home</Link>
      <AccountMenu />
    </header>
    <Outlet />
  </div>;
}

export default function App() {
  return <SessionProvider>
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Home />} />
        <Route path="/signin" element={<SignIn />} />
        <Route path="/register" element={<Register />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/recover" element={<Recover />} />
        <Route path="/settings/password" element={<PasswordSettings />} />
        <Route path="/search" element={<Search />} />
        <Route path="/repos/:owner/:name" element={<Repository />} />
        <Route path="/repos/:owner/:name/file/:branch/*path" element={<FileContent />} />
        <Route path="/repos/:owner/:name/issues" element={<RepoIssues />} />
        <Route path="/repos/:owner/:name/pulls" element={<RepoPulls />} />
        <Route path="/organizations" element={<YourOrganizations />} />
        <Route path="/organizations/new" element={<CreateOrganization />} />
        <Route path="/orgs/:identifier" element={<OrgPage />} />
        <Route path="/orgs/:identifier/people" element={<OrgPage />} />
        <Route path="/orgs/:identifier/teams" element={<OrgTeams />} />
        <Route path="/orgs/:identifier/teams/new" element={<NewTeam />} />
        <Route path="/orgs/:identifier/teams/:team" element={<TeamPage />} />
        <Route path="/orgs/:identifier/teams/:team/settings" element={<TeamPage />} />
      </Route>
    </Routes>
  </SessionProvider>;
}
