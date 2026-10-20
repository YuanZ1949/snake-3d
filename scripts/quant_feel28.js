#!/usr/bin/env node
// 批37 项11：批28 §7.3 转向手感量化
//
// spec：docs/superpowers/specs/2026-10-16-prediction-design.md §7.3（需人测五点）
//   本脚本自动化其中三组可量化数据：
//     Q1 转向跟手  —— 按键 → previewDir / moveDir / 渲染头 的响应延迟（ms）
//     Q2 开放地无回弹 —— 无输入直行段：方向翻转数 + 头坐标 A→B→A 回弹数
//     Q3 局末结算窗口不抖（M3） —— over→win 段：头坐标来回跳变数
//     M1 speed 期间不抖 —— 吃到 speed 道具（eff.speed 剩余 ms>0 窗口）无输入段：方向翻转/回弹数
//     M4 传送门/对头回弹 —— 踏门瞬移跳变数 + A→B→A 回弹数；对头追击窗口（尽力而为）
//   批38：M1/M4 由留人测改为脚本量化（Playwright ws 嗅探 items/portals/玩家 eff，零游戏代码改动）；
//   结论判定仍留用户实操。
//
// 用法（本地服）：
//   $env:PORT='8123'; Start-Process .venv\Scripts\python.exe -ArgumentList serve.py -WindowStyle Hidden
//   node scripts/quant_feel28.js [--base http://127.0.0.1:8123] [--out test-results/quant_feel28.json]
//
// 退出码：0 = 数据采集成功（不代表手感结论——结论由用户看数据判断）；1 = 数据全空；2 = 致命。
// v4：solo 房 respawn=False → 死亡恢复=开新局（goto+btnSolo+重注探针）；
//     页内循环全部有界（零向量 dir={0,0} 时原无限循环会挂死 renderer）。
// v5：+M1 speed 道具窗口 / M4 传送门穿越 / M4b 对头追击（ws 嗅探 + 贪心导航）。
'use strict';
const { chromium } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf('--' + k); return i >= 0 && args[i + 1] ? args[i + 1] : d; };
const BASE = opt('base', 'http://127.0.0.1:8123');
const OUT = opt('out', path.join('test-results', 'quant_feel28.json'));

