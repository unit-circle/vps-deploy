# VPS Deploy

[简体中文](README.md) | **English**

Deploy **VLESS Reality + Hysteria2** on a fresh Ubuntu / Debian VPS, generate a Clash / Mihomo subscription, and combine nodes from multiple VPS instances behind one stable subscription URL.

> Status: local configuration, subscription-service and aggregation tests completed. The current repository version has not completed end-to-end acceptance on a real VPS. Start with a fresh server without important data. This is not an official Evoxt product.

## Start here

| Goal | Guide |
|---|---|
| From an Evoxt account to a working client | [Evoxt beginner guide](docs/evoxt.en.md) |
| Several VPS instances in one subscription | [Multi-server guide](docs/multi-server.en.md) |
| Chinese documentation | [中文 README](README.md) |
| Installation or connectivity issues | [Troubleshooting](docs/evoxt.en.md#troubleshooting-and-lessons-learned) |

## Features and limits

- Two native nodes per VPS: VLESS Reality / Vision on TCP 443 and Hysteria2 on UDP 443.
- Random UUID, Reality keys, HY2 password and subscription path. HY2 uses a self-signed certificate with certificate pinning.
- Official Xray / Hysteria installers, dedicated service accounts, explicit permissions and systemd startup.
- Custom labels such as `Tokyo-VLESS` and `Seoul-HY2`.
- `vps-nodes` imports, replaces and removes remote node snapshots without changing the hub subscription URL.
- Aggregation only combines client configuration. It does **not** provision remote VPS instances, relay their traffic or combine their bandwidth.
- Default routing is `MATCH,PROXY`; no regional split routing, automatic latency groups, per-user quotas or web panel.
- No automatic firewall changes, overwriting of existing deployments or in-place upgrades.

## Requirements

Intended for fresh Ubuntu 22.04 / 24.04 or Debian 12 / 13 with systemd, root access, a public IPv4 address and access to GitHub. Ubuntu 24.04 x86_64 is the preferred starting point. Other architectures and releases have not been verified by this project.

Ensure `curl`, `python3` and `flock` exist. If needed:

```bash
apt-get update && apt-get install -y curl ca-certificates python3 util-linux
```

## One-command deployment

Connect by SSH and run as root. Replace `YOUR_PUBLIC_IPV4` with the VPS public IPv4; choose a label instead of `Tokyo` if desired.

```bash
curl --proto '=https' --tlsv1.2 -fL --retry 3 https://raw.githubusercontent.com/unit-circle/vps-deploy/main/deploy-vps.sh -o /root/deploy-vps.sh && bash /root/deploy-vps.sh YOUR_PUBLIC_IPV4 "Tokyo"
```

This downloads a file before executing it. Review the script first. For a reproducible project version, download and verify the entire repository at one commit; pinning only the entry script does not pin its companion tool, which otherwise follows `main`. Upstream installers and binaries currently use their stable versions at execution time.

Do not rerun deployment to add nodes to an existing host. IP changes, incomplete installations and legacy migrations require inspecting the current state and backing it up first.

## Required inbound firewall rules

| Protocol | Port | Purpose |
|---|---:|---|
| TCP | 22 or your actual SSH port | Administration |
| TCP | 443 | VLESS Reality |
| UDP | 443 | Hysteria2 |
| TCP | 8080 | HTTP subscription download |

TCP 443 and UDP 443 are separate rules. If both the cloud firewall and UFW are enabled, allow traffic in both. Restrict SSH to your own public IP when practical; node ports must allow client source IPs. TCP 80 is unnecessary for the default setup. No separate port purchase is required.

## Use the deployment

```bash
# Three active results indicate running services, not verified public proxy handshakes
systemctl is-active xray hysteria-server vps-sub

# Print the secret subscription URL
cat /root/vps-nodes/subscription.txt

# List source counts without credentials
vps-nodes list
```

Add a remote subscription in Clash Verge or another Mihomo client, paste the actual URL, update and activate it. Select the `PROXY` group, test VLESS and HY2 separately, then enable the client system proxy. TUN is optional for initial testing.

## Multiple servers, one subscription

Deploy both A (the subscription hub) and B (the added server) first. On B:

```bash
vps-nodes export /root/b-native.json
```

On A, replace `B_PUBLIC_IPV4`:

```bash
scp root@B_PUBLIC_IPV4:/root/b-native.json /root/b-native.json
vps-nodes import tokyo /root/b-native.json
vps-nodes list
```

A now publishes four nodes instead of two at the same URL. Update **A's subscription** in the client. Import C for six nodes. These JSON exports contain credentials and must never be committed to GitHub.

To refresh B, export to a fresh filename, copy it to A and import with the same source ID. This replaces B's snapshot instead of appending duplicates. Synchronization is manual; see the [full guide](docs/multi-server.en.md).

## Files, maintenance and security

| Path | Contents |
|---|---|
| `/root/vps-nodes/subscription.txt` | Secret subscription URL |
| `/root/vps-nodes/local-nodes.json` | Native nodes of this VPS |
| `/root/vps-nodes/clash.yaml` | Full aggregated client configuration |
| `/root/vps-nodes/sources/` | Imported remote snapshots |
| `/root/vps-nodes/backups/` | Private aggregation backups |
| `/root/vps-nodes/links.txt` | Two native share URIs; unaffected by aggregation |
| `/etc/vps-sub/clash.yaml` | Published subscription content |
| `/usr/local/etc/xray/config.json` | Xray server configuration |
| `/etc/hysteria/config.yaml` | HY2 server configuration |

Files ending in `.yaml` are emitted as JSON, which YAML readers can accept. The management tool only accepts the project's JSON exports, not arbitrary third-party YAML.

The random URL path is a credential. **HTTP does not encrypt subscription downloads.** HY2 pinning does not protect the HTTP subscription. For long-term use, put the endpoint behind trusted HTTPS on a domain you control and restrict public port 8080 after updating clients. This repository does not automatically configure HTTPS. Do not submit real URLs to public subscription-conversion services.

There is no automatic uninstaller. Reinstalling or deleting a VPS or its configuration loses credentials; back up privately first. Never commit real node exports, passwords, private keys or account information.

## Evoxt promotion

- Coupon: **to be supplied by the maintainer**.
- Referral link: **to be supplied**; any commission relationship will be disclosed.
- Discount, eligibility and expiration are governed by the checkout page and provider terms; they do not affect script functionality.
- No specific price, throughput or latency is promised.

## Local checks

```bash
bash -n deploy-vps.sh
python3 -m unittest discover -s tests -v
```

These do not replace real-VPS installation, public TCP / UDP reachability or client proxy-request tests. Upstream installers can change; retain the final error before attempting a fix instead of disabling firewalls or deleting configuration.

## References

- [Official Xray installer](https://github.com/XTLS/Xray-install)
- [Official Hysteria installer](https://v2.hysteria.network/docs/getting-started/Server-Installation-Script/)
- [Mihomo Hysteria2 configuration](https://wiki.metacubex.one/en/config/proxies/hysteria2/)
- [Official Evoxt deployment guide](https://evoxt.com/guides/how-to-deploy-a-evoxt-vm-with-10-simple-steps/)
- [Official Evoxt firewall guide](https://evoxt.com/evoxt/evoxt-firewall-guide/)

Documentation checked on 2026-10-23. Follow applicable laws and your provider's terms.
