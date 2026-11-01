# VPS Deploy

[简体中文](README.md) | **English**

Deploy **VLESS Reality + Hysteria2** on a fresh Ubuntu / Debian VPS, generate a Clash / Mihomo subscription, and use a menu for checks, backups, configuration migrations and explicit-version upgrades.

The default keeps the VPS's native exit and selects IPv4 outbound traffic. Network tuning and subscription HTTPS are optional, explicit actions.

> Validation: local syntax, artifact-generation, subscription-service and maintenance-logic tests are available. The complete version still requires real-VPS installation, kernel-tuning and public ACME acceptance. This is not an official Evoxt product.

## Quick start

Connect to a fresh VPS by SSH as root and prepare the prerequisites:

```bash
apt-get update && apt-get install -y curl ca-certificates python3 util-linux
```

Download the launcher and open the menu:

```bash
curl --proto '=https' --tlsv1.2 -fL --retry 3 https://raw.githubusercontent.com/unit-circle/vps-deploy/main/bootstrap.sh -o /root/bootstrap-vps.sh && bash /root/bootstrap-vps.sh
```

The launcher downloads the deployment script and companion tools at **one Git commit**, records that revision and validates syntax. The local bundle remains available for review and reuse. Fresh installation still uses the official stable installers and records the installed versions. Pinning the project does not pin upstream software.

The parameter-based installation remains available:

```bash
bash /root/bootstrap-vps.sh YOUR_PUBLIC_IPV4 "Osaka"
```

Replace `YOUR_PUBLIC_IPV4` with the VPS public IPv4. Intended targets are Ubuntu 22.04 / 24.04 and Debian 12 / 13 with systemd; Ubuntu 24.04 is the preferred starting point. Existing configurations and credentials are never overwritten by installation. Other distributions, architectures and providers require real-host acceptance.

## Menu actions

| Action | Behavior |
|---|---|
| Fresh installation | Validate the OS, IP, label and ports; install both protocols and verify local services |
| Status and Google checks | Inspect services, sockets, IPv4 settings, permissions, certificate consistency and native IPv4 HTTPS |
| Private full backup | Save project configuration, credentials, certificates, tools, units and node binaries |
| IPv4 migration | Preserve existing fields while updating outbounds and adding optional backend loopback-binding support |
| Network tuning | Preview buffer maxima and optionally select BBR already available in the kernel |
| Optional subscription HTTPS | Trusted certificates with renewal on a dedicated TCP 8443 listener |
| Explicit-version upgrade | Select a stable Xray / Hysteria / Caddy version and verify SHA256 before replacing one binary |
| Restore backup | Verify a same-host snapshot, back up the present state and restore saved files |
| Show private subscription | Display the credential-bearing URL |

Configuration migrations, tuning, HTTPS, binary upgrades and restores preview first. Type `APPLY` in the menu to execute. On failure, the tool attempts to restore touched files and previous service state, retaining the backup location. A backup only creates local private files and does not require `--apply`.

## Encryption and subscriptions

- VLESS uses Reality / Vision. The `decryption: none` setting does not mean the Reality transport is unencrypted.
- Hysteria2 uses TLS and a random authentication password. Without a domain, clients must retain the self-signed certificate's `fingerprint` / URI `pinSHA256`; `skip-cert-verify` alone is not an authentication guarantee.
- Services use dedicated users, restricted file permissions and systemd protection options. Checks compare certificate validity, pins and native client credentials.
- **Default HTTP subscription downloads are not encrypted.** The random URL path authenticates requests but does not replace HTTPS. Without a domain, SSH can transfer the configuration for local import. Do not submit real subscriptions to public converters.

Optional HTTPS uses `https://your-subscription-domain:8443/random-path/clash.yaml`, preserving node TCP / UDP 443. Set only A records pointing directly to the VPS; this automated workflow requires no AAAA record for the subscription hostname. TCP 80 is used for ACME HTTP-01 issuance and renewal, and TCP 8443 serves subscriptions. DNS and firewall rules are not changed automatically.