// ---- 批38：ws 嗅探 + create 帧改写（init script，导航前注入；零游戏代码改动） ----
//  · 捕获玩家名（join 帧）→ 从 snap.players 定位自己，读 eff.speed 剩余 ms；
//  · 改写 create 帧补 {portal:true, theme:'default', bots:0}（服务端 _msg_create 本就接受这三字段，
//    与用户在创建面板勾选等价）→ solo 房必有传送门、地形干净（default: walls=0, portal=True）、
//    无 bot 撞击（批38 实证：3 bots 下玩家存活期 < speed 道具 spawn 均值 140s，M1/M4 无法采样）；
//  · 合并 full/delta 快照到 __qfCache{portals,items,cols,rows}（初始 full 帧给全量，delta 帧只带变化字段）；
//  · 对头逼近事件（同轴对向、距离 ≤8）入 __qfHeadOn（M4b 尽力而为）。
const WS_PATCH = () => {
  if (window.__qfWsPatched) return;
  window.__qfWsPatched = true;
  window.__qfCache = { portals: [], items: [], walls: [], rocks: [], hmap: [], cols: 0, rows: 0, block: new Set(), hmapBy: new Map() };
  // 地形障碍重建（default 主题 rock=1.0 密岩——批38 实证：只数边界距离的 keep-alive 必死于岩石）
  const rebuildBlock = () => {
    const c = window.__qfCache;
    c.block = new Set();
    for (const w of c.walls) c.block.add(w[0] + ',' + w[1]);
    for (const r of c.rocks) c.block.add(r[0] + ',' + r[1]);
    c.hmapBy = new Map();
    for (const h of c.hmap) c.hmapBy.set(h[0] + ',' + h[1], h[2]);
  };
  // 沿 (dx,dy) 可走格数：墙/岩/上行≥2 高差挡路（复刻 advanceStep 挡路规则；传送门格不挡）
  window.__qfWalk = (hx, hy, dx, dy) => {
    const c = window.__qfCache;
    const cols = c.cols || 24, rows = c.rows || 24;
    if (c.cols === 0) return 0;   // 快照未到，保守认为无空间
    let d = 0, x = hx, y = hy;
    let hCur = c.hmapBy.get(x + ',' + y) || 0;
    while (d < cols + rows) {
      x += dx; y += dy;
      if (x < 0 || y < 0 || x >= cols || y >= rows) break;
      const k = x + ',' + y;
      if (c.block.has(k)) break;
      const hT = c.hmapBy.get(k);
      if (hT !== undefined && hT - hCur >= 2) break;
      hCur = hT || 0;
      d++;
    }
    return d;
  };
  const KMAP = { '0,-1': 'ArrowUp', '0,1': 'ArrowDown', '-1,0': 'ArrowLeft', '1,0': 'ArrowRight' };
  const dirKey = d => KMAP[d[0] + ',' + d[1]];
  // 保命 v3：直行余量 ≥3 不管（≈2 拍存活窗，交给控制器/轮询下一拍再判）；<3 才拐——
  //  拐向余量 ≥2 → 拐（安全优先）；都 <2 但拐向 ≥1 且直行 ≤1 → 拐一格保一格；
  //  否则保持直行（拐进余量 0 = 撞岩自杀，v2 教训；v2 的 ≥4 门槛过苛 → 拐向全 <4 时原地等死）。
  // 统一头/向来源：服务端权威（快照 me，≤800ms 新鲜）优先，投影兜底。
  // 批38 v4 动机：死亡→复活后投影短暂指旧头，用它规划必撞崖/界（实证 60 死全是 cliff/wall）。
  window.__qfHeadDir = () => {
    const sv = window.__qfSrv;
    if (sv && performance.now() - sv.t < 800) return { x: sv.hx, y: sv.hy, dx: sv.dx, dy: sv.dy, alive: sv.alive, src: 'srv' };
    const s = window.__predState();
    const md = s.moveDir, h = s.proj && s.proj.cells && s.proj.cells[0];
    if (!md || !h) return null;
    return { x: h.x, y: h.y, dx: md.x, dy: md.y, alive: s.alive !== false, src: 'proj' };
  };
  window.__qfSurviveKey = () => {
    const st = window.__qfHeadDir();
    const md = { x: st && st.dx, y: st && st.dy }, h = st;
    if (!md || (md.x === 0 && md.y === 0) || !h) return null;
    const fwd = window.__qfWalk(h.x, h.y, md.x, md.y);
    if (fwd >= 3) return null;
    const cands = [[-md.y, md.x], [md.y, -md.x]]
      .map(c => [c, window.__qfWalk(h.x, h.y, c[0], c[1])]);
    cands.sort((a, b) => b[1] - a[1]);
    const best = cands[0];
    if (best[1] >= 2 || (best[1] >= 1 && fwd <= 1)) return dirKey(best[0]);
    return null;
  };
  // ---- 页内导航控制器（批38 二次迭代）----
  // node 侧逐 evaluate 导航 = 每按一键一个完整 RTT（~1.1s/press），蛇 150ms/步（speed 期 90ms）：
  // 实测 M1 3 个道具 0 吃到、M4 3 次 nav 全 ok=false。选向/按压/完成判定整体搬进页内 100ms 循环。
  window.__qfCtrl = { on: false, spec: null, done: false, presses: 0, noPath: 0, lastDir: null, lastPressAt: 0 };
  // BFS 多目标寻路：静态地形（block + 上行≥2）+ 自身身体（服务端按移动前 cells[1:] 判 self，含尾格）；
  // 传送门格不挡。返回首步方向 [dx,dy] 或 null（不可达 / 已在目标格 / 缓存未就绪）。
  window.__qfPlan = (hx, hy, mdx, mdy, tg) => {
    const c = window.__qfCache;
    if (!c.cols || !tg || !tg.size) return null;
    const cols = c.cols, rows = c.rows;
    let body = new Set();
    const sv = window.__qfSrv;
    if (sv && sv.body && performance.now() - sv.t < 800) {
      for (const k of sv.body) body.add(k);   // v4：服务端身体权威（投影体复活后失真）
    } else try {
      const s = window.__predState(), cells = (s.proj && s.proj.cells) || [];
      for (let i = 1; i < cells.length; i++) body.add(cells[i].x + ',' + cells[i].y);
    } catch (_) { /* 无预测体则只按静态地形 */ }
    const start = hx + ',' + hy;
    if (tg.has(start)) return null;
    const dirs = [[1, 0], [-1, 0], [0, 1], [0, -1]];
    const seen = new Set([start]);
    const q = [{ x: hx, y: hy, h: c.hmapBy.get(start) || 0, fd: null, first: true }];
    for (let qi = 0; qi < q.length && q.length <= cols * rows + 4; qi++) {
      const cur = q[qi];
      for (const dd of dirs) {
        if (cur.first && dd[0] === -mdx && dd[1] === -mdy) continue;   // 反向键被服务端忽略
        const nx = cur.x + dd[0], ny = cur.y + dd[1];
        if (nx < 0 || ny < 0 || nx >= cols || ny >= rows) continue;
        const k = nx + ',' + ny;
        if (seen.has(k) || c.block.has(k) || body.has(k)) continue;
        const hT = c.hmapBy.get(k);
        if (hT !== undefined && hT - cur.h >= 2) continue;
        const fd = cur.fd || dd;
        if (tg.has(k)) return fd;
        seen.add(k);
        q.push({ x: nx, y: ny, h: hT || 0, fd, first: false });
      }
    }
    return null;
  };
  // 页内保命循环（__qfKaOn 由 node 按阶段开关——记录窗口必须关，合成键会进 __qf.kd 污染量化）。
  // 导航控制器 on 时本循环让位（控制器内部已含保命兜底），避免两套按键互相踩踏。
  window.__qfKaOn = false;
  setInterval(() => {
    if (!window.__qfKaOn || window.__qfCtrl.on) return;
    try {
      const d = window.__stateDbg();
      if (!d || d.state !== 'playing' || !d.alive) return;
      const k = window.__qfSurviveKey();
      if (k) document.dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true }));
    } catch (_) { /* 助手未就绪忽略 */ }
  }, 120);
  // 导航控制器主循环：done 判定 → 多目标 BFS 选向 → 保命兜底，100ms 一拍。
  // done 时顺带 kaOn=false：踏门/吃道具后 ~100ms 即进入无输入观察窗（node 侧轮询再补一刀）。
  setInterval(() => {
    const C = window.__qfCtrl;
    if (!C.on || !C.spec) return;
    try {
      const d = window.__stateDbg();
      if (!d || d.state !== 'playing' || !d.alive) return;
      if (C.spec.mode === 'item') {
        if (window.__qfSpd > 0 || !window.__qfCache.items.some(i => i.id === C.spec.id)) {
          C.done = true; C.on = false; window.__qfKaOn = false; return;
        }
      } else {
        const t = window.__qfTeleports, e = t && t.length ? t[t.length - 1] : null;
        if (e && e.t >= C.spec.baseT && !e.db) {
          C.done = true; C.on = false; window.__qfKaOn = false; return;
        }
      }
      const st = window.__qfHeadDir();
      if (!st || !st.alive || (st.dx === 0 && st.dy === 0)) return;   // v4：复活后方向未下发时按 (0,0) 保守等下一拍
      const h = { x: st.x, y: st.y }, md = { x: st.dx, y: st.dy };
      let tg = null;
      if (C.spec.mode === 'item') {
        const sp = window.__qfCache.items.find(i => i.id === C.spec.id);
        tg = new Set(sp ? [sp.x + ',' + sp.y] : []);
      } else {
        tg = new Set(window.__qfCache.portals.map(p => p[0] + ',' + p[1]));
      }
      const press = k => {
        document.dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true }));
        C.presses++; C.lastPressAt = performance.now();
      };
      let dir = null;
      if (tg.size) dir = window.__qfPlan(h.x, h.y, md.x, md.y, tg);
      // v4：按下前用 __qfWalk 校验首格可走（规划与真实态间的 1-2 步漂移兜底，防崖/界死）
      if (dir && window.__qfWalk(h.x, h.y, dir[0], dir[1]) < 1) { dir = null; C.noPath++; }
      if (dir) {
        C.lastDir = dir.join(',');
        if (md.x === dir[0] && md.y === dir[1]) return;   // 已朝目标向，无需再按
        if (performance.now() - C.lastPressAt < 160) return;   // 等上一拍方向生效（一步 ≤150ms）
        press(dirKey(dir));
        return;
      }
      C.noPath++;
      const sv = window.__qfSurviveKey();   // 保命兜底：不可达 / 规划空
      if (sv) press(sv);
    } catch (_) { /* 助手未就绪忽略 */ }
  }, 100);
  window.__qfName = null;
  window.__qfSpd = 0;
  window.__qfMe = null;
  window.__qfSrv = null;   // 批38 v4：服务端权威 {hx,hy,dx,dy,alive,t}（快照 players.me），投影兜底
  // 批38 v5（关键）：默认 camFollow=true 时 setDir 把按键当「相对旋转」——x=0(↑/↓)直接忽略、
  // ←/→只左右转（index.html:2764）。绝对键全废 → 实证60死 cliff/wall 螺旋。切固定视角恢复绝对方向。
  // WS_PATCH 时机早于 btnCam 绑定时点击无效 → 由 node 侧在 join 后调 __qfCamFix（幂等，body.follow 判定）。
  window.__qfCamFix = () => {
    try {
      if (document.body.classList.contains('follow')) {
        const b = document.getElementById('btnCam');
        if (b) b.click();
      }
    } catch (_) { /* 未就绪忽略 */ }
  };
  window.__qfHeadOn = [];
  window.__qfDeaths = [];
  const Orig = window.WebSocket;
  window.WebSocket = function (url, protocols) {
    const ws = protocols === undefined ? new Orig(url) : new Orig(url, protocols);
    const origSend = ws.send.bind(ws);
    ws.send = data => {
      if (typeof data === 'string') {
        try {
          const o = JSON.parse(data);
          if (o.t === 'join' && o.name) window.__qfName = o.name;
          if (o.t === 'create') { o.portal = true; o.theme = 'day'; o.bots = 0; o.respawn = true; data = JSON.stringify(o); }
        } catch (_) { /* 非 JSON 帧原样放行 */ }
      }
      return origSend(data);
    };
    // 关键：不能用纯 JS defineProperty 拦截 onmessage——Chromium 的消息派发走原生
    // event listener 机制，绕过 JS 属性访问器（纯拦截=下行帧全部丢失，游戏卡 idle）。
    // 必须调原生 setter 注册真实监听器，在回调里包装后再转交原 handler。
    const origDesc = Object.getOwnPropertyDescriptor(Orig.prototype, 'onmessage');
    Object.defineProperty(ws, 'onmessage', {
      configurable: true,
      get() { return origDesc.get.call(ws); },
      set(f) {
        origDesc.set.call(ws, e => {
          try {
            const m = JSON.parse(e.data);
            const c = window.__qfCache;
            if (m.full) { c.portals = m.portals || []; c.items = m.items || []; }
            else {
              if (m.portals !== undefined) c.portals = m.portals;
              if (m.items !== undefined) c.items = m.items;
            }
            if (m.walls !== undefined) c.walls = m.walls;
            if (m.rocks !== undefined) c.rocks = m.rocks;
            if (m.hmap !== undefined) c.hmap = m.hmap;
            if (m.full || m.walls !== undefined || m.rocks !== undefined || m.hmap !== undefined) rebuildBlock();
            if (m.cols) c.cols = m.cols;
            if (m.rows) c.rows = m.rows;
            if (m.players) {
              // 客户端 join 常发空 name（playerName 默认空串）→ 名字找不到时按「非 bot 且非 off」定位（solo 房唯一人类）
              let me = window.__qfName ? m.players.find(p => p.name === window.__qfName) : null;
              if (!me) me = m.players.find(p => !p.bot && !p.off);
              window.__qfMe = me ? { id: me.id, name: me.name, bot: !!me.bot } : null;
              window.__qfSpd = me && me.eff ? (me.eff.speed || 0) : 0;
              // 批38 v4：服务端权威头/向/活存取（投影在死亡→复活后短暂失真，用它规划必撞崖/界——实证60死全是 cliff/wall）
              if (me && me.cells && me.cells[0] && me.dir) {
                window.__qfSrv = { hx: me.cells[0][0], hy: me.cells[0][1], dx: me.dir[0], dy: me.dir[1], alive: !!me.alive, t: performance.now(),
                  body: me.cells.slice(1).map(cc => cc[0] + ',' + cc[1]) };
              }
              if (me && me.alive && me.cells && me.cells[0] && me.dir) {
                const mx = me.cells[0][0], my = me.cells[0][1];
                for (const q of m.players) {
                  if (q.name === me.name || !q.alive || !q.cells || !q.cells[0] || !q.dir) continue;
                  const d = Math.abs(mx - q.cells[0][0]) + Math.abs(my - q.cells[0][1]);
                  const aligned = (my === q.cells[0][1] && me.dir[0] * q.dir[0] < 0)
                    || (mx === q.cells[0][0] && me.dir[1] * q.dir[1] < 0);
                  if (aligned && d <= 8) {
                    const last = window.__qfHeadOn[window.__qfHeadOn.length - 1];
                    if (!last || performance.now() - last.t > 500) {
                      window.__qfHeadOn.push({ t: performance.now(), dist: d, with: q.name });
                    }
                  }
                }
                if (window.__qfHeadOn.length > 200) window.__qfHeadOn.shift();
              }
            }
            // 死亡原因捕获（cause: wall/rock/cliff/self/stuck/crush/bite）：bots=0 房里 die 基本都是自己
            if (Array.isArray(m.ev)) {
              for (const e of m.ev) {
                if (e && e.t === 'die') {
                  window.__qfDeaths.push({ t: Math.round(performance.now()), cause: String(e.cause || '?'), by: (e.by == null ? null : e.by) });
                  if (window.__qfDeaths.length > 60) window.__qfDeaths.shift();
                }
              }
            }
          } catch (_) { /* 非快照帧忽略 */ }
          if (f) f(e);
        });
      },
    });
    return ws;
  };
  window.WebSocket.prototype = Orig.prototype;
};

