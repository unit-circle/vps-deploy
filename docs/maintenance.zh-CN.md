# 维护、网络调优与可选 HTTPS

[返回 README](../README.md) | [English](maintenance.en.md)

以下命令在已部署 VPS 的 SSH 窗口中以 root 执行。下载仓库不会自动修改 VPS。初次安装使用菜单 1；已有部署使用维护选项，不要重复安装。

## 入口与版本

新部署安装了 `vps-manage`。旧部署可下载 README 中的 `bootstrap.sh`，执行 `bash /root/bootstrap-vps.sh` 打开相同菜单；也可将本文命令的 `vps-manage` 替换成 `bash /root/bootstrap-vps.sh`。

入口把部署脚本和两个辅助工具固定到同一提交。需要重现项目版本时，可在服务器使用：

```bash
VPS_DEPLOY_REF=YOUR_FULL_COMMIT_SHA bash /root/bootstrap-vps.sh
```

替换完整 SHA；这不固定初次安装时的上游稳定软件。`deployment.json` 记录初始项目与程序版本。维护工具的 `upgrade` 则要求具体稳定版本，并检查官方资产的 SHA256 摘要；若官方接口没有摘要，必须用 `--sha256` 提供自己核对的官方校验值。

## 先检查和备份

```bash
vps-manage check --google
vps-manage backup
```

检查包含服务、TCP / UDP 443 监听、Xray 配置、出站策略、敏感文件权限、HY2 证书有效期及原生节点指纹/凭据一致性。本机订阅 GET 必须与磁盘内容一致；启用 HTTPS 后还检查证书信任、域名和内容。不会输出 UUID、密码或订阅随机路径。

Google 诊断分别报告 IPv4 DNS 与 HTTPS 状态。`204` 通常表示连通性端点成功，Accounts 可能返回重定向。它不是两种代理的公网握手测试，也不是 IP 地区鉴定。使用客户端分别选择两个节点，查看实际网页与搜索页底部的位置来源；客户端提前解析出的 IPv6 地址、浏览器位置权限和账户状态需要分别排查。

快照保存在 `/root/vps-backups/时间戳-随机串/`，目录 700、文件 600，含 SHA256 清单。包含项目配置、原生/聚合节点、证书私钥、程序和服务文件；不递归复制聚合工具的历史备份，不包含整个操作系统。文件级复制不是一致性磁盘快照，保留多个可用快照，并在恢复后复查证书和服务。

## 旧部署迁移 IPv4 策略

```bash
vps-manage update
vps-manage update --apply
```

第一条预览，第二条才执行。它只调整：

- Xray `direct/freedom` 的 `streamSettings.sockopt.domainStrategy=ForceIPv4`。
- HY2 默认 `direct` 出站的字符串 `mode: "4"`。
- 项目原版订阅服务的一行监听表达式，让后续 HTTPS 可以切换回环监听；默认仍为原有 `0.0.0.0:8080`。

保留端口、密钥、密码、证书、订阅 URL 与其它字段。需要原来三个服务都处于 active，更新前备份，Xray 验证通过后重启节点服务，再检查状态与订阅。失败时尝试回滚。第三方 YAML、自定义 HY2 ACL、多出站或找不到唯一 direct/freedom 时会停止，需要人工审阅。

## 稳定优先的网络调优

```bash
vps-manage network
vps-manage network --apply

# 可选：只有内核已报告支持 BBR 时才设置
vps-manage network --bbr
vps-manage network --bbr --apply
```

缓冲区只调整 `net.core.rmem_max`、`net.core.wmem_max`，目标至少为 `16777216`。BBR 额外调整 `net.ipv4.tcp_congestion_control`。专用配置文件是 `/etc/sysctl.d/90-vps-deploy.conf`；若已有同名非项目文件，会停止而不覆盖。

不修改其它 sysctl 文件、不安装新内核、不强行加载模块、不替换现有网卡队列、不关闭 IPv6，也不改系统 DNS、MTU 或防火墙。BBR 不直接控制 HY2 的 QUIC。实际收益取决于线路、CPU、丢包和内存；需要用相同节点、时段和测试文件比较。恢复修改前快照可还原记录的运行值及项目专用文件。

