# Evoxt beginner deployment guide

[简体中文](evoxt.zh-CN.md) | **English** · [README](../README.en.md)

This walkthrough uses **Windows + a fresh Evoxt VPS + Ubuntu 24.04**. Do not install over an existing website, panel or proxy deployment. Replace every `YOUR_PUBLIC_IPV4` / `B_PUBLIC_IPV4` placeholder before using a command.

## 1. Basic terms

| Term | Meaning |
|---|---|
| VPS | A remote Linux server |
| SSH | A way to connect to and administer the server |
| root | The Linux administrator account |
| Node | An address, protocol and credentials used by a proxy client |
| Subscription | A URL that downloads client configuration containing one or more nodes |
| Hub A | A server publishing the combined subscription |

Two protocols on one VPS still share one machine and route. A separate VPS adds an independent server endpoint.

## 2. Create an Evoxt VPS

1. Visit [Evoxt](https://evoxt.com/), register and sign in yourself.
2. Open the deployment page and choose a region and plan. Region labels do not guarantee latency from your network; consult provider test IPs or support.
3. Select **Ubuntu 24.04**, rather than Windows or a preinstalled panel image.
4. Choose a recognizable hostname such as `proxy-tokyo-01`. Save your SSH key or the supplied access details.
5. Review the plan, billing cycle and final amount. If a coupon is available, confirm its effect before ordering.
6. Complete the order, wait for Online / Running, then record the public IPv4, SSH account and actual SSH port.

The maintainer has **not supplied a coupon or referral link yet**. Neither is required by the script. Never post root passwords or SSH private keys in Issues, screenshots or chat.

The UI may change; consult the [official Evoxt deployment guide](https://evoxt.com/guides/how-to-deploy-a-evoxt-vm-with-10-simple-steps/). This document makes no current price or stock guarantees.

## 3. Configure Evoxt's cloud firewall

Open the VPS management page and find Firewall. Confirm the SSH rule and an alternate console/VNC access method first. Evoxt documents that enabling its cloud firewall blocks other inbound protocols while adding TCP 22 for Linux administration. If SSH uses a different port, allow that actual port yourself.

Add and save these inbound accept rules:

| Action | Protocol | Destination port | Suggested source |
|---|---|---:|---|
| Allow / Accept | TCP | Actual SSH port, usually 22 | Your public IP when practical |
| Allow / Accept | TCP | 443 | `0.0.0.0/0` or client source IPs |
| Allow / Accept | UDP | 443 | `0.0.0.0/0` or client source IPs |
| Allow / Accept | TCP | 8080 | `0.0.0.0/0` or subscription-download source IPs |

Keep normal outbound access. TCP and UDP need separate rules. Allowing TCP 443 does not allow HY2. ICMP for ping is optional and has no port. This script listens on IPv4 only.

See the [official firewall guide](https://evoxt.com/evoxt/evoxt-firewall-guide/). Cloud rules and the VPS's UFW are separate layers.

## 4. Connect from Windows

Open **PowerShell** from the Start menu:

```powershell
ssh root@YOUR_PUBLIC_IPV4
```

For a custom SSH port such as 2222:

```powershell
ssh -p 2222 root@YOUR_PUBLIC_IPV4
```

On first connection, verify the host fingerprint against trusted console information before accepting. Password input is invisible; type it and press Enter. Do not copy prompt text such as `PS C:\...>` or `root@...:~#` into commands.

The prompt `root@hostname:~#` means you are connected. Run subsequent Bash commands there, not in local PowerShell after disconnecting. A non-root administrator should run `sudo -i` first.

Check the OS and install prerequisites:

```bash
cat /etc/os-release
apt-get update && apt-get install -y curl ca-certificates python3 util-linux
```

## 5. Download and deploy

The label identifies nodes; examples include `Tokyo` and `Seoul`. Replace the IP placeholder:

```bash
curl --proto '=https' --tlsv1.2 -fL --retry 3 https://raw.githubusercontent.com/unit-circle/vps-deploy/main/deploy-vps.sh -o /root/deploy-vps.sh && bash /root/deploy-vps.sh YOUR_PUBLIC_IPV4 "Tokyo"
```

To inspect the script first:

```bash
curl -fL --retry 3 https://raw.githubusercontent.com/unit-circle/vps-deploy/main/deploy-vps.sh -o /root/deploy-vps.sh
less /root/deploy-vps.sh
bash /root/deploy-vps.sh YOUR_PUBLIC_IPV4 "Tokyo"
```

Press `q` to leave `less`. Downloads take time. A completed download, Hysteria installation message or Xray `Configuration OK` alone does not indicate a complete deployment. Wait for final validation and do not run multiple installers at once.

The public address comes from the command argument; no external IP-detection site is used. Do not enter your computer's LAN address.

## 6. Optional Ubuntu UFW

If UFW is already enabled, allow the same ports. To enable it, keep the current SSH session open and allow your actual SSH port first:

```bash
apt-get install -y ufw
ufw allow 22/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw allow 8080/tcp
ufw default deny incoming
ufw default allow outgoing
ufw enable
ufw status verbose
```

Replace 22 if needed and answer `y` to the prompt. Test a second SSH connection before closing the original session. Do not disable every firewall as a connectivity test.

## 7. Verify services and obtain the subscription

```bash
systemctl is-active xray hysteria-server vps-sub
ss -lntp 'sport = :443'
ss -lnup 'sport = :443'
cat /root/vps-nodes/subscription.txt
```

Expect three `active` results, Xray on TCP 443 and Hysteria on UDP 443. The final command prints a secret HTTP URL. Do not publish it in screenshots.

If HTTP is temporarily inaccessible, download the configuration from Windows for a local-import diagnostic:

```powershell
scp root@YOUR_PUBLIC_IPV4:/root/vps-nodes/clash.yaml "$env:USERPROFILE\Desktop\vps-clash.yaml"
```

`scp` uses uppercase `-P` for a custom SSH port, for example `scp -P 2222 ...`. The downloaded file also contains credentials.

## 8. Configure Clash Verge / a Mihomo client

1. Install a trusted client from its official releases that supports VLESS Reality and Hysteria2. Old incompatible Clash builds will not work.
2. Open subscriptions / Profiles, add a remote subscription, paste the complete URL and save.
3. Update, select and activate it; labels may differ by client version.
4. In proxies, select `Tokyo-VLESS` in `PROXY` and test it; then test `Tokyo-HY2` separately.
5. After actual proxy requests work, enable the client system proxy. TUN is unnecessary for the initial check.
6. Open a target website to confirm real requests succeed. A latency number does not establish that all applications use the proxy.

There are no built-in country-based direct rules. Selecting `DIRECT` bypasses the proxy. System proxy / TUN controls which applications are captured. Applications with manually configured proxy ports may need updating; the generated local mixed port is 7890.

## 9. Add a second or third VPS

Deploy every new server separately, preferably with different labels. Pick one hub and follow the [multi-server guide](multi-server.en.md). The client can keep one hub subscription; there is no need for 3X-UI on each VPS.

## Troubleshooting and lessons learned

Collect current state and the last 30–60 error lines, without posting full private configuration:

```bash
systemctl status xray hysteria-server vps-sub --no-pager -l
journalctl -u xray -u hysteria-server -u vps-sub -n 60 --no-pager
ss -lntup | grep -E ':(443|8080)\b'
```

| Symptom | What to check |
|---|---|
| `unknown option -- -` | Upstream removed `-u`; this version omits it. Confirm the downloaded and executed file paths |
| HY2 `200/CHDIR` | Working-directory access failure; this version sets `/var/lib/vps-hy` with StateDirectory. Inspect the effective unit, rather than switching to root |
| `permission denied` | Identify the exact path and service user; do not apply 777 to keys |
| Key-output parsing failure | Upstream output may change. Four known public-key labels are handled; never publish raw `xray x25519` output |
| Existing configuration detected | Intentional protection. Back up and distinguish a running installation from partial files before modifying anything |
| Local checks pass, client times out | Check both firewalls, public IP, client capabilities and handshake logs |
| HY2 works but VLESS fails | UDP reachability does not prove TCP reachability; inspect TCP and Reality parameters |
| VLESS works but HY2 fails | Inspect UDP 443, HY2 service and the client's complete certificate fingerprint |
| Subscription download fails | Check TCP 8080, `vps-sub` and the full URL path. Changing HTTP to HTTPS does not add TLS |
| Different latency after changing regions | Provider/country labels do not guarantee routes; reinstalling cannot guarantee lower base network latency |

Windows TCP checks:

```powershell
Test-NetConnection YOUR_PUBLIC_IPV4 -Port 443
Test-NetConnection YOUR_PUBLIC_IPV4 -Port 8080
```

These do not test UDP. Use timestamps so old log errors are not mistaken for current failures.

## 10. Maintenance

- Services start at boot; normal VPS reboots do not require redeployment.
- IP or credential changes require updating client configuration and the hub's imported snapshots. There is no automatic IP-change command.
- Upstream upgrades may change installer flags, users, permissions or units. This project has no one-command upgrade; back up first.
- Protect subscription transport with trusted HTTPS for long-term use; never commit real subscriptions or submit them to public converters.
- Private backups must include credentials, certificate/key material and subscription settings. A README backup alone cannot restore nodes.

Documentation date: 2026-10-23. The current complete version has no real-VPS end-to-end acceptance record yet.