// ---- page 内采样器（setInterval 16ms，不依赖 rAF；诊断实测 45-64 样本/秒正常） ----
const INJECT = () => {
  window.__qf = {
    rec: false, samples: [], kd: [], timer: null, sampleErr: null,
    start() {
      this.samples = []; this.kd = []; this.sampleErr = null; this.rec = true;
      window.__qfPrevHead = null;   // 批38：跨录段不产生伪踏门跳变
      window.__qfPrevAlive = null;
      if (!window.__qfTeleports) window.__qfTeleports = [];   // 批38 M4：跨录段累积（基线语义），导航后清空语义由 node 侧 base 控制
      if (this.timer) clearInterval(this.timer);
      this.timer = setInterval(() => {
        if (!this.rec) return;
        try {
          const s = window.__predState(), st = window.__stateDbg();
          const head = s.proj && s.proj.cells && s.proj.cells[0] ? [s.proj.cells[0].x, s.proj.cells[0].y] : null;
          // 批38 M4：踏门瞬移检测（正常移动 ≤1 格/样本；≥3 格跳变 → 事后用服务端 portals 验证）
          if (head) {
            const ph = window.__qfPrevHead;
            if (ph && Math.abs(head[0] - ph[0]) + Math.abs(head[1] - ph[1]) >= 3) {
              // db=deadBefore：跳变前一帧已死 → 服务端复活落点（serve.py :2171），必须排除——
              // 实测 M4 窗口 rawTele 12-15 全是复活跳变，0 个踏门被证实
              window.__qfTeleports.push({ t: performance.now(), from: ph.slice(), to: head.slice(), db: window.__qfPrevAlive === false });
              if (window.__qfTeleports.length > 60) window.__qfTeleports.shift();
            }
            window.__qfPrevHead = head;
          }
          window.__qfPrevAlive = !!st.alive;
          window.__qf.samples.push({
            t: performance.now(),
            st: st.state, alive: !!st.alive,
            md: s.moveDir ? [s.moveDir.x, s.moveDir.y] : null,
            pv: s.previewDir ? [s.previewDir.x, s.previewDir.y] : null,
            head: head,
            spd: window.__qfSpd || 0,
            act: s.active, cols: s.cols, rows: s.rows,
          });
        } catch (e) { window.__qf.sampleErr = String(e); }
      }, 16);
    },
    stop() {
      this.rec = false;
      if (this.timer) { clearInterval(this.timer); this.timer = null; }
      return { samples: this.samples.slice(), kd: this.kd.slice(), sampleErr: this.sampleErr };
    },
  };
  if (!window.__qfKdBound) {
    window.__qfKdBound = true;
    window.addEventListener('keydown', e => {
      if (window.__qf && window.__qf.rec) window.__qf.kd.push({ t: performance.now(), k: e.key });
    }, true);
  }
};

