#!/usr/bin/env python3
"""Apply a completed captured reply to an isolated Git snapshot; no API calls.

Use verify_app.py on the output afterward. Never modifies the live source run.
"""
import argparse
import io
import json
from pathlib import Path
import subprocess
import tarfile

from codegen import incomplete_blocks, parse_edit_blocks, parse_file_blocks, prepare_edit_files, write_files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir', type=Path)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--reply', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root, output = args.run_dir.resolve(), args.output.resolve()
    if output.exists() or output == root or root in output.parents:
        parser.error('output must be a new directory outside the source run')
    result = json.loads(args.reply.read_text())
    choices = result.get('choices', [])
    if len(choices) != 1 or choices[0].get('finish_reason') != 'stop':
        parser.error('only a single completed reply can be applied by this tool')
    text = choices[0].get('message', {}).get('content', '')
    files, edits = parse_file_blocks(text), parse_edit_blocks(text)
    if incomplete_blocks(text) or set(files) & {p for p, _, _ in edits}:
        parser.error('incomplete or mixed-format reply')
    if not files and not edits:
        parser.error('reply contains no patch')
    if any(not p.startswith(('frontend/', 'backend/')) for p in [*files, *(p for p, _, _ in edits)]):
        parser.error('patch must stay inside frontend/ and backend/')
    sha = subprocess.check_output(['git', '-C', str(root), 'rev-parse', '--verify',
                                   '--end-of-options', args.commit + '^{commit}'], text=True).strip()
    archive = subprocess.check_output(['git', '-C', str(root), 'archive', sha, '--', 'frontend', 'backend'])
    output.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        if any(not member.isfile() and not member.isdir() for member in bundle.getmembers()):
            parser.error('snapshot contains unsupported links or special files')
        bundle.extractall(output, filter='data')
    staged, errors = prepare_edit_files(output, edits)
    if errors:
        parser.error('anchor validation failed; snapshot retained, no edits applied: ' + '; '.join(errors[:3]))
    files.update(staged)
    written = write_files(output, files)
    print(json.dumps({'source_commit': sha, 'output': str(output), 'written': written}))


if __name__ == '__main__':
    main()
