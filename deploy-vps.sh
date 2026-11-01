#!/usr/bin/env bash
# Ubuntu 22.04/24.04, Debian 12/13; intended for a fresh dedicated VPS.
# Public IPv4 is a command argument, never hardcoded. Version: 2026-11-01.
# Uses official stable installers; no full remote VPS installation test performed.
# Usage: bash deploy-vps.sh [PUBLIC_IPV4 [NODE_NAME] | --menu | --help]
# Does not change firewall rules. Existing configurations are never overwritten.
set -Eeuo pipefail
umask 022
export LC_ALL=C
export TERM=${TERM:-xterm}
die() { echo "错误：$*" >&2; exit 1; }
if [[ ${1:-} == --help ]]; then
  echo '用法：bash deploy-vps.sh [公网IPv4 [节点名称] | --menu]'
  echo '无参数启动菜单。管理命令：check、backup、update、network、https、upgrade、restore。'
  echo '修改操作先预览；加 --apply 才执行。查看完整说明：README.md。'
  exit 0
fi
[[ $EUID -eq 0 ]] || die '请使用 root 执行。'
command -v python3 >/dev/null || die '请先执行 apt-get update && apt-get install -y python3'
command -v curl >/dev/null || die '请先安装 curl 和 ca-certificates。'
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project_revision=local
bootstrap_dir=
local_bundle=false
if [[ -f "$script_dir/scripts/vps-nodes.py" && -f "$script_dir/scripts/vps-manage.py" ]]; then
  local_bundle=true
