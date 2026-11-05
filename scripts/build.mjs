#!/usr/bin/env node
/**
 * Генератор статического сайта IV&AX MOTO.
 *   node scripts/build.mjs
 *
 * Читает:  site.config.json, src/data/motorcycles.json, src/pages/*.html, src/templates/bike.html, src/partials/*.html
 * Пишет:   *.html в корень, bikes/<slug>.html, sitemap.xml, robots.txt, site.webmanifest
 * Страницы и сгенерированные файлы коммитим — хостингу сборка не нужна.
 */
import { readFileSync, writeFileSync, mkdirSync, readdirSync, existsSync } from 'node:fs';
import { dirname, join, basename } from 'node:path';
import { fileURLToPath } from 'node:url';
import * as svg from './lib/bikes-svg.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => readFileSync(join(ROOT, p), 'utf8');
const write = (p, s) => {
  mkdirSync(dirname(join(ROOT, p)), { recursive: true });
  writeFileSync(join(ROOT, p), s.replace(/\r\n/g, '\n'), 'utf8');
};

const site = JSON.parse(read('site.config.json'));
const bikes = JSON.parse(read('src/data/motorcycles.json'));

const NBSP = '\u00a0';
const TYPE_LABEL = { sport: 'Спорт', naked: 'Нейкед', cruiser: 'Круизер' };
const COND_LABEL = { new: 'Новый', used: 'С пробегом' };

const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const money = (n) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, NBSP) + NBSP + '₽';
const num = (n) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);

// ---------- Данные ----------
for (const b of bikes) {
  b.fullName = b.brand === 'Demo' ? b.model : `${b.brand} ${b.model}`;
  b.priceText = money(b.price);
  b.typeLabel = TYPE_LABEL[b.type] ?? b.type;
  b.condLabel = COND_LABEL[b.condition] ?? b.condition;
  b.mileageText = b.mileage > 0 ? `${num(b.mileage)}${NBSP}км` : 'Новый';
  b.url = `bikes/${b.slug}.html`;
}

const FAQ = [
  ['Можно ли купить мотоцикл в рассрочку или кредит?', 'Да, оформление возможно через банки-партнёры. Ставка и условия зависят от банка и определяются индивидуально. Предварительный платёж можно прикинуть в калькуляторе на странице «Рассрочка».'],
  ['Как записаться на тест-драйв?', 'Оставьте заявку на сайте или позвоните нам — менеджер согласует время и расскажет, какие документы и экипировка понадобятся. Условия тест-драйва уточняйте у менеджера.'],
  ['Принимаете ли вы мотоцикл в trade-in?', 'Да. Стоимость определяется после осмотра и диагностики вашего мотоцикла. Предварительную оценку можно получить по фото.'],
  ['Какая категория прав нужна для мотоцикла?', 'Для мотоциклов объёмом более 125 см³ или мощностью более 11 кВт нужна категория «A». Для более лёгких моделей — достаточно категории «A1». Точные требования смотрите в действующем законодательстве.'],
  ['Есть ли гарантия на мотоциклы?', 'Условия гарантии на новые и подержанные мотоциклы прописываются в договоре купли-продажи. Менеджер расскажет подробности по конкретной модели.'],
  ['Вы помогаете с оформлением и регистрацией?', 'Да, подскажем по документам, необходимым для постановки на учёт и страхования. Регистрация в ГИБДД и ОСАГО оформляются владельцем в установленном порядке.'],
];

