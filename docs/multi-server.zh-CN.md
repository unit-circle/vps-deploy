# 一条订阅管理多台 VPS

**简体中文** | [English](multi-server.en.md) · [返回 README](../README.md)

## 先区分两件事

**部署节点**是在每台服务器安装代理程序；**发布订阅**是把客户端连接这些节点的参数集中到一个文件。一个订阅 URL 本身不能帮你创建另一台 VPS 或在它上面安装程序。

本项目的工作方式：A、B、C 各部署两个节点；A 作为主订阅服务器，保留本机节点并导入 B、C 的节点快照；客户端只导入 A 的 URL，即可看到六个节点。代理流量直连所选节点，不必绕经 A。

| 服务器 | 本机协议 | 是否发布主订阅 |
|---|---|---|
| A | VLESS + HY2 | 是，最终含 A/B/C 六个节点 |
| B | VLESS + HY2 | 可有本机订阅，但客户端不必导入 |
| C | VLESS + HY2 | 可有本机订阅，但客户端不必导入 |

主订阅地址不变的条件是 A 的 IP/域名、端口和随机路径保持不变。换掉 A 的 IP 后，基于 IP 的旧链接不会自动跟随；使用自有域名的 HTTPS 有助于后续迁移，但本项目不自动配置它。

## 1. 在 A、B 上分别部署

在各自服务器的 root SSH 窗口中运行 README 的部署命令。A 可命名 `Seoul`，B 可命名 `Tokyo`。IP 必须分别填写对应服务器的公网地址，不要把 A 的 IP 填到 B。

确认两台的本地服务均正常，并分别完成客户端握手测试。先确保节点可用，再聚合；聚合不会修复坏节点。

## 2. 在 B 导出本机节点

在 B 上执行：

```bash
vps-nodes export /root/b-native.json
```

导出文件权限为 600，包含凭据。导出只含 B 的本机节点，即使 B 自己曾导入过 C，也不会把 C 再次嵌套导出。

为了避免覆盖文件，目标路径必须尚不存在。再次导出时换一个文件名，例如：

```bash
vps-nodes export /root/b-native-v2.json
```

## 3. 在 A 安全复制 B 的文件

**下面的命令在 A 的 SSH 窗口执行**，不是在 B 上，也不是在本地 PowerShell：

```bash
scp root@B_PUBLIC_IPV4:/root/b-native.json /root/b-native.json
chmod 600 /root/b-native.json
```

首次连接核对 B 的 SSH 主机指纹，再按提示输入 B 的密码或使用已配置的 SSH 密钥。自定义 SSH 端口时：

```bash
scp -P 2222 root@B_PUBLIC_IPV4:/root/b-native.json /root/b-native.json
```

不需要把 SSH 私钥放到 GitHub，也不需要开放 B 的 8080 给 A；这里通过 SSH 获取文件。若不允许服务器之间 SSH，可以通过自己的电脑分两次 `scp`，文件同样需要私密保存。

## 4. 在 A 导入并更新客户端

```bash
vps-nodes import tokyo /root/b-native.json
vps-nodes list
vps-nodes url
```

`tokyo` 是来源 ID，只能是 1–32 位字母、数字、下划线或短横线，且不能叫 `local`。远程节点自动添加 `[tokyo]` 前缀，避免与本机节点重名。

成功后 A 的订阅含四个节点，URL 与导入前一致。打开 Clash，更新 **A 的订阅**。不必重新安装 A，也不必重新启动 Xray 或 HY2；订阅服务会在下一次请求读取新文件。

只查看来源和数量：

```bash
vps-nodes list
```

查看 URL 会显示私密随机路径，不要公开。

## 5. 导入 C、更新 B、移除 B

新增 C：先在 C 导出、复制到 A，然后在 A 上执行：

```bash
vps-nodes import singapore /root/c-native.json
```

更新 B：在 B 重新导出到新文件名，复制到 A，在 A 用**相同来源 ID**导入：

```bash
vps-nodes import tokyo /root/b-native-v2.json
```

同名来源会整体替换；不会重复增加节点。如果 B 重装或换了 IP/密钥，必须更新快照；工具不会定时连接 B。

从 A 的订阅中移除 B：

```bash
vps-nodes remove tokyo
```

这只删除 A 保存的 `tokyo` 快照并重建订阅，不会卸载 B、关闭 B 或撤销 B 上的凭据。客户端需要更新订阅，已有连接也不一定立即结束。

从当前原生节点和来源快照重新生成：

```bash
vps-nodes rebuild
```

`PROXY` 分组由工具管理，导入时会重建其中的节点列表；主配置的路由规则保留，远程文件附带的规则和分组不导入。不要手动给 `PROXY` 分组加入期望长期保留的自定义成员。

## 6. 旧版脚本的迁移

如果使用之前的 `deploy-vps.sh` 已正常部署，但没有 `vps-nodes`，**不要重新部署整个服务器**。只下载管理工具：

```bash
curl --proto '=https' --tlsv1.2 -fL --retry 3 https://raw.githubusercontent.com/unit-circle/vps-deploy/main/scripts/vps-nodes.py -o /root/vps-nodes-tool.py
python3 -m py_compile /root/vps-nodes-tool.py
install -m 755 /root/vps-nodes-tool.py /usr/local/sbin/vps-nodes
```

旧配置如果还没有聚合过，可以从原始配置生成本机节点快照：

```bash
python3 <<'PY'
import json, os
from pathlib import Path
state = Path('/root/vps-nodes')
target = state / 'local-nodes.json'
if target.exists():
    raise SystemExit('local-nodes.json 已存在，不修改')
c = json.loads((state / 'clash.yaml').read_text())
nodes = c['proxies']
if len(nodes) != 2 or {n['type'] for n in nodes} != {'vless', 'hysteria2'}:
    raise SystemExit('不是预期的原始双节点配置，停止自动迁移')
if len({n['server'] for n in nodes}) != 1:
    raise SystemExit('两节点不属于同一地址，停止自动迁移')
fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as f:
    json.dump({'proxies': nodes}, f, ensure_ascii=False, indent=2)
print('本机节点快照已生成')
PY
```

迁移前需自行确认这两个节点确实都是本机原生节点。如果旧文件已经手动聚合或来自其他项目，不要直接套用以上提取。更早的 `seoul-sub` / `/root/seoul-nodes/` 版本路径不同，不适用该自动迁移。

## 7. 备份与限制

- 每次导入/删除/重建前，修改涉及的旧文件会备份到 `/root/vps-nodes/backups/`。备份同样含凭据。
- 写入先暂存，再替换，保留已发布文件的用户组与权限；失败时尝试回滚已替换文件。断电或文件系统故障不能视为有数据库级事务保障。
- 无效 JSON、重复节点名、错误来源 ID 在发布前拒绝。只接受本项目的 VLESS Reality / HY2 JSON，单来源最多 200 个节点、聚合最多 1000 个。
- `links.txt` 仍只有本机两条 URI；多服务器聚合看 `clash.yaml` 与主订阅，不要误认为 URI 文件也会自动扩展。
- 这是快照合并，不是自动定时拉取、负载均衡、节点带宽合并、账号撤销或故障转移系统。
- A 不可用时无法下载新的主订阅；客户端缓存的节点配置通常仍可直接连接 B/C，取决于客户端行为。
- 当前下载通道仍是 HTTP。私密 SSH 导入不能消除客户端 HTTP 下载的风险；后续应使用可信 HTTPS。

如需定时同步或控制面板，请作为后续功能设计，不要在文档里当成已有能力。
