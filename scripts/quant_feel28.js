#!/usr/bin/env node
// 批37 项11：批28 §7.3 转向手感量化
//
// spec：docs/superpowers/specs/2026-10-16-prediction-design.md §7.3（需人测五点）
//   本脚本自动化其中三组可量化数据：
//     Q1 转向跟手  —— 按键 → previewDir / moveDir / 渲染头 的响应延迟（ms）
//     Q2 开放地无回弹 —— 无输入直行段：方向翻转数 + 头坐标 A→B→A 回弹数
//     Q3 局末结算窗口不抖（M3） —— over→win 段：头坐标来回跳变数
//   留人测（不自动化，与 spec 原口径一致）：
//     M1 吃 speed 道具期间不抖；进传送门/对头时允许一次回弹
//
// 用法（本地服）：
//   $env:PORT='8123'; Start-Process .venv\Scripts\python.exe -ArgumentList serve.py -WindowStyle Hidden
//   node scripts/quant_feel28.js [--base http://127.0.0.1:8123] [--out test-results/quant_feel28.json]
//
// 退出码：0 = 数据采集成功（不代表手感结论——结论由用户看数据判断）；1 = 数据全空；2 = 致命。
// v4：solo 房 respawn=False → 死亡恢复=开新局（goto+btnSolo+重注探针）；
//     页内循环全部有界（零向量 dir={0,0} 时原无限循环会挂死 renderer）。
'use strict';
const { chromium } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf('--' + k); return i >= 0 && args[i + 1] ? args[i + 1] : d; };
const BASE = opt('base', 'http://127.0.0.1:8123');
const OUT = opt('out', path.join('test-results', 'quant_feel28.json'));

// ---- page 内采样器（setInterval 16ms，不依赖 rAF；诊断实测 45-64 样本/秒正常） ----
const INJECT = () => {
  window.__qf = {
    rec: false, samples: [], kd: [], timer: null, sampleErr: null,
    start() {
      this.samples = []; this.kd = []; this.sampleErr = null; this.rec = true;
      if (this.timer) clearInterval(this.timer);
      this.timer = setInterval(() => {
        if (!this.rec) return;
        try {
          const s = window.__predState(), st = window.__stateDbg();
          window.__qf.samples.push({
            t: performance.now(),
            st: st.state, alive: !!st.alive,
            md: s.moveDir ? [s.moveDir.x, s.moveDir.y] : null,
            pv: s.previewDir ? [s.previewDir.x, s.previewDir.y] : null,
            head: s.proj && s.proj.cells && s.proj.cells[0] ? [s.proj.cells[0].x, s.proj.cells[0].y] : null,
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

const evalTo = async (page, fn, name, ms = 10000) => {
  let timer;
  try {
    return await Promise.race([
      page.evaluate(fn),
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
  try {
    const s = await pageState(page);
    if (s.state === 'playing' && s.alive) return true;
    console.log(`[${tag}] state=${s.state} alive=${s.alive} → new solo life`);
  } catch (e) {
    console.log(`[${tag}] pageState fail (${String(e).slice(0, 80)}) → new solo life`);
  }
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
    const h = s.proj.cells[0], K = 6, LIM = Math.max(s.cols, s.rows) + 2;
    const cands = [[-md.y, md.x], [md.y, -md.x]];
    const ok = cands.filter(c => {
      const x = h.x + c[0] * K, y = h.y + c[1] * K;
      return x >= 0 && x < s.cols && y >= 0 && y < s.rows;
    });
    if (!ok.length) return { err: 'corner', md: [md.x, md.y], head: [h.x, h.y], cols: s.cols, rows: s.rows };
    const dist = c => {
      let d = 0;
      while (d < LIM) {
        const nx = h.x + c[0] * (d + 1), ny = h.y + c[1] * (d + 1);
        if (nx < 0 || nx >= s.cols || ny < 0 || ny >= s.rows) break;
        d++;
      }
      return d;
    };
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
    let d = 0;
    while (d < LIM) {
      const nx = h.x + md.x * (d + 1), ny = h.y + md.y * (d + 1);
      if (nx < 0 || nx >= s.cols || ny < 0 || ny >= s.rows) break;
      d++;
    }
    return d;
  }, 'headroom');
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
    if (!eq(seq[i].head, seq[i - 1].head)) headMoves++;
    if (i >= 2 && eq(seq[i].head, seq[i - 2].head) && !eq(seq[i].head, seq[i - 1].head)) headBounces++;
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
  const report = { base: BASE, at: new Date().toISOString(), q1_turn: [], q2_straight: null, q3_end: null, notes: [] };
  const errs = [];
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const ctx = await browser.newContext({ baseURL: BASE, viewport: { width: 1280, height: 800 } });
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
    console.log('[step] in game, Q1 begin');

    // ---- Q1：取 6 个有效转向延迟（死亡 → respawn 恢复）----
    let tries = 0;
    while (report.q1_turn.length < 6 && tries < 14) {
      tries++;
      if (!(await ensurePlaying(page, 'Q1'))) { report.notes.push(`Q1 try${tries}: cannot reach playing`); break; }
      const tr = await pickTurn(page);
      if (tr && tr.err) {
        console.log(`[Q1] try${tries}: pickTurn err=${JSON.stringify(tr)}`);
        if (tr.err === 'corner') { report.notes.push(`Q1 try${tries}: corner ${JSON.stringify(tr)}`); break; }
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

    report.allErrs = errs;
    fs.mkdirSync(path.dirname(OUT), { recursive: true });
    fs.writeFileSync(OUT, JSON.stringify(report, null, 2));
    console.log('Q1_turn=' + JSON.stringify(report.q1_turn));
    console.log('Q2_straight=' + JSON.stringify(report.q2_straight));
    console.log('Q3_end=' + JSON.stringify(report.q3_end));
    console.log('NOTES=' + JSON.stringify(report.notes));
    console.log('ALL_ERRS=' + JSON.stringify(errs));
    console.log('OUT=' + OUT);
    const fatal = report.q1_turn.length === 0 && !report.q2_straight && !report.q3_end;
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
