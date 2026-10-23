#!/usr/bin/env python3
"""Local, snapshot-based multi-VPS subscription management. No network fetching."""
import argparse
import copy
import fcntl
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path

STATE = Path('/root/vps-nodes')
PUBLISHED = Path('/etc/vps-sub/clash.yaml')
MAX_BYTES = 2 * 1024 * 1024


def encode(obj):
    return (json.dumps(obj, ensure_ascii=False, indent=2) + '\n').encode()


def load(path):
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('Input is larger than 2 MiB')
    try:
        return json.loads(path.read_text())
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError('Expected JSON exported by this project; ordinary YAML is not accepted') from None


def validate(doc):
    if not isinstance(doc, dict) or not isinstance(doc.get('proxies'), list) or not doc['proxies']:
        raise ValueError('Expected a nonempty proxies array')
    if len(doc['proxies']) > 200:
        raise ValueError('Maximum 200 nodes per source')
    names = set()
    for n in doc['proxies']:
        if not isinstance(n, dict):
            raise ValueError('Each node must be an object')
        name = n.get('name')
        if not isinstance(name, str) or not name.strip() or len(name) > 128 or any(ord(c) < 32 for c in name):
            raise ValueError('Invalid node name')
        if name in names or name in {'DIRECT', 'REJECT', 'PROXY'}:
            raise ValueError('Duplicate or reserved node name')
        names.add(name)
        if not isinstance(n.get('server'), str) or not n['server'].strip():
            raise ValueError('Missing server address')
        if type(n.get('port')) is not int or not 1 <= n['port'] <= 65535:
            raise ValueError('Invalid node port')
        if n.get('type') == 'vless':
            opts = n.get('reality-opts')
            if not n.get('uuid') or n.get('tls') is not True or not isinstance(opts, dict) or not opts.get('public-key') or not opts.get('short-id'):
                raise ValueError('Incomplete VLESS Reality node')
        elif n.get('type') == 'hysteria2':
            if not n.get('password') or not n.get('fingerprint'):
                raise ValueError('Hysteria2 password and certificate fingerprint are required')
        else:
            raise ValueError('Only project VLESS Reality / Hysteria2 exports are supported')
    # Ignore rules, proxy-groups and other settings in imported files.
    return {'proxies': copy.deepcopy(doc['proxies'])}


def combine(base, local, sources):
    doc = copy.deepcopy(base)
    proxies = copy.deepcopy(local['proxies'])
    for source_id, snapshot in sorted(sources.items()):
        for n in snapshot['proxies']:
            node = copy.deepcopy(n)
            node['name'] = f'[{source_id}] {node["name"]}'
            proxies.append(node)
    if len(proxies) > 1000:
        raise ValueError('Maximum 1000 aggregated nodes')
    names = [n['name'] for n in proxies]
    if len(set(names)) != len(names):
        raise ValueError('Names collide after prefixing; choose another source ID')
    doc['proxies'] = proxies
    # This tool owns the PROXY group; routing rules remain unchanged.
    groups = [g for g in doc.get('proxy-groups', []) if g.get('name') != 'PROXY']
    groups.insert(0, {'name': 'PROXY', 'type': 'select', 'proxies': names + ['DIRECT']})
    doc['proxy-groups'] = groups
    return doc


def stage(path, data, metadata):
    fd, tmp = tempfile.mkstemp(prefix='.vps-nodes-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
            if metadata:
                os.fchown(f.fileno(), metadata.st_uid, metadata.st_gid)
            os.fchmod(f.fileno(), stat.S_IMODE(metadata.st_mode) if metadata else 0o600)
        return Path(tmp)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def transaction(changes):
    """Stage all files first, preserve modes/owners, back up and roll back failures."""
    backups = STATE / 'backups'
    backups.mkdir(mode=0o700, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix='subscription-', dir=backups))
    originals, staged, done = {}, {}, []
    try:
        for i, (path, data) in enumerate(changes.items()):
            meta = path.stat() if path.exists() else None
            old = path.read_bytes() if meta else None
            originals[path] = (old, meta)
            if old is not None:
                b = backup / f'{i}-{path.name}'
                b.write_bytes(old)
                b.chmod(0o600)
            if data is not None:
                staged[path] = stage(path, data, meta)
        for path, data in changes.items():
            if data is None:
                path.unlink(missing_ok=True)
            else:
                os.replace(staged[path], path)
            done.append(path)
    except BaseException:
        for path in reversed(done):
            old, meta = originals[path]
            if old is None:
                path.unlink(missing_ok=True)
            else:
                os.replace(stage(path, old, meta), path)
        raise
    finally:
        for tmp in staged.values():
            tmp.unlink(missing_ok=True)
    return backup


