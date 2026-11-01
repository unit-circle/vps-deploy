#!/usr/bin/env python3
"""Explicit, backed-up maintenance for vps-deploy. Python standard library only."""
import argparse
from contextlib import contextmanager
import copy
import hashlib
import http.client
import io
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import secrets
import shutil
import socket
import stat
import ssl
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile

ROOT = Path('/')
SERVICES = ('xray', 'hysteria-server', 'vps-sub', 'vps-sub-https')
NETWORK_KEYS = ('net.core.rmem_max', 'net.core.wmem_max', 'net.ipv4.tcp_congestion_control')
MANAGED = (
    '/usr/local/etc/xray', '/etc/hysteria', '/root/vps-nodes', '/etc/vps-sub',
    '/opt/vps-sub', '/etc/systemd/system/xray.service',
    '/etc/systemd/system/hysteria-server.service',
    '/etc/systemd/system/hysteria-server@.service',
    '/etc/systemd/system/xray.service.d', '/etc/systemd/system/hysteria-server.service.d',
    '/etc/systemd/system/vps-sub.service', '/etc/systemd/system/vps-sub-https.service',
    '/usr/local/sbin/vps-nodes', '/usr/local/sbin/vps-manage',
    '/usr/local/bin/xray', '/usr/local/bin/hysteria', '/usr/local/bin/caddy',
    '/etc/sysctl.d/90-vps-deploy.conf', '/etc/vps-sub-https', '/var/lib/vps-sub-https',
)
XRAY = '/usr/local/etc/xray/config.json'
HY2 = '/etc/hysteria/config.yaml'
SETTINGS = '/etc/vps-sub/settings.json'
NETWORK_FILE = '/etc/sysctl.d/90-vps-deploy.conf'


def path(name):
    return ROOT / name.lstrip('/')


def command(args, timeout=30):
    """Never put untrusted program output or credentials into error messages."""
    result = subprocess.run([str(a) for a in args], capture_output=True, text=True,
                            timeout=timeout, check=False)
    if result.returncode:
        raise ValueError('Command failed: ' + str(args[0]) + '; inspect locally if needed')
    return result.stdout.strip()


def load(name):
    try:
        return json.loads(path(name).read_text(encoding='utf-8-sig'))
    except (ValueError, UnicodeError):
        raise ValueError('Expected project-generated JSON: ' + name + '; custom YAML needs manual review') from None