// 注意：Playwright evaluate 只接受 1 个参数——多值一律打包成单数组传入。
const evalTo = async (page, fn, name, ms = 10000, arg = undefined) => {
  let timer;
  try {
    return await Promise.race([
      page.evaluate(fn, arg),
      new Promise((_, rej) => { timer = setTimeout(() => rej(new Error('EVAL_TIMEOUT[' + name + '] ' + ms + 'ms')), ms); }),
    ]);
  } finally { clearTimeout(timer); }
};
const pageState = p => evalTo(p, () => window.__stateDbg(), 'pageState');
const predState = p => evalTo(p, () => window.__predState(), 'predState');
const startRec = p => evalTo(p, () => window.__qf.start(), 'startRec');
const stopRec = p => evalTo(p, () => window.__qf.stop(), 'stopRec');

const eq = (a, b) => a && b && a[0] === b[0] && a[1] === b[1];
const pressKey = { '0,-1': 'ArrowUp', '0,1': 'ArrowDown', '-1,0': 'ArrowLeft', '1,0': 'ArrowRight' };

// solo 房 respawn=False（serve.py _msg_respawn: room.respawn 才放行）→ 死亡无法复活，
// 只能开新局：goto('/') → btnSolo → 重注探针。
async function ensurePlaying(page, tag) {
  let bad = '';
  try {
    const s = await pageState(page);
    if (s.state === 'playing' && s.alive) return true;
    bad = `state=${s.state} alive=${s.alive}`;
  } catch (e) {
    bad = 'pageState fail ' + String(e).slice(0, 60);
  }
  // 复活房（create 带 respawn:true）：服务端 RESPAWN_MS=3000 自动复活（serve.py :2171），
  // 瞬态 over 是正常节拍 → 先等 ≤8s；死透/换局才开新命（goto+btnSolo）。
  console.log(`[${tag}] ${bad} → wait auto-respawn ≤8s`);
  const t0 = Date.now();
  while (Date.now() - t0 < 8000) {
    await page.waitForTimeout(700);
    try {
      const s2 = await pageState(page);
      if (s2.state === 'playing' && s2.alive) { console.log(`[${tag}] auto-respawned in ${Date.now() - t0}ms`); return true; }
    } catch (_) { /* 继续等 */ }
  }
  console.log(`[${tag}] no respawn → new solo life`);
  try {
    await page.goto('/');
    await page.waitForFunction(() => typeof window.__stateDbg === 'function' && typeof window.__predState === 'function', null, { timeout: 20000 });
    await page.click('#btnSolo');
    await page.waitForFunction(() => {
      const sc = document.getElementById('startScreen');
      return sc && sc.classList.contains('hidden');
    }, null, { timeout: 20000 });
    await page.waitForFunction(() => {
      const s = window.__stateDbg();
      return s.state === 'playing' && s.alive && window.__predState().active;
    }, null, { timeout: 20000 });
    await evalTo(page, INJECT, 'inject');
    // 批38 v5：新局页面 camFollow 复位为 true → 再切一次固定视角
    await evalTo(page, () => { if (typeof window.__qfCamFix === 'function') window.__qfCamFix(); });
    return true;
  } catch (e) {
    console.log(`[${tag}] newLife FAILED: ${String(e).slice(0, 120)}`);
    return false;
  }
}

async function pickTurn(page) {
  return evalTo(page, () => {
    const s = window.__predState();
    const md = s.moveDir;
    // 防御：dir 未就绪时 moveDir 可能为 {0,0}（零向量），任何越界循环都会永不终止
    if (!md || (md.x === 0 && md.y === 0)) return { err: 'badMoveDir', md: md, hasProj: !!(s.proj && s.proj.cells && s.proj.cells.length) };
    if (!s.proj || !s.proj.cells.length) return { err: 'noProj' };
    const h = s.proj.cells[0], K = 3, LIM = Math.max(s.cols, s.rows) + 2;
    const cands = [[-md.y, md.x], [md.y, -md.x]];
    const borderDist = c => {
      let d = 0;
      while (d < LIM) {
        const nx = h.x + c[0] * (d + 1), ny = h.y + c[1] * (d + 1);
        if (nx < 0 || nx >= s.cols || ny < 0 || ny >= s.rows) break;
        d++;
      }
      return d;
    };
    // 批38：障碍感知——default 主题 rock=1.0，只看边界的选向会直转进岩石（实测 Q1 全 null / M1 保命失效）
    const dist = window.__qfWalk ? (c => window.__qfWalk(h.x, h.y, c[0], c[1])) : borderDist;
    const ok = cands.filter(c => dist(c) >= K);
    if (!ok.length) return { err: 'corner', md: [md.x, md.y], head: [h.x, h.y], cols: s.cols, rows: s.rows };
    ok.sort((a, b) => dist(b) - dist(a));
    return { target: ok[0], head: [h.x, h.y] };
  }, 'pickTurn');
}

