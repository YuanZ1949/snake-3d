#!/usr/bin/env node
// 批35：低多边形角色模型生成器（零依赖，手写 GLB 二进制）
// 产物：models/nailong.glb、models/furina.glb
// 结构：单 primitive + 顶点色（COLOR_0），每条蛇只 1 次 draw call
// 用法：node scripts/gen_models.js
'use strict';
const fs = require('fs');
const path = require('path');

// ---------- 基础几何体（返回 {pos, nor, idx}） ----------
function sphere(r, w, h) {
  const pos = [], nor = [], idx = [];
  for (let iy = 0; iy <= h; iy++) {
    const v = iy / h, phi = v * Math.PI;
    for (let ix = 0; ix <= w; ix++) {
      const u = ix / w, th = u * Math.PI * 2;
      const x = -Math.cos(th) * Math.sin(phi), y = Math.cos(phi), z = Math.sin(th) * Math.sin(phi);
      pos.push(x * r, y * r, z * r); nor.push(x, y, z);
    }
  }
  const row = w + 1;
  for (let iy = 0; iy < h; iy++)
    for (let ix = 0; ix < w; ix++) {
      const a = iy * row + ix, b = a + row;
      idx.push(a, b, a + 1, b, b + 1, a + 1);
    }
  return { pos, nor, idx };
}

// 圆柱/圆锥：rTop != rBottom 即锥台
function cyl(rTop, rBot, h, seg, cap) {
  const pos = [], nor = [], idx = [];
  const half = h / 2;
  const slope = (rBot - rTop) / h;
  for (let i = 0; i <= seg; i++) {
    const th = i / seg * Math.PI * 2, c = Math.cos(th), s = Math.sin(th);
    const nl = Math.hypot(1, slope), n = [c / nl, slope / nl, s / nl];
    pos.push(c * rTop, half, s * rTop); nor.push(n[0], n[1], n[2]);
    pos.push(c * rBot, -half, s * rBot); nor.push(n[0], n[1], n[2]);
  }
  for (let i = 0; i < seg; i++) {
    const a = i * 2, b = a + 2;
    idx.push(a, b, a + 1, b, b + 1, a + 1);
  }
  if (cap !== false) {
    // 顶盖
    let top = pos.length / 3;
    pos.push(0, half, 0); nor.push(0, 1, 0);
    for (let i = 0; i <= seg; i++) {
      const th = i / seg * Math.PI * 2;
      pos.push(Math.cos(th) * rTop, half, Math.sin(th) * rTop); nor.push(0, 1, 0);
    }
    for (let i = 0; i < seg; i++) idx.push(top, top + 1 + i, top + 2 + i);
    // 底盖
    let bot = pos.length / 3;
    pos.push(0, -half, 0); nor.push(0, -1, 0);
    for (let i = 0; i <= seg; i++) {
      const th = i / seg * Math.PI * 2;
      pos.push(Math.cos(th) * rBot, -half, Math.sin(th) * rBot); nor.push(0, -1, 0);
    }
    for (let i = 0; i < seg; i++) idx.push(bot, bot + 2 + i, bot + 1 + i);
  }
  return { pos, nor, idx };
}

function box(w, h, d) {
  const x = w / 2, y = h / 2, z = d / 2;
  const F = [
    [[-x, -y, z], [x, -y, z], [x, y, z], [-x, y, z], [0, 0, 1]],
    [[x, -y, -z], [-x, -y, -z], [-x, y, -z], [x, y, -z], [0, 0, -1]],
    [[x, -y, z], [x, -y, -z], [x, y, -z], [x, y, z], [1, 0, 0]],
    [[-x, -y, -z], [-x, -y, z], [-x, y, z], [-x, y, -z], [-1, 0, 0]],
    [[-x, y, z], [x, y, z], [x, y, -z], [-x, y, -z], [0, 1, 0]],
    [[-x, -y, -z], [x, -y, -z], [x, -y, z], [-x, -y, z], [0, -1, 0]],
  ];
  const pos = [], nor = [], idx = [];
  F.forEach((f, i) => {
    const b = i * 4;
    for (let k = 0; k < 4; k++) { pos.push(...f[k]); nor.push(...f[4]); }
    idx.push(b, b + 1, b + 2, b, b + 2, b + 3);
  });
  return { pos, nor, idx };
}

const PRIM = { sphere, cyl, box };

