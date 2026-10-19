#!/usr/bin/env node
// 批35：把 three r160 的 ESM 版 GLTFLoader + BufferGeometryUtils 改写成挂到 THREE 全局的传统脚本
// 产物：gltf-loader.js（仓库根，由 index.html 用 <script> 引入）
// 用法：node scripts/build_gltf_loader.js   （需联网；产物已提交，日常无需重跑）
'use strict';
const fs = require('fs');
const path = require('path');

const VER = '0.160.0';
const CDN = `https://cdn.jsdelivr.net/npm/three@${VER}/examples/jsm/`;

async function get(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(url + ' -> ' + r.status);
  return await r.text();
}

// ESM import/export -> 全局 THREE 解构
function stripEsm(src, extraGlobal) {
  let s = src;
  // import { a, b } from 'three';
  s = s.replace(/import\s*\{([^}]*)\}\s*from\s*'three';?/g, (_, names) =>
    `const {${names.replace(/\s+/g, ' ').trim()}} = THREE;`);
  // import { x } from '../utils/BufferGeometryUtils.js';
  s = s.replace(/import\s*\{([^}]*)\}\s*from\s*'\.\.\/utils\/BufferGeometryUtils\.js';?/g, (_, names) =>
    `const {${names.replace(/\s+/g, ' ').trim()}} = THREE.BufferGeometryUtils;`);
  // export { X } / export { X as Y }
  s = s.replace(/^export\s*\{[^}]*\};?\s*$/gm, '');
  s = s.replace(/^export\s+(?=(class|function|const|let|var)\s)/gm, '');
  if (extraGlobal) s = extraGlobal + '\n' + s;
  return s;
}

(async () => {
  const bu = await get(CDN + 'utils/BufferGeometryUtils.js');
  const gl = await get(CDN + 'loaders/GLTFLoader.js');

  // 校验：改写后不该再残留 import/export
  const buOut = stripEsm(bu, '');
  const glOut = stripEsm(gl, '');
  for (const [n, out] of [['BufferGeometryUtils', buOut], ['GLTFLoader', glOut]]) {
    const left = out.match(/^\s*(import|export)\s/m);
    if (left) throw new Error(n + ' 改写后仍残留 ESM 语法');
  }

  const banner =
`/* 批35 — three r${VER} GLTFLoader（UMD 化产物，勿手改）
 * 由 scripts/build_gltf_loader.js 从 three@${VER}/examples/jsm 机械改写 import -> THREE 全局解构
 * 挂载：THREE.BufferGeometryUtils、THREE.GLTFLoader
 */
`;
  const out =
    banner +
    '// ---- BufferGeometryUtils ----\nTHREE.BufferGeometryUtils = (function () {\n"use strict";\n' +
    buOut.replace(/^import[^;]*;\s*$/gm, '') +
    '\nreturn { ' + [...bu.matchAll(/export\s*\{([^}]*)\}/g)].flatMap(m => m[1].split(',').map(x => {
        const p = x.trim().split(/\s+as\s+/); return (p[1] || p[0]).trim() + ': ' + p[0].trim();
      })).join(', ') + ' };\n})();\n\n' +
    '// ---- GLTFLoader ----\nTHREE.GLTFLoader = (function () {\n"use strict";\n' +
    glOut + '\nreturn GLTFLoader;\n})();\n';

  const dst = path.join(__dirname, '..', 'gltf-loader.js');
  fs.writeFileSync(dst, out);
  console.log('写出 ' + dst + ' (' + out.length + ' B)');
  // 快速语法自检
  new Function('THREE', out);
  console.log('语法自检通过');
})().catch(e => { console.error('[FAIL] ' + e.message); process.exit(1); });