async function headroom(page) {
  return evalTo(page, () => {
    const s = window.__predState();
    const md = s.moveDir;
    if (!md || (md.x === 0 && md.y === 0)) return -99;   // 零向量：任何无向循环都会死，直接短路
    if (!s.proj || !s.proj.cells.length) return -1;
    const h = s.proj.cells[0], LIM = Math.max(s.cols, s.rows) + 2;
    if (window.__qfWalk) return window.__qfWalk(h.x, h.y, md.x, md.y);   // 批38：障碍感知（Q2 门槛直行段免撞岩）
    let d = 0;
    while (d < LIM) {
      const nx = h.x + md.x * (d + 1), ny = h.y + md.y * (d + 1);
      if (nx < 0 || nx >= s.cols || ny < 0 || ny >= s.rows) break;
      d++;
    }
    return d;
  }, 'headroom');
}

// ---- 批38 v3：导航 = 启动页内控制器 + 轮询（选向/按压/完成判定都在页内 100ms 循环，见 WS_PATCH __qfCtrl）----
// target 仅留作日志/向后兼容（页内对 item 用 spec.id 单目标、对 jump 用全部门格多目标 BFS）。
// spec={mode:'item',id} 道具被吃/消失即完成；{mode:'jump',baseT} 出现 baseT 之后的非复活瞬移（踏门）即完成。
async function navToward(page, target, spec, tag, maxMs) {
  const deadline = Date.now() + maxMs;
  let deadTicks = 0, presses = 0, lastNoPath = 0;
  try {
    await evalTo(page, a => {
      if (typeof window.__qfCamFix === 'function') window.__qfCamFix();   // 批38 v5：保险（幂等，follow 才点）
      const C = window.__qfCtrl;
      C.on = true; C.done = false; C.presses = 0; C.noPath = 0;
      C.lastDir = null; C.lastPressAt = 0; C.spec = a.spec;
    }, tag + '.start', 10000, { spec: spec });
  } catch (e) { return { ok: false, presses: 0, err: String(e).slice(0, 80) }; }
  try {
    while (Date.now() < deadline) {
      let st;
      try {
        st = await evalTo(page, () => {
          const C = window.__qfCtrl;
          const d = window.__stateDbg();
          return { done: C.done, alive: !!(d && d.state === 'playing' && d.alive), presses: C.presses, noPath: C.noPath };
        }, tag + '.poll', 10000);
      } catch (e) { return { ok: false, presses, noPath: lastNoPath, err: String(e).slice(0, 80) }; }
      presses = st.presses;
      lastNoPath = st.noPath;
      if (st.done) return { ok: true, presses, noPath: st.noPath };
      if (!st.alive) {
        deadTicks++;
        if (deadTicks > 3) return { ok: false, presses, dead: true, noPath: st.noPath };   // 复活房：等满仍死才放弃
        await page.waitForTimeout(2500);   // 服务端 RESPAWN_MS=3000 自动复活，等两拍
        continue;
      }
      deadTicks = 0;
      await page.waitForTimeout(250);
    }
    return { ok: false, presses, timeout: true, noPath: lastNoPath };
  } finally {
    try { await evalTo(page, () => { window.__qfCtrl.on = false; window.__qfCtrl.spec = null; }, tag + '.stop', 5000); }
    catch (_) { /* 收尾失败不阻断 */ }
  }
}

// ---- 批38 M1：等待 speed 道具出现在嗅探缓存（spawn 0.0025/tick × 20tick/s ÷ 7 类 ≈ 均值 140s）----
// keepAlive=true：每次轮询做一次保命检查（前方余量 <10 先拐弯），否则无输入蛇 ~3.5s 撞墙死。
async function waitForSpeedItem(page, maxMs, keepAlive) {
  const deadline = Date.now() + maxMs;
  let lastLog = 0;
  while (Date.now() < deadline) {
    if (keepAlive) {
      try {
        const sv = await evalTo(page, () => window.__qfSurviveKey(), 'kaSurvive');
        if (sv) await page.keyboard.press(sv);
      } catch (e) { /* 保命失败不阻断等待 */ }
    }
    try {
      // 批38 二次迭代：取距头最近的 speed 道具（旧版取缓存第一个——常是远处/快过期的，16s nav 追不上）
      const r = await evalTo(page, () => {
        const c = window.__qfCache;
        const sp = c.items.filter(i => i.type === 'speed');
        if (!sp.length) return null;
        const s = window.__predState();
        const h = s.proj && s.proj.cells && s.proj.cells[0];
        if (h) sp.sort((a, b) => (Math.abs(a.x - h.x) + Math.abs(a.y - h.y)) - (Math.abs(b.x - h.x) + Math.abs(b.y - h.y)));
        return { id: sp[0].id, x: sp[0].x, y: sp[0].y, n: sp.length };
      }, 'waitSpeedItem');
      if (r) return r;
    } catch (e) { return null; }
    if (Date.now() - lastLog > 15000) { console.log(`[M1] waiting speed item... ${Math.round((deadline - Date.now()) / 1000)}s left`); lastLog = Date.now(); }
    await page.waitForTimeout(500);
  }
  return null;
}

// ---- 批38 M4：踏门事件验证 + 踏门后 1.5s 观察窗分析 ----
// teleport 事件（采样 ≥3 格跳变）须与服务端 portals 对证实：from 紧邻门格 A（曼哈顿 ≤1）且 to == 对偶门格 B。
function analyzePortal(seg, tele, portals) {
  const pairs = [];
  for (let i = 0; i + 1 < portals.length; i += 2) pairs.push([portals[i], portals[i + 1]]);
  const near = (a, b) => Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]) <= 1;
  const S = seg.samples;
  const t0 = S.length ? S[0].t : 0, t1 = S.length ? S[S.length - 1].t : 0;
  const events = [];
  let respawnFiltered = 0;
  for (const ev of tele) {
    if (ev.t < t0 || ev.t > t1) continue;
    if (ev.db === true) { respawnFiltered++; continue; }   // 复活落点跳变不是踏门
    const pair = pairs.find(([a, b]) => (near(ev.from, a) && eq(ev.to, b)) || (near(ev.from, b) && eq(ev.to, a)));
    if (!pair) continue;
    const win = S.filter(s => s.t >= ev.t && s.t <= ev.t + 1500);
    const a = analyzeStraight({ samples: win, kd: [] });
    events.push({
      from: ev.from, to: ev.to, postFrames: win.length,
      mdChanges: a.mdChanges, mdReversals: a.mdReversals, headBounces: a.headBounces,
      endedAlive: a.endedAlive,
    });
  }
  return { crossings: events.length, events, rawTeleports: tele.length, respawnFiltered: respawnFiltered };
}

