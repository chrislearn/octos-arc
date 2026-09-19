// Optional same-origin SPA navigation. Set frontend/package.json arc.spa=true
// when using this helper so direct loads and refreshes reach index.html.
export function startRouter(render) {
  const show = () => render(new URL(window.location.href));
  document.addEventListener('click', event => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey ||
        event.shiftKey || event.altKey || !(event.target instanceof Element)) return;
    const link = event.target.closest('a[data-route]');
    if (!link || link.target || link.hasAttribute('download')) return;
    const destination = new URL(link.href, window.location.href);
    if (destination.origin !== window.location.origin) return;
    event.preventDefault();
    history.pushState(null, '', destination.pathname + destination.search + destination.hash);
    show();
  });
  window.addEventListener('popstate', show);
  show();
  return show;
}
