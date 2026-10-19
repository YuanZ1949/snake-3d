#!/usr/bin/env node
/**
 * scripts/prod_verify35.js —— 批35 生产验收的**可复现**脚本
 *
 * 背景：批35 的一次性取证脚本（_tmp_*.js）已按清理要求删除，验收 4 中「prod_verify 无新增
 * console 错误」当时没有可执行件。本脚本把那套流程固化下来，随时可重跑。
 *
 * 做的事（对每个皮肤 id 16 奶龙 / 17 芙宁娜）：
 *   1. 打开生产站点，等前端探针就绪
 *   2. 单人练习入局（#btnSolo → 等 #startScreen hidden）
 *   3. __applySkinDbg(id) → 等 __modelDbg().mine.node === true（GLB 挂载成功）
 *   4. __modelBoxDbg() 取模型屏幕盒子 → 中心 ±170/±190 算 CLIP（夹在视口内）
 *   5. 截图 ON（真实比例，不传 zoom ⇒ 只开模型）→ __modelShowDbg(false) 截图 OFF → 还原
 *   6. 全程收集 pageerror + console.error
 *
 * 口径（与 .tamako/evidence.md 一致）：
 *   - 不挂机（#pauseMask 保持 display:none）—— 居中胶囊会盖进裁剪区
 *   - 不传 zoom = 真实比例；zoom 只放大模型节点，相机从不改动
 *   - 登录是可选的：16/17 属 FREE_SKINS，探针是纯客户端路径
 *
 * 用法：
 *   node scripts/prod_verify35.js                       # 默认打生产 8090，图落 test-results/
 *   node scripts/prod_verify35.js --login               # 先注册/登录随机账号（走账号链路）
 *   node scripts/prod_verify35.js --base http://127.0.0.1:8123 --out docs/evidence/batch35
 *
 * 退出码：0 = pass，1 = 验收不通过，2 = 环境/执行致命错误
 */

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const SKINS = [
  { id: 16, name: 'nailong', label: '奶龙' },
  { id: 17, name: 'furina', label: '芙宁娜' },
];
const CLIP_HALF_W = 170;   // CSS px，与既有取证一致
const CLIP_HALF_H = 190;

function parseArgs(argv) {
  const a = { base: 'http://193.112.172.83:8090', out: 'test-results', login: false, timeout: 40000 };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    if (k === '--base') a.base = argv[++i];
    else if (k === '--out') a.out = argv[++i];
    else if (k === '--login') a.login = true;
    else if (k === '--timeout') a.timeout = parseInt(argv[++i], 10) || a.timeout;
    else if (k === '--help' || k === '-h') { a.help = true; }
    else { console.error(`unknown arg: ${k}`); a.bad = true; }
  }
  a.base = a.base.replace(/\/+$/, '');
  return a;
}

