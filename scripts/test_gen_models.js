#!/usr/bin/env node
// 批35 生成器单测：校验 gen_models.js 产出的 GLB 二进制结构合法
// 用法：node scripts/test_gen_models.js
'use strict';
const fs = require('fs');
const path = require('path');
const { MODELS, buildGlb } = require('./gen_models.js');

let fails = 0;
function ok(name, cond, extra) {
  if (cond) console.log('  [PASS] ' + name);
  else { console.log('  [FAIL] ' + name + (extra ? ' | ' + extra : '')); fails++; }
}
function readChunks(buf) {
  // GLB: 12B header, then N * (8B chunkHeader + data)
  const chunks = [];
  let off = 12;
  while (off < buf.length) {
    const len = buf.readUInt32LE(off);
    const type = buf.readUInt32LE(off + 4);
    const start = off + 8;
    if (start + len > buf.length) throw new Error('chunk 溢出: off=' + off + ' len=' + len);
    chunks.push({ type, len, data: buf.subarray(start, start + len), off });
    off = start + len;
  }
  return chunks;
}

for (const [name, spec] of Object.entries(MODELS)) {
  console.log('模型 ' + name);
  const buf = buildGlb(spec);

  ok('magic == glTF', buf.toString('latin1', 0, 4) === 'glTF');
  ok('version == 2', buf.readUInt32LE(4) === 2);
  ok('header.length == 文件字节数', buf.readUInt32LE(8) === buf.length,
     buf.readUInt32LE(8) + ' vs ' + buf.length);

  const chunks = readChunks(buf);
  ok('chunk 数 == 2 (JSON + BIN)', chunks.length === 2, String(chunks.length));
  ok('JSON chunk type 0x4E4F534A', chunks[0] && chunks[0].type === 0x4E4F534A);
  ok('BIN chunk type 0x004E4942', chunks[1] && chunks[1].type === 0x004E4942);
  ok('chunk 长度 4 字节对齐', chunks.every(c => c.len % 4 === 0));

  let j;
  try { j = JSON.parse(chunks[0].data.toString('utf8')); } catch (e) { j = null; }
  ok('JSON 可解析', !!j);
  if (!j) continue;

  ok('asset.version == 2.0', j.asset && j.asset.version === '2.0');
  ok('buffers[0].byteLength == BIN chunk 实长',
     j.buffers[0].byteLength === chunks[1].len,
     j.buffers[0].byteLength + ' vs ' + chunks[1].len);

  // accessor -> bufferView -> bin 范围不越界
  let inRange = true, badAcc = '';
  for (const a of j.accessors) {
    const bv = j.bufferViews[a.bufferView];
    const need = a.count * ({ SCALAR: 1, VEC2: 2, VEC3: 3 }[a.type]) * ({ 5126: 4, 5123: 2 }[a.componentType]);
    if (bv.byteOffset + (a.byteOffset || 0) + need > chunks[1].len) { inRange = false; badAcc = a.type; }
  }
  ok('accessor 不越出 BIN chunk', inRange, badAcc);

  // 逐 mesh：POSITION/NORMAL/indices 三件套齐全，索引不越顶点数
  let triCount = 0, vertsCount = 0, trioOk = true, idxOk = true;
  for (const m of j.meshes) {
    const p = m.primitives[0];
    if (p.attributes.POSITION === undefined || p.attributes.NORMAL === undefined || p.indices === undefined) trioOk = false;
    const posAcc = j.accessors[p.attributes.POSITION];
    const idxAcc = j.accessors[p.indices];
    vertsCount += posAcc.count;
    triCount += idxAcc.count / 3;
    const bv = j.bufferViews[idxAcc.bufferView];
    const bin = chunks[1].data;
    const ioff = bv.byteOffset + (idxAcc.byteOffset || 0);
    for (let i = 0; i < idxAcc.count; i++) {
      const v = bin.readUInt16LE(ioff + i * 2);
      if (v >= posAcc.count) { idxOk = false; break; }
    }
  }
  ok('每个 primitive 有 POSITION/NORMAL/indices', trioOk);
  ok('indices 均 < 顶点数', idxOk);
  console.log('    规模：顶点 ' + vertsCount + ' / 三角面 ' + triCount);
  ok('面数在低模区间 (<8000)', triCount > 0 && triCount < 8000, String(triCount));

  // POSITION min/max 与实际数据一致（GLTFLoader 依赖它做包围盒）
  const p0 = j.accessors[j.meshes[0].primitives[0].attributes.POSITION];
  const bin = chunks[1].data;
  const bv0 = j.bufferViews[p0.bufferView];
  let minOK = true;
  const p0off = bv0.byteOffset + (p0.byteOffset || 0);
  for (let i = 0; i < p0.count; i++) {
    const x = bin.readFloatLE(p0off + i * 12);
    if (x < p0.min[0] - 1e-6 || x > p0.max[0] + 1e-6) { minOK = false; break; }
  }
  ok('POSITION min/max 覆盖实际数据', minOK);
}

const outDir = path.join(__dirname, '..', 'models');
for (const name of Object.keys(MODELS)) {
  const f = path.join(outDir, name + '.glb');
  ok(name + '.glb 已落盘', fs.existsSync(f));
}

console.log(fails === 0 ? '\nGENERATOR CHECKS PASSED' : '\nGENERATOR CHECKS FAILED (' + fails + ')');
process.exit(fails === 0 ? 0 : 1);