// ---------- Иконки ----------
const ICONS = {
  pin: '<path d="M12 21s7-6.2 7-12a7 7 0 1 0-14 0c0 5.8 7 12 7 12z"/><circle cx="12" cy="9" r="2.6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  phone: '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  shield: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
  key: '<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M16 7l3 3M14 9l2 2"/>',
  wallet: '<rect x="3" y="6" width="18" height="13" rx="2"/><path d="M3 10h18M16 14.5h2"/>',
  repeat: '<path d="M17 2l4 4-4 4M3 11V9a3 3 0 0 1 3-3h15M7 22l-4-4 4-4M21 13v2a3 3 0 0 1-3 3H3"/>',
  flag: '<path d="M5 21V4M5 4h11l-2 4 2 4H5"/>',
  tools: '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.8 2.8-2.5-.6-.6-2.5z"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  gauge: '<path d="M4 17a8 8 0 1 1 16 0"/><path d="M12 17l4-6"/>',
  vk: '<path d="M3 7h3c.3 4 2 6 3 6V7h3v3.5c1-.1 2.200-1.600 3-3.500h3c-.4 1.700-1.600 3.200-2.700 4 1.300.7 2.500 2 3.200 4h-3.200c-.6-1.400-1.600-2.200-3.300-2.500V15C7 15 3.300 12 3 7z"/>',
  telegram: '<path d="M21 4L3 11l5 2 2 6 3-4 5 4z"/><path d="M8 13l9-6"/>',
  youtube: '<rect x="2.500" y="5.500" width="19" height="13" rx="4"/><path d="M10 9.500v5l4.500-2.500z"/>',
  whatsapp: '<path d="M3 21l1.500-5A8.500 8.500 0 1 1 8 19.500z"/><path d="M9 9c0 3 3 6 6 6l1-2-2-1-1 .8c-.8-.4-1.600-1.200-2-2l.8-1-1-2z"/>',
};
const icon = (name, cls = '') => `<svg class="ico ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${ICONS[name] ?? ''}</svg>`;

const LOGO_MARK = '<svg class="logo__mark" viewBox="0 0 48 48" aria-hidden="true" focusable="false"><rect width="48" height="48" rx="12" fill="#e10600"/><path d="M10 12h9l5 15 5-15h9L28 36h-8z" fill="#fff"/><path d="M8 42h32" stroke="#0b0b0c" stroke-width="3" stroke-linecap="round"/></svg>';

// ---------- Карточки ----------
function card(b, R) {
  const badges = (b.badges ?? []).slice(0, 2).map((t, i) => `<span class="badge${i ? ' badge--white' : ''}">${esc(t)}</span>`).join('');
  return `<div class="bike-item" data-reveal data-type="${b.type}" data-condition="${b.condition}" data-price="${b.price}" data-year="${b.year}" data-cc="${b.cc}" data-name="${esc((b.brand + ' ' + b.model + ' ' + b.year).toLowerCase())}">
  <article class="bike-card tilt">
    <div class="bike-card__art">
      <div class="bike-card__badges">${badges}</div>
      <span class="bike-card__year" aria-hidden="true">${b.year}</span>
      ${svg.use(b.type, { label: `${b.fullName} ${b.year} — иллюстрация` })}
    </div>
    <div class="bike-card__body">
      <div>
        <p class="bike-card__brand">${esc(b.brand === 'Demo' ? b.typeLabel : b.brand)}</p>
        <h3 class="bike-card__title"><a href="${R}${b.url}">${esc(b.model)} <span class="accent">${b.year}</span></a></h3>
      </div>
      <ul class="specs">
        <li><span>Объём</span><b>${b.cc}${NBSP}см³</b></li>
        <li><span>Мощность</span><b>${b.hp}${NBSP}л.с.</b></li>
        <li><span>Пробег</span><b>${b.mileageText}</b></li>
        <li><span>КПП</span><b>${esc(b.gearbox.replace('ступеней', 'ст.').replace('ступени', 'ст.'))}</b></li>
      </ul>
      <div class="bike-card__foot">
        <div class="price"><small>Цена</small><b>${b.priceText}</b></div>
        <span class="more-link">Подробнее ${icon('arrow')}</span>
      </div>
    </div>
  </article>
</div>`;
}