def parser():
    p = argparse.ArgumentParser(description='Manage one subscription containing multiple VPS nodes')
    commands = p.add_subparsers(dest='command', required=True)
    commands.add_parser('list', help='List sources and counts without credentials')
    commands.add_parser('url', help='Print the secret subscription URL')
    export = commands.add_parser('export', help='Export only this VPS native nodes to a private file')
    export.add_argument('file', type=Path)
    imp = commands.add_parser('import', help='Add or replace a source snapshot')
    imp.add_argument('source')
    imp.add_argument('file', type=Path)
    remove = commands.add_parser('remove', help='Remove a source from this subscription only')
    remove.add_argument('source')
    commands.add_parser('rebuild', help='Rebuild from local nodes and stored snapshots')
    return p


def run(args):
    if os.geteuid() != 0:
        raise ValueError('Run as root')
    if not PUBLISHED.is_file() or not (STATE / 'clash.yaml').is_file():
        raise ValueError('Deploy this VPS first; required subscription files are missing')
    # Serialize all commands so export cannot race with imports.
    with (STATE / '.nodes.lock').open('a') as lock:
        os.chmod(lock.name, 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        local_path = STATE / 'local-nodes.json'
        base = load(STATE / 'clash.yaml')
        if not local_path.is_file():
            raise ValueError('Missing local-nodes.json; follow the legacy migration section first')
        local = validate(load(local_path))
        sources_dir = STATE / 'sources'
        sources_dir.mkdir(mode=0o700, exist_ok=True)
        sources = {p.stem: validate(load(p)) for p in sorted(sources_dir.glob('*.json'))}
        if args.command == 'url':
            print((STATE / 'subscription.txt').read_text().strip())
            return
        if args.command == 'export':
            target = args.file.expanduser().absolute()
            if target.exists():
                raise ValueError('Export target already exists; choose a new private filename')
            # O_EXCL and mode 0600 prevent overwriting a config or following a symlink.
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as f:
                f.write(encode(local))
            print(f'Exported {len(local["proxies"])} native nodes to {target}; keep this file private')
            return
        if args.command == 'list':
            print(f'local: {len(local["proxies"])} nodes')
            for source, doc in sources.items():
                print(f'{source}: {len(doc["proxies"])} nodes')
            print('Total:', len(local['proxies']) + sum(len(d['proxies']) for d in sources.values()))
            return
        changes = {}
        if args.command in {'import', 'remove'}:
            if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,31}', args.source) or args.source == 'local':
                raise ValueError('Source ID: 1–32 letters/digits/_/-, cannot be local')
            source_path = sources_dir / (args.source + '.json')
            if args.command == 'import':
                sources[args.source] = validate(load(args.file))
                changes[source_path] = encode(sources[args.source])
            else:
                if args.source not in sources:
                    raise ValueError('Unknown source ID')
                del sources[args.source]
                changes[source_path] = None
        merged = combine(base, local, sources)
        data = encode(merged)
        changes[STATE / 'clash.yaml'] = data
        changes[PUBLISHED] = data
        backup = transaction(changes)
        print(f'Published {len(merged["proxies"])} nodes; URL and node credentials unchanged')
        print('Update the subscription in your client. Backup:', backup)


def main():
    args = parser().parse_args()
    try:
        run(args)
    except ValueError as error:
        print('Operation failed:', error, file=sys.stderr)
        return 1
    except (OSError, KeyError, TypeError):
        # Do not echo imported values, node credentials or a traceback.
        print('Operation failed. Check source ID, JSON format, required fields, file paths and permissions.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