// ---------- 变换（s 缩放 -> r 欧拉弧度(XYZ) -> t 平移） ----------
function xform(g, t) {
  if (!t) return g;
  const s = t.s || [1, 1, 1], r = t.r || [0, 0, 0], p = t.t || [0, 0, 0];
  const [cx, sx] = [Math.cos(r[0]), Math.sin(r[0])];
  const [cy, sy] = [Math.cos(r[1]), Math.sin(r[1])];
  const [cz, sz] = [Math.cos(r[2]), Math.sin(r[2])];
  const rot = (vx, vy, vz) => {
    let y1 = vy * cx - vz * sx, z1 = vy * sx + vz * cx, x1 = vx;   // Rx
    let x2 = x1 * cy + z1 * sy, z2 = -x1 * sy + z1 * cy, y2 = y1;  // Ry
    return [x2 * cz - y2 * sz, x2 * sz + y2 * cz, z2];             // Rz
  };
  const o = { pos: [], nor: [], idx: g.idx.slice() };
  for (let i = 0; i < g.pos.length; i += 3) {
    const [x, y, z] = rot(g.pos[i] * s[0], g.pos[i + 1] * s[1], g.pos[i + 2] * s[2]);
    o.pos.push(x + p[0], y + p[1], z + p[2]);
    const [nx, ny, nz] = rot(g.nor[i], g.nor[i + 1], g.nor[i + 2]);
    const l = Math.hypot(nx, ny, nz) || 1;
    o.nor.push(nx / l, ny / l, nz / l);
  }
  return o;
}

// sRGB hex -> 线性 RGB（glTF 顶点色为线性空间）
function lin(hex) {
  const c = parseInt(hex.slice(1), 16);
  const f = v => { v /= 255; return v <= .04045 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); };
  return [f(c >> 16 & 255), f(c >> 8 & 255), f(c & 255)];
}