// ---------- Формы ----------
function leadForm(kind, ctx) {
  const R = ctx.R;
  const cfg = {
    callback: { btn: 'Перезвоните мне', subject: 'Обратный звонок', model: false, comment: false },
    testdrive: { btn: 'Записаться на тест-драйв', subject: 'Тест-драйв', model: true, comment: true },
    credit: { btn: 'Отправить заявку', subject: 'Рассрочка / кредит', model: true, comment: true },
    bike: { btn: 'Узнать цену и наличие', subject: `Запрос по модели: ${ctx.bike?.fullName ?? ''} ${ctx.bike?.year ?? ''}`, model: false, comment: true },
    contact: { btn: 'Отправить сообщение', subject: 'Сообщение с сайта', model: false, comment: true },
  }[kind];
  const id = `f-${kind}`;
  const options = bikes.map((b) => `<option value="${esc(b.fullName + ' ' + b.year)}">${esc(b.fullName)} ${b.year}</option>`).join('');
  return `<form class="form" data-form="${kind}" id="${id}" novalidate method="post" action="#">
  <input type="hidden" name="subject" value="${esc(cfg.subject)}">
  <div class="form__row">
    <div class="field"><label for="${id}-name">Ваше имя</label><input id="${id}-name" name="name" type="text" autocomplete="name" required minlength="2" maxlength="80" placeholder="Иван"><span class="field__error">Введите имя (не короче 2 символов)</span></div>
    <div class="field"><label for="${id}-phone">Телефон</label><input id="${id}-phone" name="phone" type="tel" inputmode="tel" autocomplete="tel" required placeholder="+7 (___) ___-__-__" data-phone><span class="field__error">Укажите телефон полностью</span></div>
  </div>
  ${cfg.model ? `<div class="field"><label for="${id}-model">Интересующая модель</label><select id="${id}-model" name="model"><option value="">Пока не определился(лась)</option>${options}</select></div>` : ''}
  ${cfg.comment ? `<div class="field"><label for="${id}-msg">Комментарий (необязательно)</label><textarea id="${id}-msg" name="message" maxlength="600" placeholder="Удобное время, вопросы, trade-in…"></textarea></div>` : ''}
  <fieldset class="field" style="border:0;padding:0;margin:0"><legend class="sr-only">Как с вами связаться</legend>
    <div class="contact-way" role="radiogroup" aria-label="Способ связи">
      <label><input type="radio" name="way" value="call" checked><span>Позвоните мне</span></label>
      <label><input type="radio" name="way" value="messenger"><span>Напишите в мессенджер</span></label>
    </div>
  </fieldset>
  <input class="hp" type="text" name="website" tabindex="-1" autocomplete="off" aria-hidden="true">
  <label class="check"><input type="checkbox" name="consent" required><span class="box" aria-hidden="true"></span><span>Я даю <a href="${R}consent.html" target="_blank" rel="noopener">согласие на обработку персональных данных</a> и ознакомлен(а) с <a href="${R}privacy.html" target="_blank" rel="noopener">Политикой конфиденциальности</a>.</span></label>
  <p class="field__error" data-consent-error style="display:none">Без согласия на обработку персональных данных мы не можем принять заявку.</p>
  <button class="btn btn--block" type="submit" data-magnetic>${cfg.btn} ${icon('arrow', 'arrow')}</button>
  <p class="form-note">Нажимая кнопку, вы отправляете заявку. Мы свяжемся с вами в рабочее время (${esc(site.hours)}).</p>
  <div class="form-status" role="status" aria-live="polite"></div>
</form>`;
}

// ---------- SEO ----------
const ld = (obj) => `<script type="application/ld+json">${JSON.stringify(obj).replace(/</g, '\\u003c')}</script>`;
const abs = (path) => `${site.domain}/${path}`.replace(/\/index\.html$/, '/').replace(/\/$/, '/');
const OG_IMAGE = () => `${site.domain}/assets/og-image.png`;
const dealer = () => {
  const sameAs = Object.values(site.socials).filter(Boolean);
  return {
    '@context': 'https://schema.org',
    '@type': 'MotorcycleDealer',
    '@id': `${site.domain}/#dealer`,
    name: site.brand,
    url: `${site.domain}/`,
    image: OG_IMAGE(),
    logo: `${site.domain}/assets/logo.svg`,
    telephone: site.phoneRaw,
    email: site.email,
    description: `Мотосалон ${site.brand} в ${site.cityIn}: новые и подержанные мотоциклы, тест-драйв, рассрочка, trade-in.`,
    address: { '@type': 'PostalAddress', addressLocality: site.city, addressRegion: site.region, addressCountry: 'RU', streetAddress: site.address },
    geo: { '@type': 'GeoCoordinates', latitude: site.geo.lat, longitude: site.geo.lon },
    openingHours: ['Mo-Sa 10:00-20:00', 'Su 11:00-18:00'],
    areaServed: site.city,
    ...(sameAs.length ? { sameAs } : {}),
  };
};

function crumbsOf(ctx) {
  const list = [['Главная', 'index.html'], ...(ctx.page.crumbs ?? [])];
  return list;
}

