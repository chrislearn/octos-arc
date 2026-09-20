"""Budget failure evidence fairly, without task names or fixture-specific rules."""
import re


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