const log = (...xs) => console.log(...xs);
const say = (tag, obj) => log(`${tag}=${typeof obj === 'string' ? obj : JSON.stringify(obj)}`);

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) { log('see header comment'); return 0; }
  if (args.bad) return 2;

  const outDir = path.resolve(process.cwd(), args.out);
  fs.mkdirSync(outDir, { recursive: true });

  log(`PROD_VERIFY35 base=${args.base} out=${args.out} login=${args.login}`);
  say('ARGS', { base: args.base, out: args.out, login: args.login, timeout: args.timeout });

  const errs = [];          // pageerror + console.error
  const browser = await chromium.launch({ headless: true });
  const results = [];
  let fatal = null;

  try {
    const ctx = await browser.newContext({
      baseURL: args.base,
      viewport: { width: 1280, height: 800 },
      deviceScaleFactor: 2,      // 截图为 2×，clip 仍按 CSS px 计
    });
    const page = await ctx.newPage();
    page.on('pageerror', (e) => errs.push(`pageerror: ${e.message}`));
    page.on('console', (m) => { if (m.type() === 'error') errs.push(`console.error: ${m.text()}`); });

    // ---- 1. 打开站点，等探针就绪 ----
    await page.goto(args.base + '/', { waitUntil: 'domcontentloaded', timeout: args.timeout });
    await page.waitForFunction(
      () => typeof window.__modelDbg === 'function' && typeof window.__applySkinDbg === 'function',
      null, { timeout: args.timeout },
    );
    log('STEP ok: probes ready (__modelDbg/__applySkinDbg)');

    // ---- 1b. 可选登录（默认跳过：16/17 恒免费，探针是客户端路径）----
    if (args.login) {
      const { ensureLogin, uniqName } = require('../e2e/_helpers.js');
      await ensureLogin(page, uniqName('fz'), '351234');
      log('STEP ok: logged in (random fz account)');
    }

    // ---- 2. 单人练习入局 ----
    await page.click('#btnSolo');
    await page.waitForFunction(
      () => { const s = document.getElementById('startScreen'); return !!s && s.classList.contains('hidden'); },
      null, { timeout: args.timeout },
    );
    log('STEP ok: in game (#startScreen hidden)');

    const pauseMask = await page.evaluate(() => {
      const el = document.getElementById('pauseMask');
      if (!el) return { exists: false };
      const cs = getComputedStyle(el);
      const r = el.getBoundingClientRect();
      return { exists: true, display: cs.display, rect: { x: r.x, y: r.y, w: r.width, h: r.height } };
    });
    say('PAUSE_MASK', pauseMask);

    // ---- 3~5. 每个皮肤：挂载 → 盒子 → ON/OFF 截图 ----
    for (const sk of SKINS) {
      const rec = { id: sk.id, name: sk.name, label: sk.label };

      await page.evaluate((id) => window.__applySkinDbg(id), sk.id);
      await page.waitForFunction(
        () => { const d = window.__modelDbg(); return !!(d && d.mine && d.mine.node === true); },
        null, { timeout: args.timeout },
      );
      const onState = await page.evaluate(() => {
        const d = window.__modelDbg();
        return JSON.stringify({ mine: d.mine });
      });
      rec.afterApply = JSON.parse(onState);
      log(`STEP ok: skin ${sk.id} ${sk.name} mounted (mine.node=true)`);

      const box = await page.evaluate(() => window.__modelBoxDbg());
      rec.box = box;
      if (!box || typeof box.x !== 'number' || !box.w) {
        rec.error = 'model box unavailable (is the model on myEnt.head?)';
        results.push(rec);
        continue;
      }
      const cx = box.x + box.w / 2, cy = box.y + box.h / 2;
      const clip = {
        x: Math.max(0, Math.round(cx - CLIP_HALF_W)),
        y: Math.max(0, Math.round(cy - CLIP_HALF_H)),
        width: Math.min(1280, Math.round(cx + CLIP_HALF_W)) - Math.max(0, Math.round(cx - CLIP_HALF_W)),
        height: Math.min(800, Math.round(cy + CLIP_HALF_H)) - Math.max(0, Math.round(cy - CLIP_HALF_H)),
      };
      rec.clip = clip;

      const onFile = path.join(outDir, `prod35_${sk.name}_on.png`);
      await page.screenshot({ path: onFile, clip });
      rec.onPng = path.relative(process.cwd(), onFile);

      // OFF：__modelShowDbg(false) 关模型、开回退球（真实比例，不传 zoom）
      rec.showOff = await page.evaluate(() => window.__modelShowDbg(false));
      const offFile = path.join(outDir, `prod35_${sk.name}_off.png`);
      await page.screenshot({ path: offFile, clip });
      rec.offPng = path.relative(process.cwd(), offFile);

      // 还原
      rec.showOn = await page.evaluate(() => window.__modelShowDbg(true));
      rec.ok = rec.afterApply.mine.node === true
        && rec.showOff && rec.showOff.node === false && rec.showOff.skull === true;
      results.push(rec);
      log(`STEP ${rec.ok ? 'ok' : 'FAIL'}: skin ${sk.id} ON/OFF captured`);
    }
  } catch (e) {
    fatal = e && e.message ? e.message : String(e);
  } finally {
    await browser.close().catch(() => {});
  }

  // ---- 判定 ----
  if (fatal) say('FATAL', fatal);
  say('ALL_ERRS', errs);
  const perSkin = results.map((r) => ({
    id: r.id, name: r.name, ok: !!r.ok, node: r.afterApply && r.afterApply.mine && r.afterApply.mine.node,
    off: r.showOff || null, on: r.onPng || null, offPng: r.offPng || null, error: r.error || null,
  }));
  say('PER_SKIN', perSkin);

  const mounted = perSkin.filter((p) => p.ok).length === SKINS.length;
  const pass = !fatal && mounted && errs.length === 0;
  say('VERDICT', pass ? 'pass' : 'fail');
  log(`--- prod_verify35: ${pass ? 'PASS' : 'FAIL'} (mounted ${mounted}/${SKINS.length}, errs ${errs.length}) ---`);
  return pass ? 0 : 1;
}

main()
  .then((code) => process.exit(code))
  .catch((e) => { console.error('UNCAUGHT', e); process.exit(2); });