fi
project_file() {
  local source=$1 destination=$2
  if [[ $local_bundle == true ]]; then
    cp -- "$script_dir/$source" "$destination"
    [[ ! -f "$script_dir/.revision" ]] || project_revision=$(cat "$script_dir/.revision")
    return
  fi
  local ref=${VPS_DEPLOY_REF:-main}
  [[ $ref =~ ^[A-Za-z0-9._-]+$ ]] || die 'VPS_DEPLOY_REF 需要为 SHA、分支名或标签。'
  if [[ $project_revision == local ]]; then
    project_revision=$(curl --proto '=https' --tlsv1.2 -fsSL --retry 3 \
      "https://api.github.com/repos/unit-circle/vps-deploy/commits/$ref" | \
      python3 -c 'import json,sys; print(json.load(sys.stdin)["sha"])')
    [[ $project_revision =~ ^[0-9a-f]{40}$ ]] || die '无法解析项目版本。'
  fi
  curl --proto '=https' --tlsv1.2 -fL --retry 3 \
    "https://raw.githubusercontent.com/unit-circle/vps-deploy/$project_revision/$source" -o "$destination"
}
run_manager() {
  if [[ -z $bootstrap_dir ]]; then
    bootstrap_dir=$(mktemp -d /root/vps-menu-XXXXXXXX)
    project_file scripts/vps-manage.py "$bootstrap_dir/vps-manage.py"
    python3 -c 'import ast,sys; ast.parse(open(sys.argv[1],encoding="utf-8").read())' "$bootstrap_dir/vps-manage.py"
  fi
  python3 "$bootstrap_dir/vps-manage.py" "$@"
}
confirm_apply() {
  local answer
  read -r -p '确认影响后输入 APPLY 执行，其它输入取消：' answer
  [[ $answer == APPLY ]]
}
menu() {
  [[ -t 0 ]] || die '菜单需要交互终端；自动化请使用参数或管理子命令。'
  local choice ip label domain email component version checksum snapshot bbr
  while true; do
    printf '\nVPS Deploy：保留双协议和原生出口\n'
    printf '1) 新服务器安装  2) 状态和 Google 检查  3) 私密完整备份\n'
    printf '4) IPv4 配置更新  5) 网络调优  6) 可选 HTTPS 订阅\n'
    printf '7) 指定版本升级  8) 恢复备份  9) 显示私密订阅  0) 退出\n'
    read -r -p '选择：' choice || return 0
    case $choice in
      1) read -r -p '服务器公网 IPv4：' ip
         read -r -p '节点名称（默认 VPS）：' label
         bash "$script_dir/deploy-vps.sh" "$ip" "${label:-VPS}" || echo '安装未完成，请保留错误和安装记录。' ;;
      2) run_manager check --google || echo '检查发现问题；未修改配置。' ;;
      3) run_manager backup || echo '备份失败。' ;;
      4) if run_manager update && confirm_apply; then run_manager update --apply || echo '更新失败，请检查回滚结果。'; fi ;;
      5) read -r -p '同时启用内核已支持的 BBR？输入 yes，其它输入仅调整缓冲区：' bbr
         local -a flags=()
         [[ $bbr != yes ]] || flags+=(--bbr)
         if run_manager network "${flags[@]}" && confirm_apply; then run_manager network "${flags[@]}" --apply || echo '调优失败。'; fi ;;
      6) echo '需要已解析的域名、80/TCP、8443/TCP 和经校验的 Caddy；443 节点端口保持不变。'
         read -r -p '订阅域名：' domain
         read -r -p 'ACME 联系邮箱：' email
         if run_manager https --domain "$domain" --email "$email" && confirm_apply; then
           run_manager https --domain "$domain" --email "$email" --apply || echo 'HTTPS 启用失败，请检查回滚结果。'
         fi ;;
      7) echo '明确指定稳定版本；先检查官方 Release 说明。缺少官方资产摘要时需手动提供可信 SHA256。'
         read -r -p '组件 xray / hysteria / caddy：' component
         read -r -p '完整版本号，例如 v2.13.0：' version
         read -r -p '可选 SHA256（官方资产已有摘要时留空）：' checksum
         local -a digest=()
         [[ -z $checksum ]] || digest+=(--sha256 "$checksum")
         if run_manager upgrade "$component" --version "$version" "${digest[@]}" && confirm_apply; then
           run_manager upgrade "$component" --version "$version" "${digest[@]}" --apply || echo '版本升级失败，请检查回滚结果。'
         fi ;;
      8) read -r -p '/root/vps-backups 下的快照目录：' snapshot
         if run_manager restore "$snapshot" && confirm_apply; then run_manager restore "$snapshot" --apply || echo '恢复失败。'; fi ;;
      9) echo '以下地址包含节点凭据：'; cat /root/vps-nodes/subscription.txt ;;
      0) return 0 ;;
      *) echo '请选择 0–9。' ;;
    esac
  done
}
if [[ $# -eq 0 || ${1:-} == --menu ]]; then menu; exit 0; fi
case ${1:-} in
  check|backup|update|network|https|upgrade|restore) run_manager "$@"; exit $? ;;
esac
[[ $# -ge 1 && $# -le 2 ]] || die '参数数量不正确；使用 --help 查看说明。'
python3 - "$1" <<'CHECK_IP'
import ipaddress, sys
a = ipaddress.ip_address(sys.argv[1])
if a.version != 4 or not a.is_global:
    raise SystemExit('请填写服务器的公网 IPv4 地址')
CHECK_IP
python3 - "${2:-VPS}" <<'CHECK_NAME'
import sys
name = sys.argv[1]
if not name.strip() or len(name)>64 or any(ord(c)<32 for c in name):
    raise SystemExit('节点名称需要 1–64 个可见字符')
CHECK_NAME
command -v flock >/dev/null || die '缺少 flock，请安装 util-linux。'
exec 9>/run/lock/vps-deploy.lock
flock -n 9 || die '另一个部署进程正在运行。'
if [[ -f /root/vps-nodes/.deploy-complete ]]; then
  saved_ip=$(python3 -c "import json; print(json.load(open('/root/vps-nodes/clash.yaml'))['proxies'][0]['server'])")
  [[ $saved_ip == "$1" ]] || die "已有节点使用 IP $saved_ip。不会自动改 IP 或重建密钥。"
  echo '此脚本此前已完成部署；未作修改。当前订阅：'
  cat /root/vps-nodes/subscription.txt
  systemctl is-active xray hysteria-server vps-sub
  exit 0
fi
for path in /usr/local/etc/xray/config.json /etc/hysteria/config.yaml \
  /root/vps-nodes /etc/vps-sub /opt/vps-sub \
  /etc/systemd/system/vps-sub.service; do
  [[ ! -e "$path" ]] || die "发现已有配置或未完成的部署：$path；已停止，未覆盖。不要删除正常使用的配置。"
done
[[ -d /run/systemd/system ]] || die '需要使用 systemd 的服务器。'
. /etc/os-release
[[ $ID == ubuntu || $ID == debian ]] || die '此脚本仅支持 Ubuntu / Debian。'
work=$(mktemp -d /root/vps-install-XXXXXXXX)
echo "安装记录目录：$work"
on_error() {
  code=$?
  trap - ERR
  echo "部署未完成（退出码 $code）。保留文件以便排错，没有自动删除或重装。" >&2
  echo '查看日志：journalctl -u xray -u hysteria-server -u vps-sub -n 60 --no-pager' >&2
  exit "$code"
}
trap on_error ERR
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y curl ca-certificates unzip openssl python3 iproute2
# Check listening sockets before installation.
python3 <<'CHECK_PORTS'
import socket
for typ, port in [(socket.SOCK_STREAM,443),(socket.SOCK_DGRAM,443),(socket.SOCK_STREAM,8080)]:
    with socket.socket(socket.AF_INET, typ) as s:
        try: s.bind(('0.0.0.0',port))
        except OSError: raise SystemExit(f'端口 {port}（{typ.name}）已被占用，停止安装')
CHECK_PORTS
for user in vps-xray vps-hy vps-sub; do
  id "$user" >/dev/null 2>&1 || useradd --system --user-group --no-create-home --shell /usr/sbin/nologin "$user"
done
# Official installers: save first, then run; never use curl | bash.
curl --proto '=https' --tlsv1.2 -fL --retry 3 \
  https://raw.githubusercontent.com/XTLS/Xray-install/main/install-release.sh -o "$work/xray-install.sh"
curl --proto '=https' --tlsv1.2 -fL --retry 3 https://get.hy2.sh/ -o "$work/hysteria-install.sh"
# Current official installer removed -u/--install-user. Our systemd drop-in
# below selects vps-xray independently of the installer default account.
project_file scripts/vps-nodes.py "$work/vps-nodes.py"
project_file scripts/vps-manage.py "$work/vps-manage.py"
python3 -c 'import ast,sys; ast.parse(open(sys.argv[1]).read())' "$work/vps-nodes.py"
python3 -c 'import ast,sys; ast.parse(open(sys.argv[1],encoding="utf-8").read())' "$work/vps-manage.py"
bash -n "$work/xray-install.sh"
bash -n "$work/hysteria-install.sh"
bash "$work/xray-install.sh" install --without-geodata
bash "$work/hysteria-install.sh"
systemctl stop xray hysteria-server
install -m 755 "$work/vps-nodes.py" /usr/local/sbin/vps-nodes
install -m 755 "$work/vps-manage.py" /usr/local/sbin/vps-manage
install -d -m 755 /usr/local/etc /usr/local/etc/xray
install -d -o root -g vps-hy -m 750 /etc/hysteria
install -d -m 700 /root/vps-nodes
install -d -o root -g vps-sub -m 750 /etc/vps-sub
install -d -m 755 /opt/vps-sub
openssl req -x509 -newkey rsa:2048 -sha256 -nodes -days 3650 \
  -subj '/CN=vps-node.local' -addext 'subjectAltName=DNS:vps-node.local' \
  -keyout /etc/hysteria/server.key -out /etc/hysteria/server.crt >/dev/null 2>&1
export VPS_PUBLIC_IP="$1"
export VPS_NODE_NAME="${2:-VPS}"
python3 <<'GENERATE'
import json, os, re, secrets, subprocess, uuid
from pathlib import Path
from urllib.parse import urlencode, quote

os.umask(0o077)  # Secret files are private from their first write.
ip = os.environ['VPS_PUBLIC_IP']
label = os.environ['VPS_NODE_NAME']
if not label.strip() or len(label)>64 or any(ord(c)<32 for c in label):
    raise SystemExit('节点名称需要 1–64 个可见字符')
out = Path('/root/vps-nodes')
keys = subprocess.check_output(['/usr/local/bin/xray','x25519'], text=True, stderr=subprocess.STDOUT)
def key(label):
    m = re.search(r'^\s*'+label+r'\s*:\s*(\S+)\s*$', keys, re.I|re.M)
    if not m: raise RuntimeError('无法解析 Xray 密钥格式；请勿公开原始输出')
    return m.group(1)
private = key(r'Private\s*Key')
public = key(r'(?:Public\s*Key|Password(?:\s*\(PublicKey\))?)')
uid, sid = str(uuid.uuid4()), secrets.token_hex(8)
password, token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
sni = 'www.cloudflare.com'
cert = subprocess.check_output(['openssl','x509','-in','/etc/hysteria/server.crt',
    '-noout','-fingerprint','-sha256'],text=True)
fingerprint = cert.strip().split('=',1)[1].replace(':','').lower()
def write(path, obj):
    Path(path).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
write('/usr/local/etc/xray/config.json', {
  'log':{'loglevel':'warning'},
  'inbounds':[{'listen':'0.0.0.0','port':443,'protocol':'vless',
    'settings':{'clients':[{'id':uid,'flow':'xtls-rprx-vision'}],'decryption':'none'},
    'streamSettings':{'network':'tcp','security':'reality','realitySettings':{
      'show':False,'target':sni+':443','xver':0,'serverNames':[sni],
      'privateKey':private,'shortIds':[sid]}}}],
  'outbounds':[{'protocol':'freedom','tag':'direct',
    'streamSettings':{'sockopt':{'domainStrategy':'ForceIPv4'}}}]})
# JSON is valid YAML and avoids YAML quoting/dependency problems.
write('/etc/hysteria/config.yaml',{
  'listen':'0.0.0.0:443',
  'tls':{'cert':'/etc/hysteria/server.crt','key':'/etc/hysteria/server.key'},
  'auth':{'type':'password','password':password},
  'outbounds':[{'name':'direct','type':'direct','direct':{'mode':'4'}}],
  'masquerade':{'type':'proxy','proxy':{'url':'https://www.cloudflare.com/','rewriteHost':True}}})
nodes=[{'name':label+'-VLESS','type':'vless','server':ip,'port':443,
    'uuid':uid,'network':'tcp','tls':True,'udp':True,'flow':'xtls-rprx-vision',
    'servername':sni,'client-fingerprint':'chrome',
    'reality-opts':{'public-key':public,'short-id':sid}},
  {'name':label+'-HY2','type':'hysteria2','server':ip,'port':443,
    'password':password,'sni':'vps-node.local','skip-cert-verify':True,
    'fingerprint':fingerprint,'alpn':['h3']}]
clash={'mixed-port':7890,'allow-lan':False,'mode':'rule','log-level':'info',
  'proxies':nodes,'proxy-groups':[{'name':'PROXY','type':'select',
  'proxies':[n['name'] for n in nodes]+['DIRECT']}],'rules':['MATCH,PROXY']}
write(out/'local-nodes.json',{'proxies':nodes})
write(out/'clash.yaml',clash)
write('/etc/vps-sub/clash.yaml',clash)
write('/etc/vps-sub/settings.json',{'token':token})
v='vless://'+uid+'@'+ip+':443?'+urlencode({'encryption':'none','security':'reality',
    'type':'tcp','flow':'xtls-rprx-vision','sni':sni,'fp':'chrome','pbk':public,'sid':sid})+'#'+quote(label+'-VLESS',safe='')
h='hysteria2://'+quote(password,safe='')+'@'+ip+':443/?'+urlencode({
    'sni':'vps-node.local','insecure':'1','pinSHA256':fingerprint})+'#'+quote(label+'-HY2',safe='')
(out/'links.txt').write_text(v+'\n'+h+'\n')
(out/'subscription.txt').write_text(f'http://{ip}:8080/{token}/clash.yaml\n')
GENERATE
VPS_PROJECT_REVISION="$project_revision" python3 <<'RECORD_VERSION'
import json, os, subprocess
from pathlib import Path
versions = {component:subprocess.check_output([binary,'version'],text=True).strip()
    for component,binary in [('xray','/usr/local/bin/xray'),('hysteria','/usr/local/bin/hysteria')]}
Path('/root/vps-nodes/deployment.json').write_text(json.dumps(
    {'project_revision':os.environ['VPS_PROJECT_REVISION'],'initial_versions':versions},indent=2)+'\n')
RECORD_VERSION
chown root:vps-xray /usr/local/etc/xray/config.json
chmod 640 /usr/local/etc/xray/config.json
chown root:vps-hy /etc/hysteria/config.yaml /etc/hysteria/server.key /etc/hysteria/server.crt
chmod 640 /etc/hysteria/config.yaml /etc/hysteria/server.key /etc/hysteria/server.crt
chown root:vps-sub /etc/vps-sub/clash.yaml /etc/vps-sub/settings.json
chmod 640 /etc/vps-sub/clash.yaml /etc/vps-sub/settings.json
chmod 600 /root/vps-nodes/*
cat > /opt/vps-sub/server.py <<'SUB_SERVER'
import hmac, json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
settings = json.loads(Path('/etc/vps-sub/settings.json').read_text())
expected = '/'+settings['token']+'/clash.yaml'
class Handler(BaseHTTPRequestHandler):
    timeout = 10
    def do_GET(self): self.serve(True)
    def do_HEAD(self): self.serve(False)
    def serve(self, body):
        if not hmac.compare_digest(self.path.encode(),expected.encode()):
            self.send_error(404); return
        data = Path('/etc/vps-sub/clash.yaml').read_bytes()
        self.send_response(200)
        self.send_header('Content-Type','text/yaml; charset=utf-8')
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers()
        if body: self.wfile.write(data)
    def log_message(self, *args): pass  # Never log the secret subscription path.
ThreadingHTTPServer.daemon_threads = True
ThreadingHTTPServer.request_queue_size = 32
ThreadingHTTPServer((settings.get('listen','0.0.0.0'),8080),Handler).serve_forever()
SUB_SERVER
chmod 644 /opt/vps-sub/server.py
# Explicit users and low-port capabilities, with group-readable secret files.
for pair in xray:vps-xray hysteria-server:vps-hy; do
  svc=${pair%%:*}; usr=${pair#*:}
  install -d -m 755 "/etc/systemd/system/$svc.service.d"
  cat > "/etc/systemd/system/$svc.service.d/90-vps-user.conf" <<UNIT
[Service]
User=$usr
Group=$usr
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=true
Restart=on-failure
RestartSec=3
LimitNOFILE=65536
UMask=0027
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
UNIT
done
cat > /etc/systemd/system/hysteria-server.service.d/95-vps-workdir.conf <<'HY_WORKDIR'
[Service]
StateDirectory=vps-hy
StateDirectoryMode=0750
WorkingDirectory=/var/lib/vps-hy
HY_WORKDIR
cat > /etc/systemd/system/vps-sub.service <<'SUB_UNIT'
[Unit]
Description=VPS private-path subscription service
After=network.target
[Service]
User=vps-sub
Group=vps-sub
ExecStart=/usr/bin/python3 /opt/vps-sub/server.py
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
TasksMax=64
MemoryMax=96M
[Install]
WantedBy=multi-user.target
SUB_UNIT
/usr/local/bin/xray run -test -config /usr/local/etc/xray/config.json
systemctl daemon-reload
systemctl enable --now xray hysteria-server vps-sub
# Confirm process state, both protocol sockets, and actual local subscription GET.
python3 <<'VERIFY'
import json, subprocess, time, urllib.request
from pathlib import Path
token = json.loads(Path('/etc/vps-sub/settings.json').read_text())['token']
for attempt in range(15):
    try:
        subprocess.run(['systemctl','is-active','--quiet','xray','hysteria-server','vps-sub'],check=True)
        tcp = subprocess.check_output(['ss','-H','-lntp','sport = :443'],text=True)
        udp = subprocess.check_output(['ss','-H','-lnup','sport = :443'],text=True)
        if 'xray' not in tcp or 'hysteria' not in udp: raise RuntimeError('节点尚未监听')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://127.0.0.1:8080/'+token+'/clash.yaml',timeout=3) as r:
            if r.read()!=Path('/root/vps-nodes/clash.yaml').read_bytes():
                raise RuntimeError('订阅内容不一致')
        break
    except Exception as error:
        if attempt==14:
            detail = str(error).replace(token, '[REDACTED]')
            print('失败阶段：', type(error).__name__, detail)
            subprocess.run(['systemctl','status','xray','hysteria-server','vps-sub','--no-pager','-l'])
            raise RuntimeError('本机验证失败，请查看以上服务状态及日志') from None
        time.sleep(1)
VERIFY
touch /root/vps-nodes/.deploy-complete
chmod 600 /root/vps-nodes/.deploy-complete
echo '本机服务与订阅检查通过。公网连通和客户端握手仍需客户端测试。'
echo '订阅地址（包含凭据，请勿公开）：'
cat /root/vps-nodes/subscription.txt
echo 'Clash 文件：/root/vps-nodes/clash.yaml'
echo '节点链接：/root/vps-nodes/links.txt'
echo '防火墙需放行：实际 SSH 端口/TCP、443/TCP、443/UDP、8080/TCP。脚本未更改防火墙。'
echo '维护菜单：重新运行入口且不带参数；命令行：vps-manage --help。'
echo '可选 HTTPS 使用 8443/TCP（80/TCP 用于证书），启用后订阅后端仅监听回环地址。'