// ---------- 模型定义 ----------
// part: {g:'sphere'|'cyl'|'box', p:[参数], t:{t,r,s}, c:'#hex'}
const MODELS = {
  nailong: {
    name: '奶龙',
    parts: [
      // 身体 + 肚皮
      { g: 'sphere', p: [.26, 14, 10], t: { t: [0, -.07, 0], s: [1, .92, 1.08] }, c: '#FFD54A' },
      { g: 'sphere', p: [.19, 12, 9], t: { t: [0, -.09, .12], s: [1, .9, .8] }, c: '#FFF3C4' },
      // 头 + 吻 + 鼻
      { g: 'sphere', p: [.23, 14, 10], t: { t: [0, .17, 0] }, c: '#FFD54A' },
      { g: 'sphere', p: [.10, 10, 8], t: { t: [0, .11, .19], s: [1.15, .75, .9] }, c: '#FFF3C4' },
      { g: 'sphere', p: [.022, 6, 5], t: { t: [-.035, .13, .265] }, c: '#2b2118' },
      { g: 'sphere', p: [.022, 6, 5], t: { t: [.035, .13, .265] }, c: '#2b2118' },
      // 眼睛（大眼白 + 瞳）
      { g: 'sphere', p: [.055, 9, 7], t: { t: [-.105, .215, .165] }, c: '#ffffff' },
      { g: 'sphere', p: [.055, 9, 7], t: { t: [.105, .215, .165] }, c: '#ffffff' },
      { g: 'sphere', p: [.032, 8, 6], t: { t: [-.105, .215, .205] }, c: '#2b2118' },
      { g: 'sphere', p: [.032, 8, 6], t: { t: [.105, .215, .205] }, c: '#2b2118' },
      // 短角（橙）
      { g: 'cyl', p: [.012, .045, .13, 8], t: { t: [-.095, .345, -.01], r: [.22, 0, -.28] }, c: '#F76707' },
      { g: 'cyl', p: [.012, .045, .13, 8], t: { t: [.095, .345, -.01], r: [.22, 0, .28] }, c: '#F76707' },
      // 耳鳍
      { g: 'sphere', p: [.06, 8, 6], t: { t: [-.185, .19, -.05], s: [.5, 1, .7], r: [0, 0, .5] }, c: '#FFB84D' },
      { g: 'sphere', p: [.06, 8, 6], t: { t: [.185, .19, -.05], s: [.5, 1, .7], r: [0, 0, -.5] }, c: '#FFB84D' },
      // 小翅膀
      { g: 'box', p: [.16, .012, .11], t: { t: [-.245, .01, -.10], r: [.25, -.35, .38] }, c: '#FFB84D' },
      { g: 'box', p: [.16, .012, .11], t: { t: [.245, .01, -.10], r: [.25, .35, -.38] }, c: '#FFB84D' },
      // 尾 + 脚
      { g: 'cyl', p: [.015, .075, .22, 9], t: { t: [0, -.12, -.30], r: [-1.15, 0, 0] }, c: '#FFD54A' },
      { g: 'sphere', p: [.06, 8, 6], t: { t: [-.10, -.245, .06], s: [1, .55, 1.25] }, c: '#FFB84D' },
      { g: 'sphere', p: [.06, 8, 6], t: { t: [.10, -.245, .06], s: [1, .55, 1.25] }, c: '#FFB84D' },
    ],
  },
  furina: {
    name: '芙宁娜',
    parts: [
      // 裙摆（锥台）+ 白围裙
      { g: 'cyl', p: [.115, .215, .30, 16], t: { t: [0, -.16, 0] }, c: '#2B3A67' },
      { g: 'cyl', p: [.055, .12, .17, 12], t: { t: [0, -.17, .105], s: [1, 1, .42] }, c: '#F5F8FF' },
      // 上身白衣 + 蓝领结
      { g: 'cyl', p: [.10, .115, .15, 12], t: { t: [0, -.02, 0] }, c: '#F5F8FF' },
      { g: 'cyl', p: [.065, .065, .035, 12], t: { t: [0, .045, .085], r: [1.35, 0, 0] }, c: '#4AA3FF' },
      // 头 + 皮肤
      { g: 'sphere', p: [.185, 14, 11], t: { t: [0, .155, 0], s: [1, 1.02, .95] }, c: '#FFE0C8' },
      // 发（白）+ 双马尾（蓝）
      { g: 'sphere', p: [.215, 14, 10], t: { t: [0, .185, -.025], s: [1, .95, 1] }, c: '#EAF4FF' },
      { g: 'sphere', p: [.215, 14, 10], t: { t: [0, .135, .04], s: [.92, .70, .82] }, c: '#EAF4FF' },
      { g: 'sphere', p: [.075, 9, 7], t: { t: [-.225, .015, -.05], s: [.85, 2.5, .85] }, c: '#74C0FC' },
      { g: 'sphere', p: [.075, 9, 7], t: { t: [.225, .015, -.05], s: [.85, 2.5, .85] }, c: '#74C0FC' },
      // 刘海
      { g: 'sphere', p: [.19, 10, 7], t: { t: [0, .225, .10], s: [1, .42, .72] }, c: '#EAF4FF' },
      // 高礼帽：帽檐 + 帽筒 + 蓝缎带
      { g: 'cyl', p: [.20, .20, .016, 16], t: { t: [0, .335, -.01] }, c: '#1F2A47' },
      { g: 'cyl', p: [.105, .115, .15, 14], t: { t: [0, .415, -.01] }, c: '#2B3A67' },
      { g: 'cyl', p: [.118, .122, .035, 14], t: { t: [0, .365, -.01] }, c: '#4AA3FF' },
      // 眼睛（蓝）
      { g: 'sphere', p: [.045, 9, 7], t: { t: [-.085, .145, .145], s: [1, 1.15, .8] }, c: '#F5F8FF' },
      { g: 'sphere', p: [.045, 9, 7], t: { t: [.085, .145, .145], s: [1, 1.15, .8] }, c: '#F5F8FF' },
      { g: 'sphere', p: [.028, 8, 6], t: { t: [-.085, .145, .175] }, c: '#1C7ED6' },
      { g: 'sphere', p: [.028, 8, 6], t: { t: [.085, .145, .175] }, c: '#1C7ED6' },
      // 手臂
      { g: 'cyl', p: [.03, .04, .16, 8], t: { t: [-.135, -.045, .01], r: [0, 0, .55] }, c: '#F5F8FF' },
      { g: 'cyl', p: [.03, .04, .16, 8], t: { t: [.135, -.045, .01], r: [0, 0, -.55] }, c: '#F5F8FF' },
    ],
  },
};