Install a verified Caddy binary through the explicit-version menu, then choose HTTPS and supply a domain and ACME contact email. The tool verifies certificate trust, hostname and subscription contents before accepting the new URL. The backend becomes `127.0.0.1:8080`; clients must update their subscription URL. See [maintenance](docs/maintenance.en.md#optional-https).

## Networking and Google

Generated configurations include:

```json
{
  "protocol": "freedom",
  "tag": "direct",
  "streamSettings": {
    "sockopt": {"domainStrategy": "ForceIPv4"}
  }
}
```

```yaml
outbounds:
  - name: direct
    type: direct
    direct:
      mode: "4"
```

Xray applies this strategy to destination domain resolution, without falling back to IPv6 when no IPv4 result exists. It does not convert a literal IPv6 destination supplied by a client to IPv4. Hysteria2's `"4"` mode uses IPv4 only. [Xray reference](https://xtls.github.io/config/transports/sockopt.html), [Hysteria2 reference](https://v2.hysteria.network/docs/advanced/Full-Server-Config/#customizing-direct-outbound).

Tuning raises the relevant socket-buffer maxima to at least 16 MiB without lowering larger existing values. BBR is opt-in and requires reported kernel support. No kernel installation, active-interface queue replacement, IPv6 disabling or system DNS, MTU or firewall changes are performed. TCP BBR and Hysteria2 QUIC congestion control operate at different layers; larger values do not guarantee higher throughput. [Hysteria2 performance guide](https://v2.hysteria.network/docs/advanced/Performance/).

Google checks test IPv4 DNS and HTTPS responses from Google, Accounts and Gstatic through the **native VPS exit**. Clients must still test actual requests through VLESS and HY2 separately. Location can also depend on IP data, device location and account activity. The script does not falsify location, replace the exit or guarantee Gmail links or regional identification. [Google location help](https://support.google.com/websearch/answer/179386?hl=en).

## Required ports

| Protocol | Port | Purpose |
|---|---:|---|
| TCP | Actual SSH port, commonly 22 | Administration |
| TCP | 443 | VLESS Reality |
| UDP | 443 | Hysteria2 |
| TCP | 8080 | Default HTTP subscription; backend becomes loopback-only after HTTPS |
| TCP | 80 | Optional HTTPS certificate issuance and renewal |
| TCP | 8443 | Optional HTTPS subscription |

Allow the appropriate rules in both the cloud firewall and UFW if both are enabled. The script never changes these rules automatically. Public 8080 can be restricted after HTTPS is enabled.

## Use and maintenance

Add the subscription in Clash Verge / Mihomo, select the `PROXY` group and test VLESS and HY2 separately. TUN is optional for the first connection test.

Fresh installations provide:

```bash
vps-manage check --google
vps-manage backup
vps-manage update
vps-manage network
```

Migration and tuning previews do not restart services. Execute through menu confirmation or add `--apply` as described in [maintenance](docs/maintenance.en.md). There is no unversioned automatic upgrade; read the selected upstream release notes first.

On older deployments without `vps-manage`, download the launcher above and use its menu or `bash /root/bootstrap-vps.sh check --google`. Do not reinstall to migrate. Custom YAML, ACLs and complex outbounds can require manual review; the tool stops instead of rewriting unknown configurations.

## Multiple servers, one subscription

Deploy each server independently. Export B's native pair, then import on A:

```bash
# B
vps-nodes export /root/b-native.json

# A; replace B_PUBLIC_IPV4
scp root@B_PUBLIC_IPV4:/root/b-native.json /root/b-native.json
vps-nodes import tokyo /root/b-native.json
vps-nodes list
```

Refresh A's subscription for four nodes. Reusing a source ID replaces its snapshot. Aggregation only combines client configuration; it does not relay traffic, combine bandwidth or periodically synchronize remote nodes. Exports contain credentials. See the [aggregation guide](docs/multi-server.en.md).

## Files and restore limits

| Path | Contents |
|---|---|
| `/root/vps-nodes/subscription.txt` | Current secret subscription URL |
| `/root/vps-nodes/local-nodes.json` | Native nodes |
| `/root/vps-nodes/clash.yaml` | Aggregated client configuration |
| `/root/vps-nodes/deployment.json` | Initial versions and recent controlled upgrade metadata |
| `/usr/local/etc/xray/config.json` | Xray server configuration |
| `/etc/hysteria/` | HY2 configuration, certificate and private key |
| `/etc/vps-sub/` | Subscription settings and published configuration |
| `/etc/vps-sub-https/` | Optional Caddy configuration |
| `/etc/sysctl.d/90-vps-deploy.conf` | Optional network tuning |
| `/root/vps-backups/` | Private maintenance snapshots, including binaries and credentials |
| `/root/vps-nodes/backups/` | Aggregation-tool backups |

Project `.yaml` files contain JSON and require no YAML dependency. Maintenance does not automatically rewrite arbitrary third-party YAML.

Snapshots are root-readable file backups, **not encrypted disk images**, and may take tens to hundreds of MiB. Restoration targets the same deployed host, restores saved files and recorded network values, and does not recreate users or system dependencies or bulk-delete later files. A dedicated project tuning file is removed if absent in the snapshot. Encrypt backups separately before transferring them.

## Guides and checks

- [Evoxt account to client connection](docs/evoxt.en.md)
- [Maintenance, HTTPS, upgrades and restoration](docs/maintenance.en.md)
- [Multi-server aggregation](docs/multi-server.en.md)

```bash
bash -n bootstrap.sh
bash -n deploy-vps.sh
python3 -m unittest discover -s tests -v
```

On Windows, use `python -X utf8 -m unittest discover -s tests -v`. Tests locate Git for Windows Bash / OpenSSL and skip Linux ownership and aggregation-lock tests. GitHub Actions provides Ubuntu 22.04 / 24.04 checks. Unit tests do not install services, download node binaries or connect to existing VPS instances; they do not replace real-host acceptance.

## Evoxt promotion

Coupon and referral details await the maintainer. Any commission relationship will be disclosed. Actual terms and eligibility come from the provider checkout and do not affect script functionality.

Maintenance version: 2026-11-01. Never commit real nodes, passwords, private keys or subscription URLs.