function analyzeTrial(tr, samples, kdT) {
  const firstAfter = fn => { for (const s of samples) { if (s.t >= kdT && fn(s)) return s.t; } return null; };
  const pvT = firstAfter(s => eq(s.pv, tr.target));
  const mdT = firstAfter(s => eq(s.md, tr.target));
  const headT = firstAfter(s => {
    if (!s.head || !tr.head) return false;
    const dx = s.head[0] - tr.head[0], dy = s.head[1] - tr.head[1];
    return (dx !== 0 || dy !== 0) && Math.sign(dx) === Math.sign(tr.target[0])
      && Math.sign(dy) === Math.sign(tr.target[1]) && Math.abs(dx) + Math.abs(dy) === 1;
  });
  return {
    target: tr.target, key: pressKey[tr.target.join(',')],
    pvLat: pvT == null ? null : +(pvT - kdT).toFixed(1),
    mdLat: mdT == null ? null : +(mdT - kdT).toFixed(1),
    headLat: headT == null ? null : +(headT - kdT).toFixed(1),
    aliveAtEnd: samples.length ? samples[samples.length - 1].alive : false,
  };
}

function analyzeStraight(seg) {
  let bounces = 0, mdChanges = 0, mdReversals = 0;
  const S = seg.samples;
  for (let i = 1; i < S.length; i++) {
    if (S[i].md && S[i - 1].md && !eq(S[i].md, S[i - 1].md)) {
      mdChanges++;
      if (eq(S[i].md, [-S[i - 1].md[0], -S[i - 1].md[1]])) mdReversals++;
    }
    if (i >= 2 && S[i].head && S[i - 1].head && S[i - 2].head
      && eq(S[i].head, S[i - 2].head) && !eq(S[i].head, S[i - 1].head)) bounces++;
  }
  return {
    durMs: S.length ? +(S[S.length - 1].t - S[0].t).toFixed(0) : 0,
    frames: S.length, keysPressed: seg.kd.map(k => k.k),
    mdChanges, mdReversals, headBounces: bounces,
    endedAlive: S.length ? S[S.length - 1].alive : false,
    sampleErr: seg.sampleErr || null,
  };
}

function analyzeEnd(seg) {
  const S = seg.samples.filter(s => s.st === 'over' || s.st === 'win');
  let headMoves = 0, headBounces = 0, mdChanges = 0;
  const seq = S.filter(s => s.head);
  for (let i = 1; i < seq.length; i++) {
    // 批38 复活房：over 窗口可能有多段（死→复活→再死），段间隔是一整段 playing（秒级），
    // 采样断层 >300ms 视为跨窗口边界不计移动（否则复活落点虚增 headMoves——实测 0→10）
    if (seq[i].t - seq[i - 1].t > 300) continue;
    if (!eq(seq[i].head, seq[i - 1].head)) headMoves++;
    if (i >= 2 && seq[i - 1].t - seq[i - 2].t <= 300 && eq(seq[i].head, seq[i - 2].head) && !eq(seq[i].head, seq[i - 1].head)) headBounces++;
  }
  for (let i = 1; i < S.length; i++) if (S[i].md && S[i - 1].md && !eq(S[i].md, S[i - 1].md)) mdChanges++;
  return {
    frames: S.length, states: [...new Set(S.map(s => s.st))],
    headMoves, headBounces, mdChanges,
    durMs: S.length ? +(S[S.length - 1].t - S[0].t).toFixed(0) : 0,
    sampleErr: seg.sampleErr || null,
  };
}

