# 贪吃蛇 3D —— 云服务器部署说明

服务器：腾讯云 Ubuntu 22.04（`193.112.172.83`，地域 ap-guangzhou，实例 ins-chza13fs）
访问账号：`ubuntu`（密钥 `1.pem`）

## 对外访问地址

| 服务 | 地址 | 说明 |
|------|------|------|
| 贪吃蛇 3D 游戏 | http://193.112.172.83:8090/ | HTTP + WebSocket 同端口 8090 |
| 1Panel 面板 | 见下方「通过 SSH 隧道访问」 | 已改为仅监听 127.0.0.1:8091，不再直接对公网开放 |

> 说明：腾讯云安全组只放行了 22、8090 两个端口。8090 原为 1Panel 占用，
> 现将游戏部署在 8090，1Panel 迁移到内网 8091，因此 1Panel 需通过 SSH 隧道访问。

## 文件位置（服务器）

```
/home/ubuntu/snake-3d/
├── index.html      前端页面（CSS + HTML + JS 单文件）
├── serve.py        服务端（HTTP + WebSocket，端口由环境变量 PORT 控制）
├── three.min.js    Three.js 渲染库（本地 vendor r160）
├── data/           运行数据（账户 store.json、用量 usage.json/usage.log，永不入库）
├── README.txt      最简运行说明
└── .venv/          独立虚拟环境（websockets==13.1）
```

## 当前功能版本（2026-10，P2P5 计划 11 批已全部交付）

玩法与模式：死斗/积分两种胜利模式（限时/无限复活可配）、大招蓄力弹幕、
偏转/护盾道具（共 7 种道具）、成对传送门、AI 蛇（0-7 条，单人练习快捷入口）、
白天主题、连击倍率、房间口令（6-20 位混合）、房间 24h 保留与「保存」常驻、
断线 10s 恢复原蛇（挂起蛇灰化显示）、房间聊天、小地图、观战左右键切换、
客户端渲染插值、移动端/720p 短屏适配。

协议与工程：快照增量协议（静态字段变化才下发，首帧全量）、GitHub Actions CI
（单测 + 8 套 python E2E + Playwright 冒烟）、后台用量报表（每小时在线曲线/
房间热度，`python usage_report.py`）。详见 HANDOVER.md。

## systemd 服务

服务名：`snake-3d.service`（已设置开机自启、崩溃自动重启）

```bash
sudo systemctl status snake-3d      # 查看状态
sudo systemctl restart snake-3d     # 重启
sudo systemctl stop snake-3d        # 停止
sudo journalctl -u snake-3d -f      # 实时日志
```

关键配置：

```
Environment=PORT=8090
ExecStart=/home/ubuntu/snake-3d/.venv/bin/python /home/ubuntu/snake-3d/serve.py
```

## 端口与防火墙

- 游戏进程监听：`0.0.0.0:8090`（PORT 环境变量控制）
- 1Panel 监听：`127.0.0.1:8091`
- ufw 已放行：`8090/tcp`（`20000/tcp` 规则保留但未使用）
- 腾讯云安全组：需放行 `8090`（当前已是）

## 通过 SSH 隧道访问 1Panel

在本机执行：

```bash
ssh -N -L 18091:127.0.0.1:8091 tencent
```

然后浏览器打开（注意 1Panel 的安全入口为 `tencentcloud`）：

```
http://127.0.0.1:18091/tencentcloud/
```

## 回滚 / 恢复 1Panel 原状

1Panel 端口配置存于数据库 `/opt/1panel/db/core.db` 的 `settings` 表。
本次修改前已备份为 `core.db.bak-<时间戳>`。

恢复步骤：

```bash
sudo 1pctl stop core
sudo cp /opt/1panel/db/core.db.bak-<时间戳> /opt/1panel/db/core.db
sudo 1pctl start core
# 同时把游戏服务改回其它端口：
sudo sed -i 's/^Environment=PORT=8090/Environment=PORT=20000/' /etc/systemd/system/snake-3d.service
sudo systemctl daemon-reload && sudo systemctl restart snake-3d
```

## 依赖说明

`serve.py` 使用的是 websockets 旧版 API（`process_request(path, headers)`）。
websockets 16.x 已移除该 API，会导致 HTTP 请求 500，故虚拟环境锁定为 `websockets==13.1`。
升级依赖时请勿跨过该大版本，否则需按新版 API 改写 `serve.py`。
