# Evoxt 从零部署指南

**简体中文** | [English](evoxt.en.md) · [返回 README](../README.md)

本指南以 **Windows 电脑 + Evoxt 新 VPS + Ubuntu 24.04** 为例。已有服务器上如果有网站、面板或节点，先不要照着首次部署步骤覆盖安装。所有 `YOUR_PUBLIC_IPV4`、`B_PUBLIC_IPV4` 都是占位符，需要换成自己的地址。

## 1. 先理解几个词

| 名词 | 含义 |
|---|---|
| VPS | 一台远程 Linux 服务器 |
| SSH | 电脑连接并操作远程服务器的方式 |
| root | Linux 管理员账号 |
| 节点 | 客户端连接服务器所用的一组地址、协议和凭据 |
| 订阅 | 一个下载客户端配置的地址，可以包含很多节点 |
| 主订阅服务器 A | 收集各服务器节点并提供统一订阅的机器 |

一个 VPS 生成两种协议节点，仍然是同一台服务器和同一条线路。多买一台 VPS 才会增加一个独立服务器出口。

## 2. 注册并创建 Evoxt VPS

1. 打开 [Evoxt 官网](https://evoxt.com/)，自行注册、登录。
2. 进入控制台的部署页面，选择区域与套餐。区域名称不能保证你所在网络到它的延迟；先参考测试 IP 或厂商支持信息。
3. 操作系统选择 **Ubuntu 24.04**，不要选 Windows 或预装面板镜像。
4. 设置便于区分的主机名，例如 `proxy-tokyo-01`。保存 SSH 密钥或控制台给出的登录信息。
5. 确认套餐、计费周期和结算金额；如有优惠码，提交订单前核对是否真正生效。
6. 完成购买，等待实例变为 Online / Running，再记录公网 IPv4、SSH 用户名和实际 SSH 端口。

优惠码与推广链接目前**尚未提供**，不需要为了使用脚本填写它们。不要在 GitHub Issue、截图或聊天中公开 root 密码、SSH 私钥。

控制台布局可能变化，详细入口以 [Evoxt 官方创建指南](https://evoxt.com/guides/how-to-deploy-a-evoxt-vm-with-10-simple-steps/) 为准。本文不保证某款套餐当前的价格和库存。

## 3. 设置 Evoxt 云防火墙

进入对应 VPS 的管理页面，找到 Firewall。启用前先确认 SSH 规则和控制台/VNC 备用访问方式。Evoxt 官方文档说明，启用云防火墙后其他入站协议默认被阻止，并为 Linux 默认添加 TCP 22 管理规则；**如果改过 SSH 端口，必须手动放行实际端口**。

添加并保存以下允许入站规则：

| 动作 | 协议 | 目标端口 | 来源建议 |
|---|---|---:|---|
| Allow / Accept | TCP | 实际 SSH 端口，通常 22 | 自己的公网 IP；不固定时按实际需求设置 |
| Allow / Accept | TCP | 443 | `0.0.0.0/0` 或客户端来源 IP |
| Allow / Accept | UDP | 443 | `0.0.0.0/0` 或客户端来源 IP |
| Allow / Accept | TCP | 8080 | `0.0.0.0/0` 或需要下载订阅的来源 IP |

保持正常出站访问。TCP 与 UDP 的 443 分别创建；不要只填写一条 TCP 443 后就认为 HY2 也已放行。ICMP 是可选的 ping 功能，不填端口。本脚本仅监听 IPv4。

参考：[Evoxt 官方防火墙指南](https://evoxt.com/evoxt/evoxt-firewall-guide/)。云规则与服务器里的 UFW 是两层，不会互相替代。

## 4. 从 Windows 登录服务器

在开始菜单搜索 **PowerShell** 并打开，输入：

```powershell
ssh root@YOUR_PUBLIC_IPV4
```

如果 SSH 使用 2222：

```powershell
ssh -p 2222 root@YOUR_PUBLIC_IPV4
```

首次连接出现主机指纹提示时，与可信控制台信息核对后接受。输入密码时屏幕不显示字符是正常的，输入完成按回车。不要把提示符 `PS C:\...>` 或 `root@...:~#` 一起复制进命令。

看到 `root@主机名:~#` 就表示已登录。后面的 Bash 命令在这个窗口运行，而不是退出 SSH 后在本地运行。非 root 用户需先执行 `sudo -i`。

确认系统和必要工具：

```bash
cat /etc/os-release
apt-get update && apt-get install -y curl ca-certificates python3 util-linux
```

## 5. 下载与部署

节点名称只用于识别，可以用 `Tokyo`、`Seoul` 等。将公网 IP 占位符替换后执行：

```bash
curl --proto '=https' --tlsv1.2 -fL --retry 3 https://raw.githubusercontent.com/unit-circle/vps-deploy/main/deploy-vps.sh -o /root/deploy-vps.sh && bash /root/deploy-vps.sh YOUR_PUBLIC_IPV4 "Tokyo"
```

想先阅读脚本，可以分步执行：

```bash
curl -fL --retry 3 https://raw.githubusercontent.com/unit-circle/vps-deploy/main/deploy-vps.sh -o /root/deploy-vps.sh
less /root/deploy-vps.sh
bash /root/deploy-vps.sh YOUR_PUBLIC_IPV4 "Tokyo"
```

`less` 中按 `q` 返回。安装时间取决于网络；只看到下载完成、Hysteria 安装成功或 Xray `Configuration OK` 都不等于整个部署成功。等待最终检查结果，不要同时在多个窗口重复部署。

脚本生成的配置中，服务端 IP 来自命令参数，并不通过外部网站自动检测。不要误填电脑的局域网 IP。

## 6. 可选：启用 Ubuntu UFW

如果已启用 UFW，就需要放行对应端口。想新启用时，在保持当前 SSH 连接的情况下按顺序执行；先把 SSH 端口改成实际值：

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

确认提示时输入 `y`。另开一个 PowerShell 窗口测试 SSH 仍可登录，再关闭原连接。不要为了测试节点直接关闭所有防火墙。

## 7. 检查成功并取出订阅

```bash
systemctl is-active xray hysteria-server vps-sub
ss -lntp 'sport = :443'
ss -lnup 'sport = :443'
cat /root/vps-nodes/subscription.txt
```

前三个服务应输出三行 `active`；TCP 443 应显示 Xray，UDP 443 应显示 Hysteria。最后一条打印含随机路径的 HTTP 订阅地址。**不要把实际地址截图公开。**

如果 HTTP 暂时无法访问，可从 Windows 下载配置进行临时导入排查：

```powershell
scp root@YOUR_PUBLIC_IPV4:/root/vps-nodes/clash.yaml "$env:USERPROFILE\Desktop\vps-clash.yaml"
```

自定义 SSH 端口时，`scp` 使用大写 `-P`，例如 `scp -P 2222 ...`。下载到本地的文件同样含凭据。

## 8. 在 Clash Verge / Mihomo 客户端使用

1. 从你信任的客户端官方发行页安装支持 VLESS Reality 和 Hysteria2 的 Mihomo 客户端。旧版不支持这些协议的 Clash 不能直接使用。
2. 打开“订阅 / Profiles”，新增远程订阅，粘贴完整地址并保存。
3. 更新、选中并启用该订阅。界面文字可能随客户端版本不同。
4. 打开“代理 / Proxies”，在 `PROXY` 分组中选择 `Tokyo-VLESS`，测试一次；然后测试 `Tokyo-HY2`。
5. 节点可以代理请求后，再打开客户端“系统代理”。首次测试不必同时开启 TUN。
6. 用浏览器访问目标网站，确认实际请求成功。单纯显示延迟数字并不代表所有流量已走代理。

默认配置不内置国内直连规则；选择 `DIRECT` 会直连。客户端的程序接管范围由系统代理或 TUN 决定。若其他软件手动设置了旧的代理端口，需要自行同步，配置的本地端口是 7890。

## 9. 添加第二、第三台 VPS

每台新机器分别部署，节点名称建议不同。在其中一台选择主订阅，按[多服务器教程](multi-server.zh-CN.md)导入其他机器的导出文件。以后客户端只保留主订阅即可，不需要在每台 VPS 上安装 3X-UI。

## 排错与部署经验

先采集状态，**保留最后 30–60 行报错**，不要贴全部私密配置：

```bash
systemctl status xray hysteria-server vps-sub --no-pager -l
journalctl -u xray -u hysteria-server -u vps-sub -n 60 --no-pager
ss -lntup | grep -E ':(443|8080)\b'
```

| 现象 | 判断与处理 |
|---|---|
| `unknown option -- -` | 曾因上游移除 `-u` 参数出现；当前入口已移除，核对是否下载了最新版和实际执行的文件路径 |
| HY2 `200/CHDIR` | 进入工作目录失败；本版使用 `/var/lib/vps-hy` 与对应 StateDirectory，查看 systemd 实际配置，不要改成 root 运行来掩盖问题 |
| `permission denied` | 检查日志具体文件路径和服务用户；不要把密钥权限一律改成 777 |
| 无法解析密钥输出 | 上游输出格式可能变化；本版兼容四种已知公钥字段，不要公开 `xray x25519` 原始输出 |
| 发现已有配置 | 脚本主动停止避免覆盖；先备份并判断是正常部署还是安装残留，不要直接删除目录 |
| 本机验证通过，客户端超时 | 检查云防火墙、UFW、IP、客户端支持情况和实际握手日志 |
| HY2 可用，VLESS 不可用 | UDP 可达不证明 TCP 可达；分别检查协议和 Reality 参数 |
| VLESS 可用，HY2 不可用 | 检查 UDP 443、HY2 服务状态以及客户端证书指纹是否完整 |
| 订阅下载失败 | 检查 TCP 8080、`vps-sub`、是否复制完整路径；不要把协议手动改成 HTTPS，当前服务没有 TLS |
| 换区域后延迟不同 | 同厂商、同国家也可能路由不同；先比较基础网络，重装脚本无法保证降低延迟 |

Windows 可以检查 TCP：

```powershell
Test-NetConnection YOUR_PUBLIC_IPV4 -Port 443
Test-NetConnection YOUR_PUBLIC_IPV4 -Port 8080
```

这不是 UDP 测试。不要把旧日志中的错误当成当前状态；结合时间戳判断。

## 10. 后续维护

- 服务默认开机自启；正常重启服务器后不需要重新部署。
- 修改现有 IP 或服务凭据时，需要同步客户端配置和导入到主服务器的快照，本版没有自动换 IP 命令。
- 官方程序升级可能改变安装器、账号、权限或服务配置；本项目不提供一键升级，升级前先备份。
- HTTP 订阅包含凭据，建议后续配置你控制的可信 HTTPS；不要把真实订阅放进公开仓库或公共转换网站。
- 备份配置时务必包含证书、私钥、节点凭据和订阅设置，并保存到私密加密位置；单独备份 README 无法恢复节点。

文档日期：2026-10-23。尚无当前完整版本在真实 VPS 的端到端验收记录。