## 可选 HTTPS

1. 准备专用订阅域名，所有 A 记录只指向本 VPS；本自动流程要求该域名没有 AAAA 记录。使用直接 DNS 解析。
2. 放行 TCP 80 和 TCP 8443。80 用于证书签发和自动续期，8443 用于订阅；原有节点 443 不变。
3. 从 [Caddy 官方 Releases](https://github.com/caddyserver/caddy/releases) 选择稳定版本，通过菜单 7 安装，或使用下列命令。将占位符换成真实值。

```bash
vps-manage upgrade caddy --version YOUR_CADDY_VERSION
vps-manage upgrade caddy --version YOUR_CADDY_VERSION --apply
vps-manage https --domain sub.example.com --email admin@example.com
vps-manage https --domain sub.example.com --email admin@example.com --apply
```

命令只接受 `vX.Y.Z` 一类明确版本，不接受 `latest`。已有服务占用 80 / 8443、域名不匹配、缺少 Caddy 或旧订阅后端尚未迁移时，设置会停止。旧后端先执行上一节的 `update`。

使用独立的 `/etc/vps-sub-https/Caddyfile` 和 `vps-sub-https.service`，不会改写系统原有 `/etc/caddy/Caddyfile`。Caddy 使用 `vps-sub` 用户，证书数据存放在 `/var/lib/vps-sub-https/`。关闭 TLS-ALPN challenge，避免使用节点 TCP 443；HTTP-01 仍需公网 TCP 80。HTTPS 只开 HTTP/1.1、HTTP/2，不额外开放 UDP 8443。Caddy 日志输出关闭，避免记录私密请求路径。

证书签发可能需要约两分钟。程序通过回环地址验证正常证书链、域名和订阅正文，不跳过 TLS 验证。验证失败则尝试恢复旧 URL、后端监听和服务。验证通过后后端只监听 `127.0.0.1:8080`，外部只能使用新 HTTPS 地址。

```bash
cat /root/vps-nodes/subscription.txt
```

此命令显示私密地址。将客户端旧订阅替换为它，再收紧公网 8080。域名配置不能通过重复启用来覆盖；更换域名前先备份、审阅现有证书和配置。

## 指定版本升级与恢复

```bash
# 用官方 Release 中的版本替换 YOUR_VERSION
vps-manage upgrade xray --version YOUR_VERSION
vps-manage upgrade xray --version YOUR_VERSION --apply
vps-manage upgrade hysteria --version YOUR_VERSION --apply

# 先预览再恢复某个实际快照目录
vps-manage restore /root/vps-backups/YOUR_SNAPSHOT
vps-manage restore /root/vps-backups/YOUR_SNAPSHOT --apply
```

升级仅支持 x86_64 / aarch64 的明确稳定版。从对应官方 GitHub Release 获取匹配资产，校验 SHA256 后，只读取压缩包中预期的程序文件。没有自动追随 latest，也不重新运行整个安装器。备份旧程序，保留配置和凭据；程序版本验证、Xray 配置验证或原活跃服务的重启检查失败时尝试回滚。

恢复先校验快照的全部文件路径和摘要，再备份现状，按原权限/用户恢复文件、服务启动状态及记录的网络值。不会重建系统用户或依赖，也不会删除后来增加的所有文件；仅对项目专用网络文件处理“原快照不存在”的情况。恢复旧 HTTPS 配置时要复查当前域名、证书及 8080 是否仍需要收紧。系统重装后的灾难恢复需要额外人工步骤。

官方参考：[Xray Releases](https://github.com/XTLS/Xray-core/releases)、[Hysteria Releases](https://github.com/apernet/hysteria/releases)、[Hysteria 性能指南](https://v2.hysteria.network/docs/advanced/Performance/)、[Caddy 自动 HTTPS](https://caddyserver.com/docs/automatic-https)。
