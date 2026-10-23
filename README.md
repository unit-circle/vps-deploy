# VPS Deploy

**简体中文** | [English](README.en.md)

为 Ubuntu / Debian 新服务器部署 **VLESS Reality + Hysteria2**，自动生成 Clash / Mihomo 订阅，并支持把多台 VPS 的节点合并到一个固定订阅地址。

> 状态：已完成本地配置生成、订阅服务和聚合工具测试；尚未对当前仓库版本完成真实 VPS 端到端验收。建议先在无重要数据的新服务器上部署。项目不是 Evoxt 官方产品。

## 从这里开始

| 你的目标 | 阅读 |
|---|---|
| 从购买 Evoxt 到导入 Clash，完整走一遍 | [Evoxt 新手教程](docs/evoxt.zh-CN.md) |
| 一条订阅管理多台服务器 | [多服务器聚合教程](docs/multi-server.zh-CN.md) |
| 查看英文说明 | [English README](README.en.md) |
| 遇到安装或连接问题 | [排错与部署经验](docs/evoxt.zh-CN.md#排错与部署经验) |

## 功能与边界

- 每台 VPS 默认部署两个节点：TCP 443 的 VLESS Reality / Vision、UDP 443 的 Hysteria2。
- 随机生成 UUID、Reality 密钥、HY2 密码和订阅路径；HY2 使用自签名证书及证书指纹固定。
- 使用官方 Xray / Hysteria 安装器，配置专用运行用户、文件权限和 systemd 开机启动。
- 自定义节点名称，如 `Tokyo-VLESS`、`Seoul-HY2`。
- `vps-nodes` 可导入、替换、删除其他 VPS 的配置快照；主订阅 URL 保持不变。
- 聚合只合并客户端配置：**不自动创建远程 VPS，不中转节点流量，不把两个节点的带宽叠加**。
- 默认是 `MATCH,PROXY` 全流量规则，不包含国内外分流、自动测速分组、多用户配额或管理面板。
- 不自动修改防火墙，不自动覆盖已有节点，不自动升级现有部署。

## 环境要求

面向新安装的 Ubuntu 22.04 / 24.04、Debian 12 / 13，systemd、root 权限、可访问 GitHub 的公网 IPv4 VPS。优先使用 Ubuntu 24.04 x86_64。其他架构及系统版本尚未在本项目实测，不能视为已验证支持。

服务器需预装 `curl`、`python3`、`flock`。缺失时先执行：

```bash
apt-get update && apt-get install -y curl ca-certificates python3 util-linux
```

## 一条命令部署

先通过 SSH 登录服务器，以 root 运行。将 `YOUR_PUBLIC_IPV4` 替换成服务器公网 IPv4，`Tokyo` 可以改成自己的节点名称。

```bash
curl --proto '=https' --tlsv1.2 -fL --retry 3 https://raw.githubusercontent.com/unit-circle/vps-deploy/main/deploy-vps.sh -o /root/deploy-vps.sh && bash /root/deploy-vps.sh YOUR_PUBLIC_IPV4 "Tokyo"
```

命令先下载到文件，再执行。建议先阅读脚本；需要可复现版本时，先下载同一 Git 提交的整个仓库并校验文件，不要仅固定入口脚本而让辅助工具仍跟随 `main`。上游安装器和软件版本目前仍取执行时的稳定版本。

**已部署的机器不要靠重复执行脚本新增节点。**同一主机换 IP、安装中断后重试、旧版迁移都应先查看现有状态和备份。

## 必须放行的入站规则

| 协议 | 端口 | 用途 |
|---|---:|---|
| TCP | 22 或你的实际 SSH 端口 | 远程登录 |
| TCP | 443 | VLESS Reality |
| UDP | 443 | Hysteria2 |
| TCP | 8080 | HTTP 订阅下载 |

TCP 443 和 UDP 443 分别添加。云防火墙、UFW 都启用时，两层都要放行。SSH 可限制来源为自己的公网 IP；节点端口需允许客户端的来源 IP。当前默认方案无需 TCP 80。端口不需要单独购买。

## 部署后如何使用

```bash
# 三行 active 只证明服务运行，不代表公网代理握手已验证
systemctl is-active xray hysteria-server vps-sub

# 查看完整订阅地址（不要公开）
cat /root/vps-nodes/subscription.txt

# 查看节点与聚合来源数量，不显示凭据
vps-nodes list
```

在 Clash Verge / 支持 Mihomo 的客户端添加远程订阅，粘贴实际地址，更新并启用。选择 `PROXY` 分组，分别测试 VLESS 和 HY2，再启用客户端系统代理。TUN 不是首次连通测试的必选项。

## 一个订阅包含多台服务器

以 A 为主订阅服务器、B 为新增服务器。两台先分别完成部署。

在 B 上导出原生节点：

```bash
vps-nodes export /root/b-native.json
```

在 A 上执行，替换 `B_PUBLIC_IPV4`：

```bash
scp root@B_PUBLIC_IPV4:/root/b-native.json /root/b-native.json
vps-nodes import tokyo /root/b-native.json
vps-nodes list
```

A 的原订阅会从 2 个节点变成 4 个节点，地址不变。在客户端更新 **A 的订阅** 即可。继续导入 C 则是 6 个节点。文件是含凭据的私密 JSON；不要上传到 GitHub。

更新某台服务器的快照时，重新导出到新的文件名、复制到 A，再用相同来源 ID 导入。相同 ID 会替换，不会无限追加。它不是定时同步，详见[完整教程](docs/multi-server.zh-CN.md)。

## 文件、维护与安全

| 路径 | 内容 |
|---|---|
| `/root/vps-nodes/subscription.txt` | 私密订阅 URL |
| `/root/vps-nodes/local-nodes.json` | 当前服务器原生节点 |
| `/root/vps-nodes/clash.yaml` | 合并后的完整客户端配置 |
| `/root/vps-nodes/sources/` | 导入的远程节点快照 |
| `/root/vps-nodes/backups/` | 聚合修改前的私密备份 |
| `/root/vps-nodes/links.txt` | 本机两个节点的 URI；不会随聚合增加 |
| `/etc/vps-sub/clash.yaml` | 对外提供的订阅内容 |
| `/usr/local/etc/xray/config.json` | Xray 服务端配置 |
| `/etc/hysteria/config.yaml` | HY2 服务端配置 |

`.yaml` 文件实际由脚本写成 JSON；JSON 可以作为 YAML 使用。管理工具只接受项目导出的 JSON，不解析任意第三方 YAML。

随机路径是访问凭据，**HTTP 不会加密订阅下载**。HY2 的证书指纹不保护 HTTP 订阅。长期使用建议改为你控制的域名和可信 HTTPS 反向代理，完成客户端更新后再收紧公网 8080 入口。此仓库目前不自动配置该 HTTPS 方案。不要向公共订阅转换网站提交真实链接。

本项目不提供自动卸载命令。删除服务器、重装系统、删除配置会丢失凭据；先在私密位置备份。真实节点、密码、私钥、优惠码以外的账户信息均不应提交仓库。

## Evoxt 优惠信息

- 优惠码：**待维护者提供**。
- 推广链接：**待维护者提供**；提供后会注明是否包含返佣。
- 优惠幅度、适用套餐、有效期以结算页面和厂商条款为准；不影响脚本功能。
- 本教程没有承诺特定价格、速度或延迟。

## 本地检查

```bash
bash -n deploy-vps.sh
python3 -m unittest discover -s tests -v
```

这些检查不能替代真实 VPS 的安装、TCP / UDP 公网可达性及客户端代理请求测试。上游安装器会更新，出现不兼容时先保存最后的报错，不要关闭防火墙或删除配置试错。

## 参考资料

- [Xray 官方安装器](https://github.com/XTLS/Xray-install)
- [Hysteria 官方安装说明](https://v2.hysteria.network/docs/getting-started/Server-Installation-Script/)
- [Mihomo Hysteria2 配置](https://wiki.metacubex.one/en/config/proxies/hysteria2/)
- [Evoxt 官方部署指南](https://evoxt.com/guides/how-to-deploy-a-evoxt-vm-with-10-simple-steps/)
- [Evoxt 官方防火墙指南](https://evoxt.com/evoxt/evoxt-firewall-guide/)

文档核对日期：2026-10-23。请遵守所在地法律和服务器厂商服务条款。
