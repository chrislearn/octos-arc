// Small adapters around React/Radix, not a widget or domain-state framework.
import {useRef, useState} from 'react';
import {Dialog} from 'radix-ui';

const isolate = handler => event => {
  event.stopPropagation();
  handler?.(event);
};

// Inside Dialog.Root. The caller owns open state and save/cancel semantics.
// Radix still owns focus, Escape and outside dismissal. Never preventDefault
// here: checkbox activation and keyboard navigation must remain native.
export function DialogSurface({title, description, children, style, onClick,
  onPointerDown, onPointerUp, onKeyDown, ...props}) {
  return <Dialog.Portal>
    <Dialog.Overlay onClick={isolate()} onPointerDown={isolate()} onPointerUp={isolate()}
      style={{position: 'fixed', inset: 0, background: '#0006', zIndex: 100}} />
    <Dialog.Content {...props} data-interaction-surface="dialog"
      onClick={isolate(onClick)} onPointerDown={isolate(onPointerDown)}
      onPointerUp={isolate(onPointerUp)} onKeyDown={isolate(onKeyDown)}
      style={{position: 'fixed', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
        maxHeight: '85vh', overflow: 'auto', padding: 24, background: 'white', zIndex: 101, ...style}}>
      <Dialog.Title>{title}</Dialog.Title>
      <Dialog.Description>{description}</Dialog.Description>
      {children}
    </Dialog.Content>
  </Dialog.Portal>;
}

// run(() => requestJson(...)) returns {ok, value} or {ok:false, error/busy}.
// Only the owner may apply value and clear/close its draft after ok === true.
// The synchronous lock also covers duplicate calls before React rerenders.
export function useAsyncAction() {
  const busy = useRef(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);
  async function run(action) {
    if (busy.current) return {ok: false, busy: true};
    busy.current = true;
    setPending(true);
    setError(null);
    try {
      return {ok: true, value: await action()};
    } catch (cause) {
      const failure = cause instanceof Error ? cause : new Error(String(cause));
      setError(failure);
      return {ok: false, error: failure};
    } finally {
      busy.current = false;
      setPending(false);
    }
  }
  return {run, pending, error};
}
