#!/usr/bin/env python3
"""One bounded, tools-disabled diagnostic completion. Never writes app sources.

Select an existing recorded user prompt by a literal substring and retain the
raw response for truncation/repetition analysis. Credentials never enter logs.
"""
import argparse
import json
from pathlib import Path
import time
import urllib.request

from local_config import api_environment
from llm_proxy import open_upstream
from main import CODEGEN_SYSTEM


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir', type=Path)
    parser.add_argument('--api-config', type=Path, required=True)
    parser.add_argument('--needle', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-output', type=int, default=8192)
    args = parser.parse_args()
    if not 1 <= args.max_output <= 32768 or args.output.exists():
        parser.error('max-output must be 1..32768 and output must not exist')
    config = api_environment(args.api_config)
    prompt = None
    for line in (args.run_dir / '.arc/octos-events.jsonl').read_text().splitlines():
        event = json.loads(line)
        payload = event.get('params', {}).get('payload', {})
        text = payload.get('data', {}).get('text', '')
        if payload.get('type') == 'user_message' and args.needle in text:
            prompt = text
            break
    if not prompt:
        parser.error('No matching recorded prompt')
    body = {'model': config.get('MODEL', 'deepseek-v4-flash'),
            'messages': [{'role': 'system', 'content': CODEGEN_SYSTEM}, {'role': 'user', 'content': prompt}],
            'thinking': {'type': 'disabled'}, 'stream': False, 'max_tokens': args.max_output}
    request = urllib.request.Request(config['OPENAI_BASE_URL'].rstrip('/') + '/chat/completions',
        data=json.dumps(body).encode(), headers={'Content-Type': 'application/json',
                                               'Authorization': 'Bearer ' + config['OPENAI_API_KEY']})
    start = time.monotonic()
    try:
        with open_upstream(request, timeout=180) as response:
            result = json.load(response)
    except Exception as exc:
        print(json.dumps({'error_type': type(exc).__name__, 'http_status': getattr(exc, 'code', None)}))
        return 1
    result['_diagnostic'] = {'elapsed_seconds': round(time.monotonic() - start, 3),
                             'prompt_chars': len(prompt), 'max_output': args.max_output,
                             'system': CODEGEN_SYSTEM}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as target:
        json.dump(result, target, ensure_ascii=False, indent=2)
    print(json.dumps({'usage': result.get('usage'), 'finish_reason': result.get('choices', [{}])[0].get('finish_reason'),
                      'diagnostic': result['_diagnostic'], 'output': str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
