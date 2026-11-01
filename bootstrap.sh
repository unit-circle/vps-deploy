#!/usr/bin/env bash
# Fetch one consistent project revision, validate syntax, then enter the menu.
set -Eeuo pipefail
umask 077
if [[ ${1:-} == --help ]]; then
  echo '用法：bash bootstrap.sh [公网IPv4 [节点名称] | 管理子命令]'
  echo '默认菜单；可使用 VPS_DEPLOY_REF=完整提交SHA 固定项目版本。'
  exit 0
fi
[[ $EUID -eq 0 ]] || { echo '请使用 root。' >&2; exit 1; }
for tool in curl python3; do
  command -v "$tool" >/dev/null || { echo '请先安装 curl、ca-certificates、python3、util-linux。' >&2; exit 1; }
done
ref=${VPS_DEPLOY_REF:-main}
[[ $ref =~ ^[A-Za-z0-9._-]+$ ]] || { echo '项目版本参数不合法。' >&2; exit 1; }
revision=$(curl --proto '=https' --tlsv1.2 -fsSL --retry 3 \
  "https://api.github.com/repos/unit-circle/vps-deploy/commits/$ref" | \
  python3 -c 'import json,sys; print(json.load(sys.stdin)["sha"])')
[[ $revision =~ ^[0-9a-f]{40}$ ]] || { echo '无法解析项目版本。' >&2; exit 1; }
bundle=$(mktemp -d /root/vps-deploy-XXXXXXXX)
mkdir -m 700 "$bundle/scripts"
for file in deploy-vps.sh scripts/vps-nodes.py scripts/vps-manage.py; do
  curl --proto '=https' --tlsv1.2 -fL --retry 3 \
    "https://raw.githubusercontent.com/unit-circle/vps-deploy/$revision/$file" -o "$bundle/$file"
done
printf '%s\n' "$revision" > "$bundle/.revision"
bash -n "$bundle/deploy-vps.sh"
python3 - "$bundle" <<'CHECK_BUNDLE'
import ast, sys
from pathlib import Path
for source in (Path(sys.argv[1])/'scripts').glob('*.py'):
    ast.parse(source.read_text(encoding='utf-8'), filename=str(source))
CHECK_BUNDLE
echo "项目版本：$revision"
echo "本地入口：$bundle/deploy-vps.sh"
exec bash "$bundle/deploy-vps.sh" "$@"
