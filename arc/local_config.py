"""Read local API credentials without shell evaluation or logging values.

Development helper only; not part of the deployment bundle.
"""
from pathlib import Path
import re
from urllib.parse import urlsplit


def api_environment(path: Path) -> dict[str, str]:
    names = {'api_key': 'OPENAI_API_KEY', 'openai_api_key': 'OPENAI_API_KEY',
             'base_url': 'OPENAI_BASE_URL', 'openai_base_url': 'OPENAI_BASE_URL',
             'model': 'MODEL', 'visual_model': 'VISUAL_MODEL'}
    result = {}
    for line_number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        match = re.fullmatch(r'\s*(?:export\s+)?([\w]+)\s*[:=]\s*(.*?)\s*', line)
        if not match or match[1].lower() not in names:
            raise ValueError(f'Invalid API configuration field on line {line_number}')
        value = match[2]
        if len(value) >= 2 and value[0] == value[-1] and value[0] in '\"\'':
            value = value[1:-1]
        name = names[match[1].lower()]
        if not value or name in result:
            raise ValueError(f'Empty or duplicate API configuration field on line {line_number}')
        result[name] = value
    if not result.get('OPENAI_API_KEY') or not result.get('OPENAI_BASE_URL'):
        raise ValueError('API configuration requires api_key and base_url')
    url = urlsplit(result['OPENAI_BASE_URL'])
    if url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password:
        raise ValueError('API base URL must be an HTTP(S) endpoint without embedded credentials')
    return result
