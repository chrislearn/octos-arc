// One scope per independently replaceable read (session, record, search, ...).
// Keep it stable across renders. begin() invalidates the previous read; cancel()
// invalidates on owner change, sign-out or unmount, even without another request.
// Abort is best-effort: check ticket.isCurrent() before EVERY state publication,
// including catch/finally. This does not cancel server writes or authorize data.
export function createRequestScope() {
  let active = null;
  return {
    begin() {
      const previous = active;
      const controller = new AbortController();
      active = controller;
      previous?.abort();
      return {
        signal: controller.signal,
        isCurrent: () => active === controller && !controller.signal.aborted,
      };
    },
    cancel() {
      const previous = active;
      active = null;
      previous?.abort();
    },
  };
}
