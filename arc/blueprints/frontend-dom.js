// Escape untrusted text before interpolating it into HTML strings.
export function escapeHtml(value) {
  const element = document.createElement('span');
  element.textContent = value == null ? '' : String(value);
  return element.innerHTML;
}