// ---------- 合并 + 打包 GLB ----------
function buildGlb(spec) {
  const pos = [], nor = [], col = [], idx = [];
  let base = 0;
  for (const part of spec.parts) {
    const g = xform(PRIM[part.g](...part.p), part.t);
    const rgb = lin(part.c);
    for (let i = 0; i < g.pos.length; i += 3) {
      pos.push(g.pos[i], g.pos[i + 1], g.pos[i + 2]);
      nor.push(g.nor[i], g.nor[i + 1], g.nor[i + 2]);
      col.push(rgb[0], rgb[1], rgb[2]);
    }
    for (const v of g.idx) idx.push(v + base);
    base += g.pos.length / 3;
  }
  const count = pos.length / 3;

  // POSITION min/max（GLTFLoader 依赖它算包围盒）
  const mn = [Infinity, Infinity, Infinity], mx = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < pos.length; i += 3)
    for (let k = 0; k < 3; k++) { mn[k] = Math.min(mn[k], pos[i + k]); mx[k] = Math.max(mx[k], pos[i + k]); }

  // BIN 布局：POSITION(4B对齐) -> NORMAL -> COLOR_0 -> indices(2B对齐)
  const binParts = [];
  let off = 0;
  const push = (arr, ctor) => {
    const b = Buffer.alloc(arr.length * ctor.BYTES_PER_ELEMENT);
    arr.forEach((v, i) => ctor === Uint16Array ? b.writeUInt16LE(v, i * 2) : b.writeFloatLE(v, i * 4));
    const ent = { buf: b, off, len: b.length };
    binParts.push(ent);
    off += b.length;
    if (off % 2) { const pad = Buffer.alloc(1); binParts.push({ buf: pad, off, len: 1 }); off += 1; }  // uint16 对齐
    return ent;
  };
  const pv = push(pos, Float32Array), nv = push(nor, Float32Array), cv = push(col, Float32Array);
  // indices 需 2 字节对齐；Float32 之后天然 4 对齐，无需补
  const iv = push(idx, Uint16Array);
  while (off % 4) { binParts.push({ buf: Buffer.alloc(1), off, len: 1 }); off += 1; }

  const bin = Buffer.concat(binParts.map(p => p.buf), off);

  const bv = [
    { buffer: 0, byteOffset: pv.off, byteLength: pv.len, target: 34962 },
    { buffer: 0, byteOffset: nv.off, byteLength: nv.len, target: 34962 },
    { buffer: 0, byteOffset: cv.off, byteLength: cv.len, target: 34962 },
    { buffer: 0, byteOffset: iv.off, byteLength: iv.len, target: 34963 },
  ];
  const gltf = {
    asset: { version: '2.0', generator: 'snake3d-gen_models' },
    scene: 0,
    scenes: [{ nodes: [0] }],
    nodes: [{ mesh: 0, name: spec.name }],
    meshes: [{ name: spec.name, primitives: [{ attributes: { POSITION: 0, NORMAL: 1, COLOR_0: 2 }, indices: 3, material: 0 }] }],
    materials: [{ name: spec.name + 'Mat', pbrMetallicRoughness: { baseColorFactor: [1, 1, 1, 1], metallicFactor: 0, roughnessFactor: .85 }, doubleSided: false }],
    accessors: [
      { bufferView: 0, componentType: 5126, count, type: 'VEC3', min: mn, max: mx },
      { bufferView: 1, componentType: 5126, count, type: 'VEC3' },
      { bufferView: 2, componentType: 5126, count, type: 'VEC3' },
      { bufferView: 3, componentType: 5123, count: idx.length, type: 'SCALAR' },
    ],
    bufferViews: bv,
    buffers: [{ byteLength: bin.length }],
  };

  let json = Buffer.from(JSON.stringify(gltf), 'utf8');
  if (json.length % 4) json = Buffer.concat([json, Buffer.alloc(4 - json.length % 4, 0x20)]);
  const binPad = bin.length % 4 ? Buffer.alloc(4 - bin.length % 4) : Buffer.alloc(0);
  const binChunk = Buffer.concat([bin, binPad]);

  const head = Buffer.alloc(12);
  head.write('glTF', 0, 'latin1');
  head.writeUInt32LE(2, 4);
  head.writeUInt32LE(12 + 8 + json.length + 8 + binChunk.length, 8);

  const jh = Buffer.alloc(8); jh.writeUInt32LE(json.length, 0); jh.writeUInt32LE(0x4E4F534A, 4);
  const bh = Buffer.alloc(8); bh.writeUInt32LE(binChunk.length, 0); bh.writeUInt32LE(0x004E4942, 4);
  return Buffer.concat([head, jh, json, bh, binChunk]);
}

function main() {
  const outDir = path.join(__dirname, '..', 'models');
  fs.mkdirSync(outDir, { recursive: true });
  for (const [key, spec] of Object.entries(MODELS)) {
    const buf = buildGlb(spec);
    const f = path.join(outDir, key + '.glb');
    fs.writeFileSync(f, buf);
    console.log('生成 ' + key + '.glb (' + buf.length + ' B) — ' + spec.name);
  }
}

module.exports = { MODELS, buildGlb, sphere, cyl, box, xform, lin };
if (require.main === module) main();