(async () => {
  const report = { base: BASE, at: new Date().toISOString(), q1_turn: [], q2_straight: null, q3_end: null, m1_speed: null, m4_portal: null, m4b_headon: null, notes: [] };
  const errs = [];
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const ctx = await browser.newContext({ baseURL: BASE, viewport: { width: 1280, height: 800 } });
    await ctx.addInitScript(WS_PATCH);   // 批38：先于游戏脚本跑，嗅探 ws + 改写 create（零游戏代码改动）
    const page = await ctx.newPage();
    page.on('pageerror', e => errs.push('pageerror: ' + String(e)));
    page.on('console', m => { if (m.type() === 'error') errs.push('console: ' + m.text()); });
    page.on('crash', () => errs.push('PAGE CRASH'));
    page.on('framenavigated', f => { if (f === page.mainFrame()) errs.push('NAV: ' + f.url()); });

    await page.goto('/');
    await page.waitForFunction(() => typeof window.__stateDbg === 'function' && typeof window.__predState === 'function', null, { timeout: 20000 });
    console.log('[step] goto ok, clicking btnSolo');
    await page.click('#btnSolo');
    await page.waitForFunction(() => {
      const sc = document.getElementById('startScreen');
      return sc && sc.classList.contains('hidden');
    }, null, { timeout: 20000 });
    await page.waitForFunction(() => {
      const s = window.__stateDbg();
      return s.state === 'playing' && s.alive && window.__predState().active;
    }, null, { timeout: 20000 });
    await evalTo(page, INJECT, 'inject');
    // 批38 v5：默认 camFollow=true 时按键是相对旋转（绝对键全废）→ 切固定视角。
    // 此时 btnCam 已存在并绑好（game-ui 在 startScreen 之前渲染），点击必生效。
    const cam0 = await evalTo(page, () => { window.__qfCamFix(); return document.body.classList.contains('follow'); });
    console.log(`[step] camFix: follow-after=${cam0} (期望 false)`);
    console.log('[step] in game, Q1 begin');

    // ---- Q1：取 6 个有效转向延迟（死亡 → respawn 恢复）----
    let tries = 0;
    while (report.q1_turn.length < 6 && tries < 14) {
      tries++;
      if (!(await ensurePlaying(page, 'Q1'))) { report.notes.push(`Q1 try${tries}: cannot reach playing`); break; }
      const tr = await pickTurn(page);
      if (tr && tr.err) {
        console.log(`[Q1] try${tries}: pickTurn err=${JSON.stringify(tr)}`);
        if (tr.err === 'corner') { report.notes.push(`Q1 try${tries}: corner ${JSON.stringify(tr)}`); await page.waitForTimeout(700); continue; }
        report.notes.push(`Q1 try${tries}: ${tr.err} retry`);
        await page.waitForTimeout(600);
        continue;
      }
      if (!tr) { console.log(`[Q1] try${tries}: pickTurn returned nothing`); break; }
      await startRec(page);
      await page.waitForTimeout(120);
      await page.keyboard.press(pressKey[tr.target.join(',')]);
      await page.waitForTimeout(900);
      const seg = await stopRec(page);
      const kdHit = seg.kd.find(k => k.k === pressKey[tr.target.join(',')]);
      if (!seg.samples.length) { console.log(`[Q1] try${tries}: EMPTY samples err=${seg.sampleErr}`); continue; }
      const aliveEnd = seg.samples[seg.samples.length - 1].alive;
      if (!kdHit || !aliveEnd) { console.log(`[Q1] try${tries}: kd=${!!kdHit} aliveEnd=${aliveEnd} discard`); continue; }
      const r = analyzeTrial(tr, seg.samples, kdHit.t);
      report.q1_turn.push(r);
      console.log(`[Q1] try${tries} ${r.key} pv=${r.pvLat} md=${r.mdLat} head=${r.headLat}`);
    }

    console.log('[step] Q1 done (' + report.q1_turn.length + '/6), Q2 begin');
    // ---- Q2：无输入直行段（余量 ≥12 才录；死亡 → respawn 重试 ≤4）----
    let q2Adj = 0;
    for (let attempt = 0; attempt < 4 && !report.q2_straight; attempt++) {
      if (!(await ensurePlaying(page, 'Q2'))) { report.notes.push(`Q2 a${attempt}: cannot reach playing`); break; }
      const hr = await headroom(page);
      if (hr < 12) {
        const tr = await pickTurn(page);
        console.log(`[Q2] a${attempt} hr=${hr} turn=${tr && !tr.err ? JSON.stringify(tr.target) : JSON.stringify(tr)}`);
        if (!tr || tr.err || ++q2Adj > 8) { report.notes.push(`Q2 a${attempt}: hr=${hr} adj=${q2Adj} tr=${tr && tr.err ? tr.err : String(!!tr)} give up`); continue; }
        await page.keyboard.press(pressKey[tr.target.join(',')]);
        await page.waitForTimeout(500);
        attempt--; // 转向不算一次尝试（q2Adj 兜底防自旋）
        continue;
      }
      await startRec(page);
      await page.waitForTimeout(2500);
      const seg = await stopRec(page);
      const last = seg.samples[seg.samples.length - 1];
      console.log(`[Q2] a${attempt} hr=${hr} frames=${seg.samples.length} keys=${seg.kd.length} aliveEnd=${last ? last.alive : 'n/a'} st=${last ? last.st : 'n/a'}`);
      if (seg.kd.length || !seg.samples.length || !last.alive) {
        report.notes.push(`Q2 a${attempt}: keys=${seg.kd.length} frames=${seg.samples.length} aliveEnd=${last ? last.alive : 'n/a'} retry`);
        continue;
      }
      report.q2_straight = analyzeStraight(seg);
    }
    if (!report.q2_straight) report.notes.push('Q2: no valid straight segment collected');

    // ---- Q3：停手 → 死 → over→win 结算窗口 ----
    console.log('[step] Q2 done, Q3 begin (wait over→win, cap 90s)');
    if (!(await ensurePlaying(page, 'Q3'))) report.notes.push('Q3: newLife failed');
    await startRec(page);
    const deadline = Date.now() + 90000;
    let sawOver = false, lastLog = 0;
    while (Date.now() < deadline) {
      const s = await pageState(page);
      if (s.state === 'over') sawOver = true;
      if (s.state === 'win') break;
      if (sawOver && Date.now() > deadline - 30000) break; // over 后 60s 仍未 win → 用现有窗口
      if (Date.now() - lastLog > 10000) { console.log(`[Q3] state=${s.state} sawOver=${sawOver}`); lastLog = Date.now(); }
      await page.waitForTimeout(500);
    }
    await page.waitForTimeout(4000);
    const endSeg = await stopRec(page);
    report.q3_end = analyzeEnd(endSeg);
    console.log(`[Q3] frames(all)=${endSeg.samples.length} endFrames=${report.q3_end.frames}`);
    if (!report.q3_end.frames) report.notes.push('Q3: no over/win frames captured');

    // ---- M1：吃 speed 道具（eff.speed>0 窗口）无输入段 —— 方向翻转/回弹计数 ----
    // 同命内循环（等→追→没吃到继续等）；道具 spawn 均值 ~140s 且保质期仅 12s（可能被 bot 抢吃），
    // 死亡才开新命，摊薄等待成本。≤3 条命。
    console.log('[step] Q3 done, M1 begin (≤3 lives, per-life wait ≤150s)');
    for (let life = 0; life < 3 && !report.m1_speed; life++) {
      if (!(await ensurePlaying(page, 'M1'))) { report.notes.push(`M1 life${life}: cannot reach playing`); break; }
      await evalTo(page, () => { window.__qfKaOn = true; }, 'kaOn1');   // 等/追道具期间页内保命
      const lifeDeadline = Date.now() + 150000;
      while (Date.now() < lifeDeadline && !report.m1_speed) {
        if (!(await ensurePlaying(page, 'M1'))) { report.notes.push(`M1 life${life}: cannot recover`); break; }
        const it = await waitForSpeedItem(page, Math.min(45000, lifeDeadline - Date.now()), true);
        if (!it) continue;   // 窗口内没等到：回循环顶再查存活/继续等
        console.log(`[M1] life${life} speed item at (${it.x},${it.y}) navigating`);
        const nav = await navToward(page, [it.x, it.y], { mode: 'item', id: it.id }, 'M1nav', 16000);
        const spdNow = await evalTo(page, () => window.__qfSpd, 'm1Spd').catch(() => 0);
        if (!(spdNow > 0)) {
          report.notes.push(`M1 life${life}: item (${it.x},${it.y}) not eaten (nav ok=${nav.ok}${nav.err ? ' err=' + nav.err : ''}${nav.timeout ? ' TIMEOUT' : ''}) — likely expired/stolen, continue`);
          continue;
        }
        // 吃到后转向找长直道：speed 期 90ms/步，3.2s 记录窗 ≈35 步——hr 太短会中途撞死污染窗口
        let hr = await headroom(page);
        for (let g = 0; g < 10 && hr >= 0 && hr < 18; g++) {
          const pt = await pickTurn(page);
          if (pt && pt.target) await page.keyboard.press(pressKey[pt.target.join(',')]);
          await page.waitForTimeout(320);
          hr = await headroom(page);
        }
        await evalTo(page, () => { window.__qfKaOn = false; }, 'kaOff1');   // 记录窗口禁保命（合成键污染 kd）
        await startRec(page);
        await page.waitForTimeout(3200);   // eff.speed 6000ms 窗口内取无输入段
        const seg = await stopRec(page);
        await evalTo(page, () => { window.__qfKaOn = true; }, 'kaOn1r');
        const deaths1 = await evalTo(page, () => window.__qfDeaths.splice(0), 'm1Deaths').catch(() => []);
        if (deaths1.length) console.log(`[M1] life${life} deaths: ` + JSON.stringify(deaths1));
        const S = seg.samples.filter(s => s.spd > 0 && s.alive);   // 死亡残帧不算 speed 窗口
        console.log(`[M1] life${life} ate: spdFrames=${S.length} keys=${seg.kd.length} hr=${hr} navPresses=${nav.presses} noPath=${nav.noPath}`);
        if (S.length < 10) { report.notes.push(`M1 life${life}: spd window frames=${S.length} <10 (hr=${hr}), continue`); continue; }
        const a = analyzeStraight({ samples: S, kd: seg.kd });
        report.m1_speed = {
          ...a,
          headroomAtEat: hr,
          maxSpdMs: Math.max(...S.map(s => s.spd)),
          windowMs: +(S[S.length - 1].t - S[0].t).toFixed(0),
        };
      }
    }
    if (!report.m1_speed) report.notes.push('M1: no valid speed-window segment collected');

    // ---- M4：传送门穿越（页内 BFS 多目标导航到最近可达门格，踏门跳变须服务端 portals 对证实）----
    console.log('[step] M1 done, M4 begin');
    const m4trials = [];
    let m4cross = 0;
    for (let attempt = 0; attempt < 3 && m4cross < 2; attempt++) {
      if (!(await ensurePlaying(page, 'M4'))) { report.notes.push(`M4 a${attempt}: cannot reach playing`); break; }
      const portals = await evalTo(page, () => window.__qfCache.portals.slice(), 'm4Portals').catch(() => null);
      if (!portals || !portals.length) { report.notes.push('M4: room has no portals in sniff cache'); break; }
      const tgt = await evalTo(page, ps => {
        const s = window.__predState();
        const h = s.proj && s.proj.cells && s.proj.cells[0];
        if (!h) return null;
        let best = null, bd = Infinity;
        for (const c of ps) { const d = Math.abs(c[0] - h.x) + Math.abs(c[1] - h.y); if (d < bd) { bd = d; best = c; } }
        return best;
      }, 'm4Pick', 10000, portals).catch(e => { report.notes.push(`M4 a${attempt}: m4Pick err=${String(e).slice(0, 120)}`); return null; });
      if (!tgt) { report.notes.push(`M4 a${attempt}: no head/target`); continue; }
      const baseT = await evalTo(page, () => performance.now(), 'm4BaseT').catch(() => 0);
      await evalTo(page, () => { window.__qfKaOn = true; }, 'kaOn4');   // 导航期间页内保命
      await startRec(page);
      const nav = await navToward(page, tgt, { mode: 'jump', baseT: baseT }, 'M4nav', 20000);
      await evalTo(page, () => { window.__qfKaOn = false; }, 'kaOff4');   // 观察窗禁保命（回弹计数须无输入）
      if (!nav.dead) await page.waitForTimeout(2000);   // 踏门后观察窗（死亡则立即收段）
      const seg = await stopRec(page);
      const tele = await evalTo(page, () => window.__qfTeleports.slice(), 'm4Tele').catch(() => []);
      const r = analyzePortal(seg, tele, portals);
      const last = seg.samples[seg.samples.length - 1];
      const deaths4 = await evalTo(page, () => window.__qfDeaths.splice(0), 'm4Deaths').catch(() => []);
      if (deaths4.length) console.log(`[M4] a${attempt} deaths: ` + JSON.stringify(deaths4));
      console.log(`[M4] a${attempt} nav ok=${nav.ok} presses=${nav.presses} noPath=${nav.noPath} crossings=${r.crossings} rawTele=${r.rawTeleports} aliveEnd=${last ? last.alive : 'n/a'}`);
      if (r.crossings > 0) {
        m4cross += r.crossings;
        m4trials.push({ attempt, navPresses: nav.presses, ...r, aliveEnd: last ? last.alive : false });
      } else {
        report.notes.push(`M4 a${attempt}: 0 crossings (rawTele=${r.rawTeleports}, nav ok=${nav.ok}${nav.timeout ? ' TIMEOUT' : ''}${nav.dead ? ' DEAD' : ''}${nav.err ? ' err=' + nav.err : ''})`);
      }
    }
    if (m4trials.length) report.m4_portal = { totalCrossings: m4cross, trials: m4trials };
    else report.notes.push('M4: no portal crossing collected');

    // ---- M4b：对头追击（尽力而为；嗅探缓存里同轴对向事件）----
    try {
      const ho = await evalTo(page, () => window.__qfHeadOn.slice(), 'm4bHeadOn');
      report.m4b_headon = { events: ho.length, sample: ho.slice(0, 10), note: 'best-effort; 对头致死仅当 M4 段 aliveEnd=false' };
    } catch (e) { report.m4b_headon = { events: null, err: String(e).slice(0, 80) }; }

    report.allErrs = errs;
    fs.mkdirSync(path.dirname(OUT), { recursive: true });
    fs.writeFileSync(OUT, JSON.stringify(report, null, 2));
    console.log('Q1_turn=' + JSON.stringify(report.q1_turn));
    console.log('Q2_straight=' + JSON.stringify(report.q2_straight));
    console.log('Q3_end=' + JSON.stringify(report.q3_end));
    console.log('M1_speed=' + JSON.stringify(report.m1_speed));
    console.log('M4_portal=' + JSON.stringify(report.m4_portal));
    console.log('M4b_headon=' + JSON.stringify(report.m4b_headon));
    console.log('NOTES=' + JSON.stringify(report.notes));
    console.log('ALL_ERRS=' + JSON.stringify(errs));
    console.log('OUT=' + OUT);
    const m4ok = report.m4_portal && report.m4_portal.totalCrossings > 0;
    const fatal = report.q1_turn.length === 0 && !report.q2_straight && !report.q3_end && !report.m1_speed && !m4ok;
    console.log('VERDICT=' + (fatal ? 'fail' : 'pass'));
    await browser.close();
    process.exit(fatal ? 1 : 0);
  } catch (e) {
    console.error('FATAL', (e && e.stack) || e);
    try {
      const pages = browser.contexts().flatMap(c => c.pages());
      for (const pg of pages) {
        console.log('FORENSICS url=', pg.url());
        await pg.screenshot({ path: path.join(path.dirname(OUT), 'qf_fatal.png'), timeout: 5000 }).catch(x => console.log('shot fail', String(x)));
      }
    } catch (x) { console.log('forensics fail', String(x)); }
    console.log('ERRS_SO_FAR=' + JSON.stringify(errs));
    if (browser) await browser.close().catch(() => {});
    process.exit(2);
  }
})();