// ---------- Функции шаблонов ----------
const FN = {
  icon: (ctx, arg) => icon(arg),
  logo_mark: () => LOGO_MARK,
  sprite: () => svg.sprite(),
  hero_bike: () => svg.inline('sport', { label: 'Спортивный мотоцикл — иллюстрация' }),
  hero_bike_naked: () => svg.inline('naked', { label: 'Мотоцикл — иллюстрация' }),
  bike_art: (ctx, arg) => svg.use(arg || ctx.bike?.type || 'sport', { label: ctx.bike ? `${ctx.bike.fullName} — иллюстрация` : '' }),
  home_cards: (ctx) => bikes.filter((b) => b.popular).slice(0, 3).map((b) => card(b, ctx.R)).join('\n'),
  catalog_cards: (ctx) => bikes.map((b) => card(b, ctx.R)).join('\n'),
  related: (ctx) => bikes.filter((b) => b.slug !== ctx.bike.slug).sort((a, b) => (b.type === ctx.bike.type) - (a.type === ctx.bike.type)).slice(0, 3).map((b) => card(b, ctx.R)).join('\n'),
  type_chips: () => Object.entries(TYPE_LABEL).map(([k, v]) => `<button class="chip" type="button" data-filter-type="${k}" aria-pressed="false">${v}</button>`).join(''),
  bikes_count: () => String(bikes.length),
  faq_items: () => FAQ.map(([q, a], i) => `<details${i === 0 ? ' open' : ''}><summary>${esc(q)}</summary><div class="answer"><p>${esc(a)}</p></div></details>`).join('\n'),
  lead_form: (ctx, arg) => leadForm(arg, ctx),
  crumbs: (ctx) => {
    const list = crumbsOf(ctx);
    const items = list.map(([label, href], i) => (i === list.length - 1 ? `<li aria-current="page">${esc(label)}</li>` : `<li><a href="${ctx.R}${href}">${esc(label)}</a></li>`)).join('');
    return `<nav class="breadcrumbs" aria-label="Хлебные крошки"><ol>${items}</ol></nav>`;
  },
  bike_specs: (ctx) => {
    const b = ctx.bike;
    const rows = [
      ['Марка / модель', b.fullName], ['Год выпуска', b.year], ['Состояние', b.condLabel], ['Пробег', b.mileageText], ['Тип', b.typeLabel],
      ['Объём двигателя', `${b.cc}${NBSP}см³`], ['Мощность', `${b.hp}${NBSP}л.с.`], ['Коробка передач', b.gearbox], ['Привод', b.drive],
      ['Сухой/снаряжённый вес', `${b.weight}${NBSP}кг`], ['Бак', `${b.tank}${NBSP}л`], ['ABS', b.abs ? 'Есть' : 'Нет'], ['Цвет', b.color],
    ];
    return `<table class="spec-table"><tbody>${rows.map(([k, v]) => `<tr><th scope="row">${esc(k)}</th><td>${esc(v)}</td></tr>`).join('')}</tbody></table>`;
  },
  bike_features: (ctx) => `<ul class="check-list">${ctx.bike.features.map((f) => `<li>${esc(f)}</li>`).join('')}</ul>`,
  bike_description: (ctx) => ctx.bike.description.map((p) => `<p>${esc(p)}</p>`).join(''),
  bike_badges: (ctx) => (ctx.bike.badges ?? []).map((t, i) => `<span class="badge${i ? ' badge--white' : ''}">${esc(t)}</span>`).join(' '),
  socials: () => {
    const defs = [['vk', 'ВКонтакте'], ['telegram', 'Telegram'], ['youtube', 'YouTube'], ['whatsapp', 'WhatsApp']];
    const links = defs.filter(([k]) => site.socials[k]).map(([k, l]) => `<a href="${esc(site.socials[k])}" target="_blank" rel="noopener noreferrer" aria-label="${l}">${icon(k)}</a>`);
    return links.length ? `<div class="socials">${links.join('')}</div>` : '';
  },
  scripts: (ctx) => ['config.js', 'cookie.js', 'main.js', 'animations.js', 'forms.js', ...(ctx.page.scripts ?? [])].map((s) => `<script src="${ctx.R}js/${s}?v=${site.lastmod}" defer></script>`).join('\n'),
  seo: (ctx) => {
    const { page } = ctx;
    const title = page.title.includes(site.brand) ? page.title : `${page.title} | ${site.brand}`;
    const url = abs(page.out);
    const lines = [
      `<title>${esc(title)}</title>`,
      `<meta name="description" content="${esc(page.description)}">`,
      page.noindex ? '<meta name="robots" content="noindex, follow">' : '<meta name="robots" content="index, follow, max-image-preview:large">',
      `<link rel="canonical" href="${url}">`,
      `<meta property="og:site_name" content="${esc(site.brand)}">`,
      `<meta property="og:locale" content="ru_RU">`,
      `<meta property="og:type" content="${page.ogType ?? 'website'}">`,
      `<meta property="og:title" content="${esc(title)}">`,
      `<meta property="og:description" content="${esc(page.description)}">`,
      `<meta property="og:url" content="${url}">`,
      `<meta property="og:image" content="${OG_IMAGE()}">`,
      `<meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">`,
      `<meta name="twitter:card" content="summary_large_image">`,
      `<meta name="twitter:title" content="${esc(title)}">`,
      `<meta name="twitter:description" content="${esc(page.description)}">`,
      `<meta name="twitter:image" content="${OG_IMAGE()}">`,
    ];
    if (site.verification.yandex) lines.push(`<meta name="yandex-verification" content="${esc(site.verification.yandex)}">`);
    if (site.verification.google) lines.push(`<meta name="google-site-verification" content="${esc(site.verification.google)}">`);
    if (site.verification.bing) lines.push(`<meta name="msvalidate.01" content="${esc(site.verification.bing)}">`);

    const graphs = [];
    const kinds = page.schema ?? [];
    if (kinds.includes('dealer')) graphs.push(dealer());
    if (kinds.includes('faq')) graphs.push({ '@context': 'https://schema.org', '@type': 'FAQPage', mainEntity: FAQ.map(([q, a]) => ({ '@type': 'Question', name: q, acceptedAnswer: { '@type': 'Answer', text: a } })) });
    if (kinds.includes('website')) graphs.push({ '@context': 'https://schema.org', '@type': 'WebSite', name: site.brand, url: `${site.domain}/`, inLanguage: 'ru-RU' });
    if (kinds.includes('itemlist')) graphs.push({ '@context': 'https://schema.org', '@type': 'ItemList', name: `Каталог мотоциклов ${site.brand}`, itemListElement: bikes.map((b, i) => ({ '@type': 'ListItem', position: i + 1, url: abs(b.url), name: `${b.fullName} ${b.year}` })) });
    if (ctx.bike) {
      const b = ctx.bike;
      graphs.push({
        '@context': 'https://schema.org',
        '@type': 'Product',
        name: `${b.fullName} ${b.year}`,
        description: b.short,
        sku: b.slug,
        category: 'Мотоциклы',
        image: OG_IMAGE(),
        ...(b.brand !== 'Demo' ? { brand: { '@type': 'Brand', name: b.brand } } : {}),
        itemCondition: b.condition === 'new' ? 'https://schema.org/NewCondition' : 'https://schema.org/UsedCondition',
        additionalProperty: [
          { '@type': 'PropertyValue', name: 'Объём двигателя', value: `${b.cc} см³` },
          { '@type': 'PropertyValue', name: 'Мощность', value: `${b.hp} л.с.` },
          { '@type': 'PropertyValue', name: 'Пробег', value: b.mileage > 0 ? `${b.mileage} км` : 'Новый' },
        ],
        offers: { '@type': 'Offer', url, price: b.price, priceCurrency: 'RUB', availability: 'https://schema.org/InStock', seller: { '@type': 'Organization', name: site.brand } },
      });
    }
    if (page.crumbs?.length) {
      const list = crumbsOf(ctx);
      graphs.push({ '@context': 'https://schema.org', '@type': 'BreadcrumbList', itemListElement: list.map(([label, href], i) => ({ '@type': 'ListItem', position: i + 1, name: label, item: abs(href) })) });
    }
    return lines.concat(graphs.map(ld)).join('\n  ');
  },
};

