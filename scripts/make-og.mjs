#!/usr/bin/env node
/** Генерирует assets/og-image.png (1200×630) через headless Chrome/Edge:  node scripts/make-og.mjs */
import { writeFileSync, mkdtempSync, existsSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import * as svg from './lib/bikes-svg.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const browsers = [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  '/usr/bin/google-chrome', '/usr/bin/chromium', '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
];
const exe = browsers.find(existsSync);
if (!exe) throw new Error('Нужен Chrome или Edge');

const html = `<!doctype html><meta charset="utf-8"><style>
*{box-sizing:border-box;margin:0}body{width:1200px;height:630px;overflow:hidden;background:radial-gradient(60% 90% at 78% 40%,rgba(225,6,0,.55),transparent 70%),#0b0b0c;color:#fff;font-family:Bahnschrift,"Arial Narrow",Impact,sans-serif;position:relative}
.t{position:absolute;left:70px;top:150px;width:560px}.b{font-size:34px;letter-spacing:.28em;color:#ff3b30;font-weight:700}
h1{font-size:128px;line-height:.95;text-transform:uppercase;margin:14px 0 18px;font-stretch:80%}h1 b{color:#ff3b30}
p{font-family:"Segoe UI",Arial,sans-serif;font-size:32px;color:#d6d6da}
svg{position:absolute;right:-70px;top:150px;width:760px;color:#fff;--bike-fill:#1a1a1f}
.bk-d{fill:none;stroke:currentColor;stroke-width:3.4;stroke-linecap:round;stroke-linejoin:round}.bk-body{fill:var(--bike-fill)}.bk-tyre{stroke-width:10}.bk-thin{stroke-width:2;opacity:.7}.bk-acc{fill:#e10600;stroke:none}.bk-accs{stroke:#e10600;stroke-width:5}
.bar{position:absolute;left:0;right:0;bottom:0;height:14px;background:linear-gradient(90deg,#e10600,transparent 75%)}
</style><div class="t"><div class="b">МОТОСАЛОН · НИЖНЕКАМСК</div><h1>IV<b>&amp;</b>AX<br>MOTO</h1><p>Купить мотоцикл: тест-драйв, рассрочка, trade-in</p></div>${svg.inline('sport', { cls: 'bike' })}<div class="bar"></div>`;
const dir = mkdtempSync(join(tmpdir(), 'og-'));
const src = join(dir, 'og.html');
writeFileSync(src, html);
execFileSync(exe, ['--headless=new', '--disable-gpu', '--hide-scrollbars', '--window-size=1200,630', `--screenshot=${join(ROOT, 'assets/og-image.png')}`, pathToFileURL(src).href], { stdio: 'inherit' });
console.log('assets/og-image.png создан');
