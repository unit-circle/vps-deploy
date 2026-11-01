# VPS Deploy

**简体中文** | [English](README.en.md)

为新安装的 Ubuntu / Debian VPS 部署 **VLESS Reality + Hysteria2**，生成 Clash / Mihomo 订阅，并通过菜单完成检查、备份、配置更新和指定版本升级。

默认保留 VPS 原生出口，使用 IPv4 出站。网络调优和订阅 HTTPS 均由你选择后执行。

> 验证状态：已完成本地语法、配置生成、订阅服务和维护逻辑测试。当前完整版本尚未在真实 VPS 验证安装、内核参数和公网证书签发。项目不是 Evoxt 官方产品。

## 快速开始

在新 VPS 的 SSH 窗口中以 root 执行。先准备依赖：

```bash
apt-get update && apt-get install -y curl ca-certificates python3 util-linux
```

下载入口，启动菜单：

```bash
curl --proto '=https' --tlsv1.2 -fL --retry 3 https://raw.githubusercontent.com/unit-circle/vps-deploy/main/bootstrap.sh -o /root/bootstrap-vps.sh && bash /root/bootstrap-vps.sh
```

入口会下载并记录**同一 Git 提交**下的部署脚本和辅助工具，通过语法检查后显示菜单。下载目录会保留，便于审阅和再次使用。初次安装仍使用官方稳定版安装器和软件，并记录实际版本；项目版本固定不等于上游软件版本固定。

习惯原来的一条命令安装时，可以带参数：

```bash
bash /root/bootstrap-vps.sh YOUR_PUBLIC_IPV4 "Osaka"
```

将 `YOUR_PUBLIC_IPV4` 换成服务器公网 IPv4。面向 Ubuntu 22.04 / 24.04、Debian 12 / 13、systemd 和公网 IPv4；默认推荐 Ubuntu 24.04。已有配置会被保留，重新执行安装不会覆盖凭据。其它发行版、架构和云厂商尚待实机验收。

## 菜单能做什么

| 选项 | 行为 |
|---|---|
| 新服务器安装 | 检查系统、IP、名称和端口，安装双协议，生成订阅并检查本机服务 |
| 状态和 Google 检查 | 查看服务、监听端口、IPv4 策略、权限、证书与原生 IPv4 HTTPS 连通 |
| 私密完整备份 | 备份本项目的配置、凭据、证书、辅助工具、服务配置和节点程序 |
| IPv4 配置更新 | 保留现有字段，迁移出站策略并为订阅服务补充回环监听支持 |
| 网络调优 | 预览缓冲区上限；可选择内核已支持的 BBR |
| 可选 HTTPS 订阅 | 自有域名、可信证书、自动续期；独立使用 TCP 8443 |
| 指定版本升级 | 指定 Xray / Hysteria / Caddy 稳定版本，校验 SHA256 后替换单个程序 |
| 恢复备份 | 校验快照，先备份当前状态，再恢复同一主机的项目文件 |
| 显示私密订阅 | 显示包含凭据的订阅 URL |

配置更新、调优、HTTPS、版本升级和恢复默认先预览，菜单中输入 `APPLY` 才执行。失败时尝试恢复被修改的文件和原服务状态，并保留备份路径。备份只是本地文件创建，不要求 `--apply`。

## 加密与订阅

- VLESS 使用 Reality / Vision；配置中的 `decryption: none` 不表示 Reality 传输没有加密。
- Hysteria2 使用 TLS 和随机认证密码。无域名模式采用自签名证书，客户端必须保留证书 `fingerprint` / URI 的 `pinSHA256`，配套的 `skip-cert-verify` 不能单独作为认证保障。
- 节点服务使用专用用户、限制文件权限和 systemd 保护选项。检查命令会核对证书有效期、指纹和原生客户端凭据的一致性。
- **默认 HTTP 订阅不加密下载内容。**随机 URL 路径用于认证，无法替代 HTTPS。没有域名时可用 SSH 下载配置后本地导入；不要把真实订阅提交给公共转换网站。

可选 HTTPS 使用 `https://你的订阅域名:8443/随机路径/clash.yaml`，为已有节点保留 TCP / UDP 443。域名仅设置指向 VPS 的 A 记录；此自动流程要求该订阅域名没有 AAAA 记录。TCP 80 用于 ACME HTTP-01 签发与续期，TCP 8443 用于订阅。脚本不修改 DNS 记录或防火墙。