// ---------- Движок шаблонов ----------
const RAW_KEYS = new Set(['content']);
const warnings = new Set();
const partialCache = new Map();
const partial = (name) => {
  if (!partialCache.has(name)) partialCache.set(name, read(`src/partials/${name}.html`));
  return partialCache.get(name);
};
const lookup = (ctx, path) => path.split('.').reduce((o, k) => (o == null ? undefined : o[k]), ctx);

function render(tpl, ctx) {
  let out = tpl.replace(/\{\{>\s*([\w-]+)\s*\}\}/g, (_, n) => render(partial(n), ctx));
  out = out.replace(/\{\{@([\w-]+)(?::([^}]*))?\}\}/g, (_, fn, arg) => {
    if (!FN[fn]) throw new Error(`Неизвестная функция шаблона: ${fn}`);
    return FN[fn](ctx, arg?.trim());
  });
  out = out.replace(/\{\{\s*([\w.]+)\s*\}\}/g, (m, key) => {
    const v = lookup(ctx, key);
    if (v === undefined || v === null) { warnings.add(`Нет значения для {{${key}}} (${ctx.page?.out})`); return m; }
    return RAW_KEYS.has(key) || key.endsWith('Html') ? String(v) : esc(v);
  });
  return out;
}

function parsePage(src, file) {
  const m = src.match(/^\s*<!--page\s*([\s\S]*?)-->/);
  if (!m) throw new Error(`В ${file} нет блока <!--page {...} -->`);
  return { meta: JSON.parse(m[1]), body: src.slice(m[0].length) };
}

