# Multiple VPS instances in one subscription

[简体中文](multi-server.zh-CN.md) | **English** · [README](../README.en.md)

## Deployment and publishing are different

Deploying nodes installs proxy software on each VPS. Publishing a subscription gathers the client connection settings into one file. A subscription URL does not provision another VPS or install software on it.

Deploy two nodes each on A, B and C. A acts as the hub and imports B/C snapshots while retaining its native nodes. The client imports only A's URL to see six nodes. Proxy traffic goes directly to the selected node, not through A.

| Server | Native protocols | Role |
|---|---|---|
| A | VLESS + HY2 | Hub publishing all six A/B/C nodes |
| B | VLESS + HY2 | Additional endpoint; its native subscription is optional for the client |
| C | VLESS + HY2 | Additional endpoint; its native subscription is optional for the client |

The hub URL stays stable only while A's address/domain, port and random path stay unchanged. Changing A's IP does not magically update an IP-based URL. Trusted HTTPS on your own domain helps future migration but is not configured automatically here.

## 1. Deploy A and B separately

Run the README deployment command as root on each VPS. Use labels such as `Seoul` for A and `Tokyo` for B. Pass each server's own public IP.

Verify local services and an actual client handshake on both before merging. Aggregation does not repair a broken node.

## 2. Export native nodes on B

On B:

```bash
vps-nodes export /root/b-native.json
```

The export contains credentials and has mode 600. It includes only B's native nodes, even if B has previously imported C.

Export refuses an existing target to avoid overwrites. Use a fresh filename for later exports:

```bash
vps-nodes export /root/b-native-v2.json
```

## 3. Copy B's file securely to A

Run this **inside A's SSH session**, not on B or in local PowerShell:

```bash
scp root@B_PUBLIC_IPV4:/root/b-native.json /root/b-native.json
chmod 600 /root/b-native.json
```

Verify B's host fingerprint before accepting it. Authenticate with B's password or a previously configured SSH key. For a custom SSH port:

```bash
scp -P 2222 root@B_PUBLIC_IPV4:/root/b-native.json /root/b-native.json
```

No SSH private key belongs in GitHub. A does not need B's port 8080 for this transfer; it uses SSH. If server-to-server SSH is unavailable, transfer via your own computer using two `scp` operations and keep the files private.

## 4. Import on A and refresh the client

```bash
vps-nodes import tokyo /root/b-native.json
vps-nodes list
vps-nodes url
```

`tokyo` is a source ID: 1–32 letters, digits, underscores or hyphens, excluding `local`. Imported names receive a `[tokyo]` prefix to avoid collisions with native names.

A publishes four nodes at its existing URL. Update **A's subscription** in the client. Do not redeploy A or restart Xray/HY2. The subscription service reads the new file on the next request.

`vps-nodes list` prints source counts without credentials. `vps-nodes url` prints the secret URL; do not publish it.

## 5. Add C, refresh B or remove B

Export on C, copy its file to A, then on A:

```bash
vps-nodes import singapore /root/c-native.json
```

To refresh B, export a new file on B, copy it to A and use the **same source ID**:

```bash
vps-nodes import tokyo /root/b-native-v2.json
```

The existing source is replaced rather than duplicated. If B is reinstalled or its IP/keys change, update its snapshot. There is no scheduled remote polling.

To remove B from A's subscription:

```bash
vps-nodes remove tokyo
```

This removes A's stored snapshot and republishes the subscription. It does not uninstall B, stop its server or revoke its credentials. Clients must refresh; existing connections may continue.

To rebuild from native nodes and stored snapshots:

```bash
vps-nodes rebuild
```

The tool owns the `PROXY` group and rebuilds its member list. Existing hub routing rules remain; imported rules/groups are ignored. Do not expect manually added `PROXY` members to survive rebuilding.

## 6. Migrate an older deployment

If the previous `deploy-vps.sh` deployment works but lacks `vps-nodes`, do not redeploy the whole VPS. Download only the tool:

```bash
curl --proto '=https' --tlsv1.2 -fL --retry 3 https://raw.githubusercontent.com/unit-circle/vps-deploy/main/scripts/vps-nodes.py -o /root/vps-nodes-tool.py
python3 -m py_compile /root/vps-nodes-tool.py
install -m 755 /root/vps-nodes-tool.py /usr/local/sbin/vps-nodes
```

If the old configuration has never been aggregated, extract the native pair:

```bash
python3 <<'PY'
import json, os
from pathlib import Path
state = Path('/root/vps-nodes')
target = state / 'local-nodes.json'
if target.exists():
    raise SystemExit('local-nodes.json already exists; unchanged')
c = json.loads((state / 'clash.yaml').read_text())
nodes = c['proxies']
if len(nodes) != 2 or {n['type'] for n in nodes} != {'vless', 'hysteria2'}:
    raise SystemExit('Not the original native pair; migration stopped')
if len({n['server'] for n in nodes}) != 1:
    raise SystemExit('The pair does not share one server address; stopped')
fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as f:
    json.dump({'proxies': nodes}, f, ensure_ascii=False, indent=2)
print('Native snapshot created')
PY
```

You must independently confirm both nodes belong to this VPS before migrating. Do not use this extraction for previously merged or third-party configurations. Earlier `seoul-sub` / `/root/seoul-nodes/` layouts are different and are not migrated by these commands.

## 7. Backups and limits

- Imports/removals/rebuilds back up affected previous files under `/root/vps-nodes/backups/`. Backups contain credentials.
- Writes are staged, then replaced, preserving the published file's group and permissions. Failed replacement attempts roll back changed files. This is not a database transaction guarantee against power loss or filesystem failures.
- Invalid JSON, duplicate names and invalid source IDs are rejected before publication. Only project VLESS Reality/HY2 JSON is supported, up to 200 nodes per source and 1000 combined.
- `links.txt` still contains only the native two URIs; the full node list is in `clash.yaml` and the hub subscription.
- Snapshot merging is not scheduled synchronization, load balancing, combined bandwidth, account revocation or automatic failover.
- If A is unavailable, new subscription downloads fail. Previously cached configuration may still connect directly to B/C, depending on client behavior.
- The published endpoint remains HTTP. Secure SSH import does not protect the client's HTTP download; use trusted HTTPS for long-term service.

Scheduled synchronization or a panel requires separate future work and is not an existing capability.
