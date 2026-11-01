# Maintenance, network tuning and optional HTTPS

[README](../README.en.md) | [简体中文](maintenance.zh-CN.md)

Run these commands as root in the deployed VPS's SSH session. Downloading the repository does not modify the VPS. Use fresh installation only on a new host; choose maintenance for an existing deployment.

## Entry point and versions

Fresh installations include `vps-manage`. Older hosts can download `bootstrap.sh` from the README and run `bash /root/bootstrap-vps.sh` for the menu. Replace `vps-manage` in the examples with `bash /root/bootstrap-vps.sh` when using the downloaded launcher.

The launcher pins the deployment script and both tools to one commit:

```bash
VPS_DEPLOY_REF=YOUR_FULL_COMMIT_SHA bash /root/bootstrap-vps.sh
```

Replace the SHA. This does not pin upstream stable software used for fresh installation. `deployment.json` records initial project/software versions. The maintenance `upgrade` command requires an explicit stable version and verifies the official asset's SHA256 digest. If the release API has no digest, provide `--sha256` from independently checked official checksums.

## Check and back up first

```bash
vps-manage check --google
vps-manage backup
```

Checks cover services, TCP/UDP 443 sockets, Xray configuration, outbounds, sensitive-file permissions, HY2 certificate validity and native pin/credential consistency. The local subscription body must match the saved configuration. Configured HTTPS also checks certificate trust, hostname and body. UUIDs, passwords and secret URL paths are withheld.

Google diagnostics report IPv4 DNS and HTTPS status separately. A connectivity endpoint commonly returns 204, while Accounts may redirect. This is neither a public handshake test for both proxies nor a location assessment. Test each node in the client and inspect Google's location source. Client-resolved literal IPv6 addresses, browser permissions and account state need separate diagnosis.

Snapshots live under `/root/vps-backups/TIMESTAMP-random/`, with directories 700, files 600 and a SHA256 manifest. They include project configuration, native/aggregated nodes, certificates and private keys, tools, binaries and units. Nested aggregation-backup history and the entire OS are excluded. File copying is not a consistent disk snapshot; keep multiple working snapshots and recheck certificates and services after restoration.

## Migrate older deployments

```bash
vps-manage update
vps-manage update --apply
```

The first command previews; the second applies only these changes:

- Xray direct/freedom `streamSettings.sockopt.domainStrategy=ForceIPv4`.
- The default HY2 direct outbound's string `mode: "4"`.
- One original subscription-backend bind expression, allowing later loopback binding while retaining the default `0.0.0.0:8080`.

Other fields, ports, keys, passwords, certificates and subscription URLs remain intact. Existing core services must be active. Migration backs up, validates Xray, restarts node services and checks services/subscription, attempting rollback on failure. Third-party YAML, custom HY2 ACLs, multiple HY2 outbounds or ambiguous/missing Xray direct/freedom require manual review.

## Conservative network tuning

```bash
vps-manage network
vps-manage network --apply

# Optional: only when the kernel reports BBR availability
vps-manage network --bbr
vps-manage network --bbr --apply
```

Only `net.core.rmem_max` and `net.core.wmem_max` are raised to at least `16777216`. Opt-in BBR also sets `net.ipv4.tcp_congestion_control`. The dedicated persistent file is `/etc/sysctl.d/90-vps-deploy.conf`; an existing file without the project marker is not overwritten.

Other sysctl files, kernels, modules, current interface queues, IPv6, system DNS, MTU and firewall rules are unchanged. TCP BBR does not control HY2 QUIC congestion. Compare the same node, time period and test object; performance depends on routing, CPU, loss and memory. Restoring the preceding snapshot reverts recorded runtime values and the dedicated project file.

## Optional HTTPS

1. Use a dedicated subscription hostname whose A records point only to this VPS. This workflow requires no AAAA record for that hostname and direct DNS resolution.
2. Allow TCP 80 for ACME HTTP-01 issuance/renewal and TCP 8443 for subscriptions. Node port 443 remains unchanged.
3. Select a stable version from [Caddy Releases](https://github.com/caddyserver/caddy/releases), install it through menu 7 or the commands below, and replace all placeholders.

```bash
vps-manage upgrade caddy --version YOUR_CADDY_VERSION
vps-manage upgrade caddy --version YOUR_CADDY_VERSION --apply
vps-manage https --domain sub.example.com --email admin@example.com
vps-manage https --domain sub.example.com --email admin@example.com --apply
```

Versions must use an explicit `vX.Y.Z`-style stable tag, not `latest`. Setup stops for conflicting listeners, mismatched DNS, missing Caddy or a legacy backend without loopback-binding support. Run `update` first for that backend.

The feature owns `/etc/vps-sub-https/Caddyfile` and `vps-sub-https.service`, leaving `/etc/caddy/Caddyfile` intact. Caddy runs as `vps-sub`, storing certificate data under `/var/lib/vps-sub-https/`. TLS-ALPN challenge is disabled to avoid TCP 443; HTTP-01 still requires public TCP 80. Only HTTP/1.1 and HTTP/2 are enabled, avoiding another UDP listener. Caddy log output is disabled to avoid secret request-path logging.

Issuance may take about two minutes. The tool verifies the normal certificate chain, hostname and body over loopback, without bypassing TLS checks. Failed verification attempts to restore the old URL, binding and service state. Successful setup restricts the backend to `127.0.0.1:8080` and publishes the new HTTPS URL.

```bash
cat /root/vps-nodes/subscription.txt
```

This displays a private URL. Replace the client's old subscription URL, then restrict public 8080. Repeated setup does not overwrite an existing HTTPS domain; back up and inspect existing certificates/configuration before changing it.

## Explicit-version upgrades and restoration

```bash
# Replace YOUR_VERSION with a tag from the official release
vps-manage upgrade xray --version YOUR_VERSION
vps-manage upgrade xray --version YOUR_VERSION --apply
vps-manage upgrade hysteria --version YOUR_VERSION --apply

# Preview before restoring an actual snapshot directory
vps-manage restore /root/vps-backups/YOUR_SNAPSHOT
vps-manage restore /root/vps-backups/YOUR_SNAPSHOT --apply
```

Upgrades support explicit stable x86_64/aarch64 releases. The tool selects the expected official GitHub asset, verifies SHA256 and reads only the expected executable from an archive. It does not follow latest or rerun the entire installer. Previous binaries are backed up, configuration/credentials retained, and failures in binary-version checks, Xray validation or restarting an originally active service trigger a rollback attempt.

Restoration verifies all snapshot paths and hashes before backing up current state. It restores saved file metadata, service state and recorded network values. It does not provision users/dependencies or bulk-remove newer files; the dedicated network file is handled specially when absent in the snapshot. After restoring older HTTPS configuration, review current DNS/certificates and whether public 8080 needs restricting. Disaster recovery after OS reinstallation requires additional manual work.

References: [Xray Releases](https://github.com/XTLS/Xray-core/releases), [Hysteria Releases](https://github.com/apernet/hysteria/releases), [Hysteria performance](https://v2.hysteria.network/docs/advanced/Performance/), [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https).