const built = [];
function buildPage({ src, file, extra = {}, metaOverride = {} }) {
  const { meta, body } = parsePage(src, file);
  const page = { out: basename(file), nav: '', scripts: [], schema: [], crumbs: [], ...meta, ...metaOverride };
  // 404.html отдаётся по любому адресу, поэтому у неё пути от корня домена
  const R = page.abs ? '/' : page.out.includes('/') ? '../' : '';
  const ctx = { site, page, R, ...extra };
  ctx.content = render(body, ctx);
  let html = render(partial('layout'), ctx);
  if (page.nav) html = html.replace(new RegExp(`data-nav="${page.nav}"`, 'g'), `data-nav="${page.nav}" aria-current="page"`);
  write(page.out, html);
  built.push(page);
}

// ---------- Сборка ----------
const pagesDir = join(ROOT, 'src/pages');
for (const f of readdirSync(pagesDir).filter((x) => x.endsWith('.html'))) {
  buildPage({ src: readFileSync(join(pagesDir, f), 'utf8'), file: f });
}

const bikeTpl = read('src/templates/bike.html');
for (const b of bikes) {
  buildPage({
    src: bikeTpl,
    file: b.url,
    extra: { bike: b },
    metaOverride: {
      out: b.url,
      title: `Купить ${b.fullName} ${b.year} в ${site.cityIn} — ${b.priceText}`,
      description: `${b.fullName} ${b.year}: ${b.cc} см³, ${b.hp} л.с., ${b.condLabel.toLowerCase()}${b.mileage ? `, пробег ${num(b.mileage)} км` : ''}. Цена ${b.priceText}. Тест-драйв, рассрочка, trade-in в ${site.brand}, ${site.city}.`,
      nav: 'catalog',
      ogType: 'product',
      scripts: ['calc.js'],
      schema: [],
      crumbs: [['Каталог', 'catalog.html'], [`${b.fullName} ${b.year}`, b.url]],
    },
  });
}

// sitemap.xml
const prio = (p) => (p.out === 'index.html' ? '1.0' : p.out === 'catalog.html' ? '0.9' : p.out.startsWith('bikes/') ? '0.8' : /privacy|terms|cookies|consent/.test(p.out) ? '0.3' : '0.6');
const urls = built.filter((p) => !p.noindex).map((p) => `  <url><loc>${abs(p.out)}</loc><lastmod>${site.lastmod}</lastmod><changefreq>${p.out.startsWith('bikes/') || p.out === 'catalog.html' ? 'weekly' : 'monthly'}</changefreq><priority>${prio(p)}</priority></url>`);
write('sitemap.xml', `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.join('\n')}\n</urlset>\n`);
write('robots.txt', `User-agent: *\nAllow: /\nDisallow: /404.html\n\nSitemap: ${site.domain}/sitemap.xml\n`);
write('site.webmanifest', JSON.stringify({
  name: `${site.brand} — мотосалон в ${site.cityIn}`, short_name: site.brand, lang: 'ru', start_url: './index.html', display: 'standalone',
  background_color: '#0b0b0c', theme_color: '#0b0b0c',
  icons: [{ src: 'assets/favicon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any' }],
}, null, 2) + '\n');

console.log(`Готово: ${built.length} страниц (${bikes.length} карточек моделей), sitemap.xml, robots.txt, site.webmanifest`);
const placeholders = built.reduce((n, p) => n + ((readFileSync(join(ROOT, p.out), 'utf8').match(/class="ph"/g) ?? []).length), 0);
if (placeholders) console.log(`Внимание: в документах осталось полей-заглушек для заполнения: ${placeholders} (ищите class="ph" / «[…]»)`);
if (warnings.size) { console.warn('Предупреждения:\n - ' + [...warnings].join('\n - ')); process.exitCode = 1; }
