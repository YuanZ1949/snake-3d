const fs = require('fs');
const html = fs.readFileSync(process.argv[2], 'utf8');
// 1) extract script blocks (skip src=) and node --check each via spawnSync
const { spawnSync } = require('child_process');
const os = require('os');
const path = require('path');
const blocks = [...html.matchAll(/<script(?![^>]*src=)[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);
let jsOk = 0;
const tmp = path.join(os.tmpdir(), 'static_check.js');
for (const b of blocks) {
  fs.writeFileSync(tmp, b, 'utf8');
  const r = spawnSync(process.execPath, ['--check', tmp], { encoding: 'utf8' });
  if (r.status !== 0) { console.error('SYNTAX FAIL:', r.stderr.slice(0, 500)); process.exit(1); }
  jsOk += (b.match(/\{/g) || []).length;
}
// 2) duplicate ids
const ids = [...html.matchAll(/\sid="([^"]+)"/g)].map(m => m[1]);
const dup = ids.filter((v, i) => ids.indexOf(v) !== i);
// 3) brace balance for css + js counts (rough structural check)
const css = [...html.matchAll(/<style[^>]*>([\s\S]*?)<\/style>/g)].map(m => m[1]).join('');
const cOpen = (css.match(/\{/g) || []).length, cClose = (css.match(/\}/g) || []).length;
const jClose = blocks.reduce((n, b) => n + (b.match(/\}/g) || []).length, 0);
const dOpen = (html.match(/<div/g) || []).length, dClose = (html.match(/<\/div>/g) || []).length;
console.log(`ids=${ids.length} dup=${dup.length}${dup.length ? ' ' + dup.join(',') : ''} div=${dOpen}/${dClose} css=${cOpen}/${cClose} js=${jsOk}/${jClose}`);
if (dup.length || cOpen !== cClose || jsOk !== jClose || dOpen !== dClose) { console.log('STATIC CHECK FAILED'); process.exit(1); }
// 4) 双端 PROTO_VER 一致性（oracle F5-③：单边 bump → 旧标签 reload 死循环）
const py = fs.readFileSync(path.join(__dirname, '..', 'serve.py'), 'utf8');
const sv = /PROTO_VER\s*=\s*(\d+)/.exec(py);
const cl = /const\s+PROTO_VER\s*=\s*(\d+)/.exec(html);
if (!sv || !cl || sv[1] !== cl[1]) {
  console.log(`PROTO_VER MISMATCH: serve.py=${sv ? sv[1] : '?'} index.html=${cl ? cl[1] : '?'}`);
  process.exit(1);
}
console.log('ALL STATIC CHECKS PASSED');