def encode(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def file_hash(source):
    digest = hashlib.sha256()
    with source.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def managed():
    if not path('/root/vps-nodes/.deploy-complete').is_file():
        raise ValueError('No completed project deployment; inspect installation before maintenance')
    for name in (XRAY, HY2, SETTINGS, '/root/vps-nodes/local-nodes.json'):
        if not path(name).is_file() or path(name).is_symlink():
            raise ValueError('Required regular file is missing: ' + name)


@contextmanager
def locked():
    import fcntl
    path('/run/lock').mkdir(parents=True, exist_ok=True)
    with path('/run/lock/vps-deploy.lock').open('a') as deploy:
        try:
            fcntl.flock(deploy, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another install or maintenance operation is running') from None
        # Coordinate backups and changes with the aggregation tool, too.
        with path('/root/vps-nodes/.nodes.lock').open('a') as nodes:
            os.chmod(nodes.name, 0o600)
            fcntl.flock(nodes, fcntl.LOCK_EX)
            yield


def active(service):
    return subprocess.run(['systemctl', 'is-active', '--quiet', service],
                          capture_output=True, timeout=10).returncode == 0


def states():
    return {name: active(name) for name in SERVICES}


def enabled(service):
    return subprocess.run(['systemctl', 'is-enabled', '--quiet', service],
                          capture_output=True, timeout=10).returncode == 0


def sysctl(key):
    return command(['sysctl', '-n', key], timeout=5)


def allowed(name):
    if not isinstance(name, str) or not name.startswith('/') or '\\' in name:
        return False
    parsed = PurePosixPath(name)
    if '..' in parsed.parts or str(parsed) != name:
        return False
    return any(name == root or name.startswith(root + '/') for root in MANAGED)


def regular(name):
    target = path(name)
    for part in (target, *target.parents):
        if part.is_symlink():
            raise ValueError('Symlinks are not supported in managed paths')
        if part == ROOT:
            break
    return target


def backup():
    base = regular('/root/vps-backups')
    base.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(base, 0o700)
    target = Path(tempfile.mkdtemp(prefix=time.strftime('%Y%m%dT%H%M%SZ-', time.gmtime()), dir=base))
    os.chmod(target, 0o700)
    entries = {}
    for root in MANAGED:
        source = regular(root)
        if not source.exists():
            continue
        sources = source.rglob('*') if source.is_dir() else [source]
        for item in sources:
            name = '/' + item.relative_to(ROOT).as_posix()
            regular(name)
            if item.is_dir() or '/backups/' in name or item.name.endswith('.lock'):
                continue
            if not item.is_file():
                raise ValueError('Unsupported managed file type')
            dest = target / 'files' / name.lstrip('/')
            dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with item.open('rb') as src, dest.open('xb') as out:
                shutil.copyfileobj(src, out)
            os.chmod(dest, 0o600)
            meta = item.stat()
            entries[name] = {'sha256':file_hash(dest),
                             'mode':stat.S_IMODE(meta.st_mode), 'uid':meta.st_uid, 'gid':meta.st_gid}
    values = {}
    for key in NETWORK_KEYS:
        try:
            values[key] = sysctl(key)
        except (OSError, ValueError):
            pass
    manifest = {'schema':1, 'files':entries, 'services':states(), 'sysctl':values,
                'enabled':{s:enabled(s) for s in SERVICES},
                'network_file_present':path(NETWORK_FILE).exists()}
    manifest_path = target / 'manifest.json'
    manifest_path.write_bytes(encode(manifest))
    os.chmod(manifest_path, 0o600)
    return target


def atomic(name, data, mode=None, owner=None):
    target = regular(name)
    target.parent.mkdir(parents=True, exist_ok=True)
    if name == '/etc/vps-sub-https/Caddyfile':
        os.chmod(target.parent, 0o755)
    previous = target.stat() if target.exists() else None
    fd, temporary = tempfile.mkstemp(prefix='.vps-manage-', dir=target.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            if isinstance(data, Path):
                with data.open('rb') as source:
                    shutil.copyfileobj(source, output)
            else:
                output.write(data)
            output.flush()
            os.fsync(output.fileno())
            os.fchmod(output.fileno(), mode if mode is not None else
                      stat.S_IMODE(previous.st_mode) if previous else 0o600)
            created = os.fstat(output.fileno())
            uid, gid = owner if owner is not None else ((previous.st_uid, previous.st_gid) if previous else (created.st_uid, created.st_gid))
            os.fchown(output.fileno(), uid, gid)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)


def reset_services(previous, enablement=None):
    command(['systemctl', 'daemon-reload'])
    for service, desired in (enablement or {}).items():
        if enabled(service) != desired:
            command(['systemctl', 'enable' if desired else 'disable', service])
    for service, running in previous.items():
        if running:
            command(['systemctl', 'restart', service])
        else:
            # Older deployments have no HTTPS unit to stop.
            subprocess.run(['systemctl', 'stop', service], capture_output=True, timeout=15)


def wait_services(names):
    stable = 0
    for attempt in range(15):
        if all(active(name) for name in names):
            stable += 1
            if stable >= 3:
                sockets_ok = True
                for service, flag, process in [('xray','-lntp','xray'), ('hysteria-server','-lnup','hysteria')]:
                    if service in names:
                        sockets_ok &= process in command(['ss', '-H', flag, 'sport = :443'])
                if sockets_ok:
                    return
        else:
            stable = 0
        time.sleep(1)
    raise ValueError('A service did not remain active after the change')


def xray_test():
    command([path('/usr/local/bin/xray'), 'run', '-test', '-config', path(XRAY)])


def subscription_test():
    token = load(SETTINGS)['token']
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open('http://127.0.0.1:8080/' + token + '/clash.yaml', timeout=5) as response:
            if response.read() != path('/root/vps-nodes/clash.yaml').read_bytes():
                raise ValueError('Subscription content differs')
    except Exception:
        raise ValueError('Local subscription verification failed; secret URL withheld') from None


def https_test(domain):
    """Use loopback transport with normal certificate-chain and hostname validation."""
    connection = http.client.HTTPConnection('127.0.0.1', 8443, timeout=4)
    try:
        connection.sock = ssl.create_default_context().wrap_socket(
            socket.create_connection(('127.0.0.1', 8443), timeout=4), server_hostname=domain)
        connection.request('GET', '/' + load(SETTINGS)['token'] + '/clash.yaml', headers={'Host':domain})
        response = connection.getresponse()
        if response.status != 200 or response.read() != path('/root/vps-nodes/clash.yaml').read_bytes():
            raise ValueError('HTTPS subscription content differs')
    finally:
        connection.close()


def transactional(changes, finish, modes=None, owners=None, rollback_runtime=None):
    """Restore exactly the touched files and previous service state on failure."""
    if not all(allowed(name) for name in changes):
        raise ValueError('Change contains a path outside managed files')
    saved = backup()
    previous_services = states()
    previous_enabled = {s:enabled(s) for s in SERVICES}
    originals = {}
    for name in changes:
        target = regular(name)
        originals[name] = (saved/'files'/name.lstrip('/'), target.stat()) if target.exists() else (None, None)
    try:
        for name, data in changes.items():
            if data is None:
                regular(name).unlink(missing_ok=True)
            else:
                atomic(name, data, (modes or {}).get(name), (owners or {}).get(name))
        finish()
    except BaseException:
        errors = []
        for name, (data, meta) in reversed(list(originals.items())):
            try:
                if data is None:
                    regular(name).unlink(missing_ok=True)
                else:
                    atomic(name, data, stat.S_IMODE(meta.st_mode), (meta.st_uid, meta.st_gid))
            except (OSError, ValueError):
                errors.append(name)
        try:
            if rollback_runtime:
                rollback_runtime()
        except (OSError, ValueError, subprocess.SubprocessError):
            errors.append('runtime settings')
        try:
            reset_services(previous_services, previous_enabled)
        except (OSError, ValueError, subprocess.SubprocessError):
            errors.append('service state')
        print('Change failed; rollback attempted. Private backup:', saved)
        if errors:
            raise ValueError('Rollback incomplete; inspect the private backup and service state') from None
        raise
    print('Private backup:', saved)
    return saved


def ipv4_configs(xray, hy2):
    xray, hy2 = copy.deepcopy(xray), copy.deepcopy(hy2)
    direct = [o for o in xray.get('outbounds', []) if o.get('tag') == 'direct' and o.get('protocol') == 'freedom']
    if len(direct) != 1:
        raise ValueError('Expected exactly one Xray direct/freedom outbound')
    direct[0].setdefault('streamSettings', {}).setdefault('sockopt', {})['domainStrategy'] = 'ForceIPv4'
    outbounds = hy2.get('outbounds') or []
    if hy2.get('acl') or len(outbounds) > 1 or (outbounds and outbounds[0].get('type') != 'direct'):
        raise ValueError('Custom Hysteria2 ACL/outbounds found; manual review required')
    if not outbounds:
        outbounds = [{'name':'direct', 'type':'direct'}]
        hy2['outbounds'] = outbounds
    outbounds[0].setdefault('direct', {})['mode'] = '4'
    return xray, hy2


def update(apply=False):
    old_x, old_h = load(XRAY), load(HY2)
    new_x, new_h = ipv4_configs(old_x, old_h)
    changes = {name:encode(new) for name, old, new in [(XRAY, old_x, new_x), (HY2, old_h, new_h)] if old != new}
    backend = '/opt/vps-sub/server.py'
    source = path(backend).read_text()
    old_bind = "ThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever()"
    new_bind = "ThreadingHTTPServer((settings.get('listen','0.0.0.0'),8080),Handler).serve_forever()"
    if source.count(old_bind) == 1:
        changes[backend] = source.replace(old_bind, new_bind).encode()
    print('Migration: IPv4 outbounds and optional loopback binding support for the project subscription backend.')
    if not changes:
        print('Already configured; no changes.')
        return
    if not apply:
        print('Preview only. Add --apply to back up, validate, restart and roll back on failure.')
        return
    if not all(active(s) for s in SERVICES[:3]):
        raise ValueError('The three existing services must be active before migration')
    def finish():
        xray_test()
        command(['systemctl', 'restart', 'xray', 'hysteria-server'])
        wait_services(SERVICES[:3])
        subscription_test()
    transactional(changes, finish)


def network_plan(current, available, bbr=False):
    result = {key:str(max(int(current[key]), 16777216)) for key in NETWORK_KEYS[:2]}
    if bbr:
        if 'bbr' not in available.split():
            raise ValueError('This kernel does not report BBR support; no kernel/module changes made')
        result[NETWORK_KEYS[2]] = 'bbr'
    return result


def apply_sysctl(values):
    errors = []
    for key, value in values.items():
        try:
            command(['sysctl', '-w', key + '=' + str(value)])
        except (OSError, ValueError, subprocess.SubprocessError):
            errors.append(key)
    if errors:
        raise ValueError('Could not apply network settings: ' + ', '.join(errors))


def network(apply=False, bbr=False):
    current = {key:sysctl(key) for key in NETWORK_KEYS}
    plan = network_plan(current, sysctl('net.ipv4.tcp_available_congestion_control'), bbr)
    for key, value in plan.items():
        print(key + ': ' + current[key] + ' -> ' + value)
    print('No changes to DNS, IPv6, MTU, firewall, kernel or the current interface queue.')
    if not apply:
        print('Preview only. Add --apply to persist and apply these settings.')
        return
    if path(NETWORK_FILE).exists() and not path(NETWORK_FILE).read_text().startswith('# Managed by vps-deploy\n'):
        raise ValueError('Existing tuning file is not managed by this project')
    # Keep the previously selected BBR choice when only refreshing buffers.
    if not bbr and path(NETWORK_FILE).exists() and 'net.ipv4.tcp_congestion_control=bbr' in path(NETWORK_FILE).read_text():
        plan[NETWORK_KEYS[2]] = current[NETWORK_KEYS[2]]
    content = '# Managed by vps-deploy\n' + ''.join(key + '=' + value + '\n' for key, value in plan.items())
    def finish():
        apply_sysctl(plan)
    transactional({NETWORK_FILE:content.encode()}, finish, {NETWORK_FILE:0o644},
                  rollback_runtime=lambda:apply_sysctl({k:current[k] for k in plan}))
    print('Settings applied. A larger maximum buffer is a limit, not preallocated memory.')


def caddy_config(domain, email):
    domain = domain.lower().rstrip('.')
    if len(domain) > 253 or '.' not in domain or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in domain.split('.')):
        raise ValueError('Use a public DNS hostname without a scheme, port or path')
    try:
        ipaddress.ip_address(domain)
    except ValueError:
        pass
    else:
        raise ValueError('A domain name is required for this HTTPS workflow')
    if not re.fullmatch(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', email):
        raise ValueError('A valid ACME contact email is required')
    # No secret token is embedded in the Caddyfile. Backend authenticates all routes.
    return ('''{
    admin off
    auto_https disable_redirects
    log {
        output discard
    }
    servers {
        protocols h1 h2
    }
}
https://''' + domain + ''':8443 {
    tls {
        issuer acme {
            email ''' + email + '''
            dir https://acme-v02.api.letsencrypt.org/directory
            disable_tlsalpn_challenge
        }
    }
    reverse_proxy 127.0.0.1:8080
}
''').encode()


HTTPS_UNIT = b'''[Unit]
Description=VPS subscription HTTPS (8443; ACME HTTP-01 on 80)
After=network-online.target vps-sub.service
Wants=network-online.target
[Service]
User=vps-sub
Group=vps-sub
ExecStart=/usr/local/bin/caddy run --config /etc/vps-sub-https/Caddyfile --adapter caddyfile
Environment=XDG_DATA_HOME=/var/lib/vps-sub-https/data
Environment=XDG_CONFIG_HOME=/var/lib/vps-sub-https/config
StateDirectory=vps-sub-https
StateDirectoryMode=0700
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
NoNewPrivileges=true
ProtectHome=true
ProtectSystem=strict
PrivateTmp=true
Restart=on-failure
RestartSec=5
UMask=0077
[Install]
WantedBy=multi-user.target
'''


def https(domain, email, apply=False):
    config = caddy_config(domain, email)
    domain = domain.lower().rstrip('.')
    print('HTTPS subscription: TCP 8443; ACME HTTP-01: TCP 80; backend becomes 127.0.0.1:8080.')
    print('DNS must point directly to this VPS. No firewall rules or DNS records are changed.')
    if not apply:
        print('Preview only. Add --apply to enable HTTPS after installing a verified Caddy binary.')
        return
    if not path('/usr/local/bin/caddy').is_file():
        raise ValueError('Install Caddy with upgrade caddy --version vX.Y.Z --apply first')
    if path('/etc/vps-sub-https/Caddyfile').exists():
        raise ValueError('HTTPS is already configured; review or restore it before changing domains')
    native = load('/root/vps-nodes/local-nodes.json')['proxies']
    expected = {n['server'] for n in native}
    addresses = {a[4][0] for a in socket.getaddrinfo(domain, 80, socket.AF_INET, socket.SOCK_STREAM)}
    if addresses != expected:
        raise ValueError('All domain A records must match the native VPS IPv4 address')
    try:
        ipv6 = socket.getaddrinfo(domain, 80, socket.AF_INET6, socket.SOCK_STREAM)
    except socket.gaierror:
        ipv6 = []
    if ipv6:
        raise ValueError('This IPv4 HTTPS workflow requires no AAAA record for the subscription hostname')
    for port in (80, 8443):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(('0.0.0.0', port))
    settings = load(SETTINGS)
    settings.update(listen='127.0.0.1', https_domain=domain, https_port=8443)
    changes = {
        '/etc/vps-sub-https/Caddyfile':config,
        '/etc/systemd/system/vps-sub-https.service':HTTPS_UNIT,
        SETTINGS:encode(settings),
        '/root/vps-nodes/subscription.txt':('https://' + domain + ':8443/' + settings['token'] + '/clash.yaml\n').encode(),
    }
    # Existing subscription servers must support the bind setting before exposure is closed.
    if "settings.get('listen'" not in path('/opt/vps-sub/server.py').read_text():
        raise ValueError('Legacy subscription backend: install the reviewed current server.py before HTTPS migration')
    def finish():
        command([path('/usr/local/bin/caddy'), 'validate', '--config', path('/etc/vps-sub-https/Caddyfile'), '--adapter', 'caddyfile'])
        command(['systemctl', 'daemon-reload'])
        command(['systemctl', 'restart', 'vps-sub'])
        subscription_test()
        command(['systemctl', 'start', 'vps-sub-https'])
        wait_services(('vps-sub', 'vps-sub-https'))
        # Verify trust, hostname and body before accepting the URL; no certificate bypass.
        verified = False
        for attempt in range(24):
            try:
                https_test(domain)
                verified = True
                break
            except (OSError, ValueError, http.client.HTTPException):
                pass
            time.sleep(1)
        if not verified:
            raise ValueError('Trusted HTTPS verification failed; check A record and external TCP 80/8443')
        command(['systemctl', 'enable', 'vps-sub-https'])
    transactional(changes, finish, {'/etc/vps-sub-https/Caddyfile':0o644,
                                  '/etc/systemd/system/vps-sub-https.service':0o644})
    print('Trusted HTTPS verified. Refresh clients using subscription.txt; public HTTP backend is closed.')


def release_asset(component, version, machine):
    arch = {'x86_64':'amd64', 'aarch64':'arm64'}.get(machine)
    if not arch or not re.fullmatch(r'v\d+\.\d+\.\d+(?:\.\d+)?', version):
        raise ValueError('Use an explicit stable vX.Y.Z version on x86_64/aarch64')
    if component == 'xray':
        return 'XTLS/Xray-core', 'Xray-linux-' + ('64' if arch == 'amd64' else 'arm64-v8a') + '.zip', 'xray'
    if component == 'hysteria':
        return 'apernet/hysteria', 'hysteria-linux-' + arch, None
    if component == 'caddy':
        return 'caddyserver/caddy', 'caddy_' + version[1:] + '_linux_' + arch + '.tar.gz', 'caddy'
    raise ValueError('Unknown component')


def fetch_json(url):
    request = urllib.request.Request(url, headers={'User-Agent':'vps-deploy', 'Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def upgrade(component, version, apply=False, checksum=None):
    repo, name, member = release_asset(component, version, platform.machine())
    release = fetch_json('https://api.github.com/repos/' + repo + '/releases/tags/' + version)
    if release.get('draft') or release.get('prerelease'):
        raise ValueError('Prerelease/draft versions are not accepted')
    matches = [a for a in release.get('assets', []) if a.get('name') == name]
    if len(matches) != 1:
        raise ValueError('Expected official release asset was not found')
    asset = matches[0]
    digest = asset.get('digest') or ''
    published = digest.removeprefix('sha256:') if digest.startswith('sha256:') else None
    expected = checksum or published
    if not expected or not re.fullmatch(r'[0-9a-fA-F]{64}', expected):
        raise ValueError('Release has no SHA256 digest; supply --sha256 from an independently checked official checksum')
    if checksum and published and checksum.lower() != published.lower():
        raise ValueError('Provided checksum differs from the official asset digest')
    url = asset['browser_download_url']
    if not url.startswith('https://github.com/' + repo + '/releases/download/'):
        raise ValueError('Unexpected release download URL')
    print('Explicit binary version:', component, version, name)
    print('Expected SHA256:', expected.lower())
    if not apply:
        print('Preview only. Add --apply to download, verify, back up and replace this binary.')
        return
    target = '/usr/local/bin/' + component
    if component != 'caddy' and not path(target).is_file():
        raise ValueError('Existing binary is missing; use fresh installation first')
    with urllib.request.urlopen(url, timeout=30) as response:
        data = response.read(128 * 1024 * 1024 + 1)
    if len(data) > 128 * 1024 * 1024 or hashlib.sha256(data).hexdigest() != expected.lower():
        raise ValueError('Release size/checksum verification failed')
    if name.endswith('.zip'):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if archive.getinfo(member).file_size > 128 * 1024 * 1024:
                raise ValueError('Oversized executable')
            binary = archive.read(member)
    elif name.endswith('.tar.gz'):
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
            info = archive.getmember(member)
            if not info.isfile() or info.size > 128 * 1024 * 1024:
                raise ValueError('Invalid executable in release')
            binary = archive.extractfile(info).read()
    else:
        binary = data
    service = {'xray':'xray', 'hysteria':'hysteria-server', 'caddy':'vps-sub-https'}[component]
    was_active = active(service)
    def finish():
        output = command([path(target), 'version'])
        if version[1:] not in output:
            raise ValueError('Installed binary did not report the requested version')
        if component == 'xray':
            xray_test()
        if was_active:
            command(['systemctl', 'restart', service])
            wait_services((service,))
        if active('vps-sub'):
            subscription_test()
    changes = {target:binary}
    record = '/root/vps-nodes/deployment.json'
    if path(record).is_file():
        metadata = load(record)
        metadata.setdefault('installed_versions', {})[component] = version
        metadata['last_verified_asset_sha256'] = expected.lower()
        changes[record] = encode(metadata)
    transactional(changes, finish, {target:0o755})
    print('Requested binary installed; credentials and configurations preserved.')


def check(google=False):
    ok = True
    for service in SERVICES[:3]:
        running = active(service)
        print(service + ': ' + ('active' if running else 'inactive'))
        ok &= running
    for transport, process in (('tcp', 'xray'), ('udp', 'hysteria')):
        output = command(['ss', '-H', '-lntp' if transport == 'tcp' else '-lnup', 'sport = :443'])
        listening = process in output
        print(transport + '/443: ' + ('listening' if listening else 'missing'))
        ok &= listening
    x, h = load(XRAY), load(HY2)
    expected_x, expected_h = ipv4_configs(x, h)
    configured = x == expected_x and h == expected_h
    print('IPv4 outbound settings: ' + ('configured' if configured else 'migration available'))
    ok &= configured
    for name in (XRAY, HY2, SETTINGS, '/etc/hysteria/server.key',
                 '/etc/vps-sub/clash.yaml', '/root/vps-nodes/local-nodes.json'):
        meta = path(name).stat()
        private = stat.S_IMODE(meta.st_mode) & 0o037 == 0 and meta.st_uid == 0
        print(name + ': ' + ('restricted' if private else 'world permissions found'))
        ok &= private
    xray_test()
    subscription_test()
    print('Xray configuration and local subscription: OK')
    certificate_ok = subprocess.run(['openssl', 'x509', '-checkend', '2592000', '-noout',
        '-in', str(path('/etc/hysteria/server.crt'))], capture_output=True, timeout=10).returncode == 0
    print('HY2 certificate valid for the next 30 days: ' + str(certificate_ok))
    ok &= certificate_ok
    fingerprint = command(['openssl', 'x509', '-noout', '-fingerprint', '-sha256',
                           '-in', path('/etc/hysteria/server.crt')]).split('=', 1)[-1].replace(':', '').lower()
    native = load('/root/vps-nodes/local-nodes.json')['proxies']
    pinned = [n for n in native if n.get('type') == 'hysteria2']
    pin_ok = bool(pinned) and all(n.get('fingerprint', '').replace(':', '').lower() == fingerprint
                                and n.get('password') == h.get('auth', {}).get('password') for n in pinned)
    reality_ids = {c.get('id') for inbound in x.get('inbounds', [])
                   if inbound.get('streamSettings', {}).get('security') == 'reality'
                   for c in inbound.get('settings', {}).get('clients', [])}
    vless = [n for n in native if n.get('type') == 'vless']
    reality_ok = bool(vless) and all(n.get('tls') is True and n.get('uuid') in reality_ids for n in vless)
    print('HY2 certificate pin/password and Reality client consistency: ' + str(pin_ok and reality_ok))
    ok &= pin_ok and reality_ok
    if load(SETTINGS).get('https_domain'):
        print('HTTPS service: ' + ('active' if active('vps-sub-https') else 'inactive'))
        ok &= active('vps-sub-https')
        try:
            https_test(load(SETTINGS)['https_domain'])
            print('HTTPS trust, hostname and content: OK')
        except (OSError, ValueError, http.client.HTTPException):
            print('HTTPS trust, hostname or content check failed')
            ok = False
    if google:
        print('Google diagnostics test native VPS IPv4, not a complete client proxy handshake.')
        for host, route in [('www.google.com','/generate_204'), ('accounts.google.com','/'), ('www.gstatic.com','/generate_204')]:
            try:
                answers = socket.getaddrinfo(host, 443, socket.AF_INET, socket.SOCK_STREAM)
                code = command(['curl', '-4', '--noproxy', '*', '--connect-timeout', '5', '--max-time', '10',
                    '--silent', '--show-error', '-o', '/dev/null', '-w', '%{http_code}', 'https://' + host + route], timeout=15)
                print(host + ': IPv4 DNS=' + str(len({a[4][0] for a in answers})) + ', HTTPS=' + code)
                ok &= code.isdigit() and 200 <= int(code) < 400
            except (OSError, ValueError, subprocess.SubprocessError):
                print(host + ': IPv4 DNS/HTTPS check failed')
                ok = False
        print('IP reputation, Google location and account behavior require client-side verification.')
    return ok


def restore(directory, apply=False):
    if directory.is_symlink():
        raise ValueError('Snapshot directory must not be a symlink')
    directory = directory.resolve()
    base = path('/root/vps-backups').resolve()
    if directory.parent != base or directory.is_symlink():
        raise ValueError('Choose a direct snapshot directory under /root/vps-backups')
    manifest = json.loads((directory / 'manifest.json').read_text())
    if manifest.get('schema') != 1 or not manifest.get('files'):
        raise ValueError('Unsupported/empty snapshot')
    changes, modes, owners = {}, {}, {}
    for name, meta in manifest['files'].items():
        if not allowed(name):
            raise ValueError('Snapshot contains a path outside managed files')
        source = directory / 'files' / name.lstrip('/')
        if source.is_symlink() or not source.resolve().is_relative_to(directory / 'files'):
            raise ValueError('Invalid snapshot file path')
        if file_hash(source) != meta['sha256']:
            raise ValueError('Snapshot checksum mismatch; no files restored')
        if not isinstance(meta['mode'], int) or meta['mode'] & ~0o777:
            raise ValueError('Invalid snapshot file mode')
        changes[name], modes[name] = source, meta['mode']
        owners[name] = (meta['uid'], meta['gid'])
    if not manifest.get('network_file_present', True) and path(NETWORK_FILE).exists():
        if not path(NETWORK_FILE).read_text().startswith('# Managed by vps-deploy\n'):
            raise ValueError('Current network tuning file is not project-managed')
        changes[NETWORK_FILE] = None
    print('Verified snapshot:', directory, '; files:', len(changes))
    print('Restores saved files; does not delete files created after the snapshot.')
    if not apply:
        print('Preview only. Add --apply to back up the present state and restore.')
        return
    previous_network = {key:sysctl(key) for key in NETWORK_KEYS}
    values = manifest.get('sysctl', {})
    for key, value in values.items():
        if key not in NETWORK_KEYS or not re.fullmatch(r'[a-z0-9_]+', str(value)):
            raise ValueError('Invalid network value in snapshot')
    def finish():
        xray_test()
        apply_sysctl(values)
        reset_services({s:bool(manifest.get('services', {}).get(s)) for s in SERVICES},
                       {s:bool(manifest.get('enabled', {}).get(s)) for s in SERVICES})
        wait_services([s for s in SERVICES[:3] if manifest.get('services', {}).get(s)])
        if manifest.get('services', {}).get('vps-sub'):
            subscription_test()
    transactional(changes, finish, modes, owners, rollback_runtime=lambda:apply_sysctl(previous_network))


def parser():
    p = argparse.ArgumentParser(description='Backed-up VPS maintenance; mutating actions require --apply')
    sub = p.add_subparsers(dest='action', required=True)
    c = sub.add_parser('check'); c.add_argument('--google', action='store_true')
    sub.add_parser('backup')
    for name in ('update', 'network', 'https', 'upgrade', 'restore'):
        c = sub.add_parser(name); c.add_argument('--apply', action='store_true')
        if name == 'network': c.add_argument('--bbr', action='store_true')
        if name == 'https':
            c.add_argument('--domain', required=True); c.add_argument('--email', required=True)
        if name == 'upgrade':
            c.add_argument('component', choices=('xray', 'hysteria', 'caddy'))
            c.add_argument('--version', required=True); c.add_argument('--sha256')
        if name == 'restore': c.add_argument('directory', type=Path)
    return p


def main():
    args = parser().parse_args()
    try:
        if platform.system() != 'Linux' or os.geteuid() != 0:
            raise ValueError('Run as root on the managed Linux VPS')
        os.umask(0o077)
        managed()
        if args.action == 'check':
            return 0 if check(args.google) else 1
        with locked():
            if args.action == 'backup': print('Private backup:', backup())
            elif args.action == 'update': update(args.apply)
            elif args.action == 'network': network(args.apply, args.bbr)
            elif args.action == 'https': https(args.domain, args.email, args.apply)
            elif args.action == 'upgrade': upgrade(args.component, args.version, args.apply, args.sha256)
            elif args.action == 'restore': restore(args.directory, args.apply)
        return 0
    except ValueError as error:
        print('Error:', error, file=sys.stderr)
    except (OSError, KeyError, TypeError, subprocess.SubprocessError, json.JSONDecodeError, tarfile.TarError, zipfile.BadZipFile):
        print('Operation failed. Check files, permissions, network and service state; sensitive output withheld.', file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
