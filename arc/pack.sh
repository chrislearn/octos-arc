#!/bin/sh
# 把 arc/ 打成 ARC 平台要的提交包（main.py 必须在 zip 根目录）
set -e
# Optional first argument is deployment policy, not generated app content.
ROUTES=""
if [ "$#" -gt 0 ]; then
    ROUTES="$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$1")"
fi
cd "$(dirname "$0")"
if [ -n "$ROUTES" ]; then
    python3 -c 'import sys; from pathlib import Path; from llm_proxy import model_routes; model_routes(Path(sys.argv[1]).read_text())' "$ROUTES"
fi
rm -f ../octos-arc-bundle.zip
zip -qr ../octos-arc-bundle.zip main.py rust_engine.py arc-policy.toml prompts octos_stdio.py requirement_order.py requirement_contracts.py scenario_tests.py scenario_review.py acceptance.py web_checks.py frontend_assets.py verify_app.py action_errors.cjs page_errors.ts guard.py llm_proxy.py progress_timeout.py codegen.py flow_policy.py reply_quality.py repair_context.py source_index.py generation_checks.py snapshot_focus.py generic_template.py web_stack.py blueprints hooks requirements.txt arcbench_agent_runtime -x '*/__pycache__/*' '*.pyc'
if [ -n "$ROUTES" ]; then
    python3 -c 'import sys; from zipfile import ZipFile; z=ZipFile("../octos-arc-bundle.zip", "a"); z.write(sys.argv[1], "model-routes.json"); z.close()' "$ROUTES"
fi
# Ship the locally built kernel as bin/octos when one exists for Linux x86_64
# (arc/bin/octos, a cross target, or target/release/octos -- see pack_kernel.py).
# main.py then runs it instead of downloading OCTOS_RELEASE_URL.
# ARC_PACK_KERNEL=0 forces the small, download-based bundle.
python3 pack_kernel.py ../octos-arc-bundle.zip
echo "打包完成：$(cd .. && pwd)/octos-arc-bundle.zip（$(du -h ../octos-arc-bundle.zip | cut -f1)）"
shasum -a 256 ../octos-arc-bundle.zip
