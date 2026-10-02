import {useState} from 'react';
import {Dialog, DropdownMenu} from 'radix-ui';
import {Link, useNavigate} from 'react-router';
import {useSession} from './session.jsx';

export default function AccountMenu() {
  const {account, signOut} = useSession();
  const [menuOpen, setMenuOpen] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const navigate = useNavigate();
  if (!account) return null;
  return <>
    <DropdownMenu.Root open={menuOpen} onOpenChange={setMenuOpen}>
      <DropdownMenu.Trigger asChild>
        <button type="button" style={{marginLeft: 'auto'}}>Account menu</button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content align="end" sideOffset={4}
          style={{background: '#fff', border: '1px solid #ddd', padding: '0.25rem',
            minWidth: 160, zIndex: 50}}>
          <DropdownMenu.Label>{account.username}</DropdownMenu.Label>
          <Link to="/settings" style={{display: 'block', padding: '0.25rem 0.5rem'}}
            onClick={() => setMenuOpen(false)}>Settings</Link>
          <Link to="/organizations" style={{display: 'block', padding: '0.25rem 0.5rem'}}
            onClick={() => setMenuOpen(false)}>Your organizations</Link>
          <a href="#sign-out" style={{display: 'block', padding: '0.25rem 0.5rem'}}
            onClick={event => { event.preventDefault(); setMenuOpen(false); setDialogOpen(true); }}>Sign out</a>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
    <Dialog.Root open={dialogOpen} onOpenChange={setDialogOpen}>
      <Dialog.Portal>
        <Dialog.Overlay style={{position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 60}} />
        <Dialog.Content style={{position: 'fixed', top: '50%', left: '50%',
          transform: 'translate(-50%, -50%)', background: '#fff', border: '1px solid #ddd',
          padding: '1.5rem', minWidth: 320, maxWidth: 420, zIndex: 61}}>
          <Dialog.Title>Sign out</Dialog.Title>
          <Dialog.Description>
            Signing out ends only the current browser session. Your other sessions stay signed in.
          </Dialog.Description>
          <div style={{display: 'flex', gap: '0.5rem', marginTop: '1rem'}}>
            <button type="button" onClick={async () => {
              setDialogOpen(false);
              await signOut();
              navigate('/');
            }}>Confirm sign out</button>
            <button type="button" onClick={() => setDialogOpen(false)}>Cancel</button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  </>;
}