先通过菜单“指定版本升级”安装经校验的 Caddy，再选择 HTTPS，填写域名与 ACME 联系邮箱。程序验证可信证书、域名和订阅内容后才接受新 URL；订阅后端改为 `127.0.0.1:8080`。客户端需更新订阅地址。详见[维护说明](docs/maintenance.zh-CN.md#可选-https)。

## 网络与 Google

新生成的配置包含：

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

Xray 的策略作用于目标域名解析，没有 IPv4 结果时不会回退 IPv6；它不能把客户端直接传来的 IPv6 地址转换成 IPv4。Hysteria2 的 `"4"` 模式仅使用 IPv4。[Xray 官方说明](https://xtls.github.io/config/transports/sockopt.html)、[Hysteria2 官方说明](https://v2.hysteria.network/docs/advanced/Full-Server-Config/#customizing-direct-outbound)。

网络调优把 UDP 相关收发缓冲区最大值至少提高到 16 MiB，不降低更大的已有值；BBR 需主动选择，且仅在内核报告支持时设置。它不安装内核、不切换当前网卡队列、不关闭 IPv6，也不修改系统 DNS、MTU 或防火墙。TCP 的 BBR 与 Hysteria2 的 QUIC 拥塞控制是不同层次；更大的参数不等于更快。[Hysteria2 性能说明](https://v2.hysteria.network/docs/advanced/Performance/)。

Google 检查分别测试域名 IPv4 解析及 Google、Accounts、Gstatic 的 HTTPS 响应。它检查的是 **VPS 原生出口**，客户端仍需分别选择 VLESS / HY2 测试代理请求。地区还可能受 IP 数据、设备位置和账户活动影响；脚本不伪造地区、不更换出口，也不保证 Gmail 入口或地区显示。[Google 的位置说明](https://support.google.com/websearch/answer/179386?hl=zh-Hans)。

## 必须放行的端口

| 协议 | 端口 | 用途 |
|---|---:|---|
| TCP | 实际 SSH 端口，常见为 22 | 远程登录 |
| TCP | 443 | VLESS Reality |
| UDP | 443 | Hysteria2 |
| TCP | 8080 | 默认 HTTP 订阅；启用 HTTPS 后后端仅监听回环 |
| TCP | 80 | 仅可选 HTTPS 的证书签发与续期 |
| TCP | 8443 | 仅可选 HTTPS 订阅 |

云防火墙和 UFW 同时启用时，两层都需放行。脚本始终不自动修改这些规则。HTTPS 启用后可收紧公网 8080 规则。

## 部署后的使用与维护

在 Clash Verge / Mihomo 中添加订阅，选择 `PROXY` 分组，分别测试 VLESS 和 HY2。TUN 不是首次测试的必要条件。

新安装的服务器可直接执行：

```bash
vps-manage check --google
vps-manage backup
vps-manage update
vps-manage network
```

配置更新和网络调优默认仅预览，不会重启服务。真正执行时使用菜单确认，或按[维护说明](docs/maintenance.zh-CN.md)追加 `--apply`。不提供无版本号的自动升级；升级单个程序前先阅读对应官方 Release 说明。

旧部署还没有 `vps-manage` 时，重新下载上面的入口，使用菜单或 `bash /root/bootstrap-vps.sh check --google`。不要通过再次安装来迁移。自定义 YAML、ACL 或复杂出站可能需要人工处理；工具会停止，避免改写未知配置。

## 多台服务器，一个订阅

每台服务器先独立部署。B 导出自己的两个节点，在 A 导入：

```bash
# B
vps-nodes export /root/b-native.json

# A，替换 B_PUBLIC_IPV4
scp root@B_PUBLIC_IPV4:/root/b-native.json /root/b-native.json
vps-nodes import tokyo /root/b-native.json
vps-nodes list
```

更新 A 的订阅即可看到四个节点。相同来源 ID 再次导入会替换快照。聚合只合并客户端配置，不中转流量、不叠加带宽、不定时同步远程节点。导出文件包含凭据。详见[聚合教程](docs/multi-server.zh-CN.md)。

## 文件与恢复边界

| 路径 | 内容 |
|---|---|
| `/root/vps-nodes/subscription.txt` | 当前私密订阅地址 |
| `/root/vps-nodes/local-nodes.json` | 本机原生节点 |
| `/root/vps-nodes/clash.yaml` | 合并后的客户端配置 |
| `/root/vps-nodes/deployment.json` | 初次部署版本及最近受控升级记录 |
| `/usr/local/etc/xray/config.json` | Xray 服务端配置 |
| `/etc/hysteria/` | HY2 配置、证书与私钥 |
| `/etc/vps-sub/` | 订阅设置与发布内容 |
| `/etc/vps-sub-https/` | 可选 Caddy 配置 |
| `/etc/sysctl.d/90-vps-deploy.conf` | 可选网络调优 |
| `/root/vps-backups/` | 本机维护快照，含凭据和程序 |
| `/root/vps-nodes/backups/` | 聚合工具的变更备份 |

项目的 `.yaml` 文件实际为 JSON，不需要额外 YAML 依赖。维护工具不会自动重写任意第三方 YAML。

快照是本机 root 可读的文件级备份，**没有加密，也不是整机镜像**；可能占用数十至数百 MiB。恢复面向同一已部署主机，会恢复快照文件及记录的网络值，不会重建用户或安装系统依赖，也不会批量删除后来增加的文件。原快照没有项目网络调优文件时，恢复会删除这一专用文件。外传备份前另行加密并妥善保管。

## 文档与检查

- [Evoxt 从购买到客户端连接](docs/evoxt.zh-CN.md)
- [维护、HTTPS、升级与恢复](docs/maintenance.zh-CN.md)
- [多服务器聚合](docs/multi-server.zh-CN.md)

```bash
bash -n bootstrap.sh
bash -n deploy-vps.sh
python3 -m unittest discover -s tests -v
```

Windows 可用 `python -X utf8 -m unittest discover -s tests -v`；测试会使用 Git for Windows 的 Bash / OpenSSL，并跳过 Linux 权限和聚合锁测试。GitHub Actions 提供 Ubuntu 22.04 / 24.04 检查。单元测试不安装服务、不下载节点程序、不连接现有 VPS，也不替代实机验收。

## Evoxt 优惠信息

优惠码和推广链接待维护者提供；如包含返佣会注明。实际优惠、套餐和有效期以厂商结算页面为准，不影响脚本功能。

维护版本：2026-11-01。真实节点、密码、私钥和订阅地址不得提交仓库。
