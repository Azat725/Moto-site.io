#!/usr/bin/env node
/** Проверка сборки: битые внутренние ссылки/ресурсы, title/description/h1/canonical на каждой странице, валидность JSON-LD. */
import { readFileSync, readdirSync, existsSync, statSync } from 'node:fs';
import { join, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const files = [...readdirSync(ROOT).filter((f) => f.endsWith('.html')), ...readdirSync(join(ROOT, 'bikes')).map((f) => 'bikes/' + f)];
let bad = 0;
const fail = (m) => { bad++; console.log('✗', m); };
const ids = new Set();
for (const f of files) {
  const html = readFileSync(join(ROOT, f), 'utf8');
  const h1 = (html.match(/<h1[\s>]/g) || []).length;
  if (h1 !== 1) fail(`${f}: h1 = ${h1}`);
  if (!/<title>[^<]{10,}<\/title>/.test(html)) fail(`${f}: нет title`);
  if (!/<meta name="description" content="[^"]{50,}"/.test(html)) fail(`${f}: description короче 50 символов или отсутствует`);
  if (!/<link rel="canonical"/.test(html)) fail(`${f}: нет canonical`);
  for (const m of html.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g)) { try { JSON.parse(m[1]); } catch { fail(`${f}: битый JSON-LD`); } }
  const pageIds = [...html.matchAll(/\sid="([^"]+)"/g)].map((m) => m[1]);
  const dup = pageIds.filter((x, i) => pageIds.indexOf(x) !== i);
  if (dup.length) fail(`${f}: повторяются id: ${[...new Set(dup)].join(', ')}`);
  for (const m of html.matchAll(/\s(?:href|src)="([^"#?][^"]*?)(?:[?#][^"]*)?"/g)) {
    const u = m[1];
    if (/^(https?:|mailto:|tel:|data:|\/\/|javascript:)/.test(u)) continue;
    const p = u.startsWith('/') ? join(ROOT, u) : resolve(join(ROOT, dirname(f)), u);
    if (f === '404.html' && u.startsWith('/')) { if (!existsSync(p)) fail(`${f}: нет файла ${u}`); continue; }
    if (!existsSync(p) || statSync(p).isDirectory() && !existsSync(join(p, 'index.html'))) fail(`${f}: битая ссылка ${u}`);
  }
}
console.log(bad ? `\nПроблем: ${bad}` : `OK: ${files.length} страниц проверено, проблем нет`);
process.exit(bad ? 1 : 0);
