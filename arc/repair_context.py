"""Budget failure evidence fairly, without task names or fixture-specific rules."""
import re


def failure_triage(text: str, limit: int = 1200) -> str:
    """Classify observed failure layers, not inferred business root causes."""
    hints = []
    if re.search(r'Failed at: build/start|SyntaxError:|ERR_MODULE_NOT_FOUND|Cannot find module', text):
        hints.append('BUILD/LOAD: resolve the reported syntax/import/startup error before expanding features.')
    if re.search(r'ReferenceError:|TypeError:', text):
        hints.append('RUNTIME: trace the exact exception and caller contract; do not infer missing business features.')
    if re.search(r'\b(?:HTTP|status(?: code)?)\s*[:=]?\s*[45]\d\d\b', text, re.I):
        hints.append('HTTP: inspect the failing endpoint, status and request preconditions before changing rendering.')
    if re.search(r'getByRole\(|locator\.(?:click|fill)|toBeVisible\(\) failed', text):
        hints.append('UI/LOCATOR: first distinguish missing required data, failed request, stale UI and locator timing/semantics. '
                     'A timeout alone proves none of these. Compare the last actions, response and rendered snapshot. '
                     'If the target exists under another role, inspect helper fallback and async readiness; do not turn '
                     'all links into buttons or ordinary text into headings merely to satisfy a fallback selector.')
    if len(re.findall(r'(?m)^- Feature:', text)) > 1 and hints:
        hints.append('SHARED CAUSE: group only with a concrete common exception or source/data owner. '
                     'The same test-helper line or timeout is not evidence of the same bug; keep each verdict.')
    if not hints or limit <= 0:
        return ''
    return ('Diagnostic hypotheses (verify against current source; not test verdicts):\n' +
            '\n'.join(hints))[:limit]


def _clip(text: str, limit: int) -> str:
    if limit <= 0:
        return ''
    if len(text) <= limit:
        return text
    if limit < 80:
        return text[:limit]
    marker = '\n... [shortened] ...\n'
    room = limit - len(marker)
    head = room * 2 // 3
    return text[:head] + marker + text[-(room - head):]


def balanced_failure_evidence(text: str, limit: int = 8000) -> str:
    """All failure cores precede detail; each failure gets an equal detail share.

    Failure headers/locations/observations/steps must not lose their place to an
    earlier DOM snapshot. Keep diagnostics before DOM detail (mutation targets
    and runtime errors often explain what the screenshot alone cannot).
    Infrastructure and other unstructured messages retain their head AND tail.
    """
    return _balanced_failure_evidence(text, limit)


def diagnosed_failure_evidence(text: str, limit: int = 8000) -> str:
    """Keep classification and original evidence inside the caller's budget."""
    hint = failure_triage(text, min(1200, max(0, limit // 5)))
    if not hint:
        return balanced_failure_evidence(text, limit)
    return hint + '\n' + balanced_failure_evidence(text, max(0, limit - len(hint) - 1))


def _balanced_failure_evidence(text: str, limit: int) -> str:
    if limit <= 0:
        return ''
    if len(text) <= limit:
        return text
    starts = list(re.finditer(r'(?m)^- Feature: ', text))
    if not starts:
        return _clip(text, limit)
    prefix = text[:starts[0].start()]
    blocks = [text[m.start(): starts[i + 1].start() if i + 1 < len(starts) else len(text)]
              for i, m in enumerate(starts)]
    cores, details = [], []
    for block in blocks:
        parts = re.split(r'(?m)(?=  (?:Page at failure|Browser diagnostics)\b)', block)
        cores.append(parts[0].strip())
        diagnostic = [p for p in parts[1:] if p.startswith('  Browser diagnostics')]
        page = [p for p in parts[1:] if p.startswith('  Page at failure')]
        details.append('\n'.join(diagnostic + page).strip())
    prefix = _clip(prefix, min(500, limit // 10))
    # Reserve most room for every core, not the first verbose failure.
    core_share = max(0, (limit * 3 // 4 - len(prefix) - len(cores)) // len(cores))
    result = prefix + '\n'.join(_clip(core, core_share) for core in cores)
    remaining = max(0, limit - len(result))
    nonempty = [i for i, detail in enumerate(details) if detail]
    share = remaining // max(1, len(nonempty))
    for i in nonempty:
        heading = '\nDetail for ' + cores[i].splitlines()[0][:160] + ':\n'
        if share > len(heading):
            result += heading + _clip(details[i], share - len(heading))
    return result[:limit]
