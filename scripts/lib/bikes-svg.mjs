// Векторные силуэты мотоциклов (заглушки вместо фото).
// Все линии имеют pathLength="1" — это позволяет «прорисовывать» их анимацией stroke-dashoffset.
// viewBox 0 0 800 400. Колёса: центры (170,290) и (630,290), земля на y≈371.

const P = (cls, d) => `<path class="${cls}" pathLength="1" d="${d}"/>`;
const C = (cls, cx, cy, r) => `<circle class="${cls}" pathLength="1" cx="${cx}" cy="${cy}" r="${r}"/>`;

function spokes(cx, cy) {
  const out = [];
  for (let k = 0; k < 6; k++) {
    const a = (k * Math.PI) / 3 + 0.2;
    out.push(`M${(cx + Math.cos(a) * 12).toFixed(1)} ${(cy + Math.sin(a) * 12).toFixed(1)}L${(cx + Math.cos(a) * 52).toFixed(1)} ${(cy + Math.sin(a) * 52).toFixed(1)}`);
  }
  return out.join('');
}

function wheel(cx, cy) {
  return [
    C('bk-d bk-tyre', cx, cy, 76),
    C('bk-d', cx, cy, 54),
    `<g class="wheel">${P('bk-d bk-thin', spokes(cx, cy))}${C('bk-d bk-thin', cx, cy, 34)}${C('bk-d', cx, cy, 10)}</g>`,
  ];
}

const swingarm = () => [
  P('bk-d', 'M300 262L170 290M304 282L170 290'),
  P('bk-d', 'M292 246L262 190'), // амортизатор
];

const BODIES = {
  sport: () => [
    ...swingarm(),
    P('bk-d', 'M350 318C300 336 220 336 130 312L138 296C220 318 300 318 340 304'),                 // выхлоп
    P('bk-d bk-body', 'M318 248L326 312L430 312L448 262L420 240Z'),                                 // картер
    P('bk-d', 'M576 146L630 290M590 140L644 284'),                                                  // вилка
    P('bk-d', 'M550 244A92 92 0 0 1 662 204'),                                                      // переднее крыло
    P('bk-d bk-body', 'M120 176C150 164 220 164 290 160C330 158 352 150 380 138C410 124 460 118 508 116L536 110L566 80C574 76 586 80 590 88L600 126C640 140 668 172 676 204C660 214 630 222 600 222L560 232L520 244C480 256 440 262 400 272L340 280C300 272 270 244 240 222C200 204 150 196 118 192Z'), // кузов
    P('bk-d bk-thin', 'M470 198C520 178 590 172 650 198'),
    P('bk-d bk-thin', 'M160 172C210 168 270 168 330 162'),
    P('bk-acc', 'M618 150L664 184L640 196L610 168Z'),                                               // фара
    P('bk-acc', 'M118 176L132 170L140 186L120 192Z'),                                               // задний свет
    P('bk-acc', 'M484 254L540 240L604 226L652 212L654 220L608 234L544 250L488 264Z'),               // красная полоса
    P('bk-accs bk-d', 'M392 134C430 122 470 120 506 120'),
  ],
  naked: () => [
    ...swingarm(),
    P('bk-d', 'M350 318C300 336 220 336 130 312L138 296C220 318 300 318 340 304'),
    P('bk-d bk-body', 'M330 214L336 300L436 300L456 214Z'),                                         // двигатель
    P('bk-d bk-body', 'M360 214L372 182L430 176L444 212'),                                          // цилиндры
    P('bk-d', 'M472 160L520 176L504 236L466 228Z'),                                                 // радиатор
    P('bk-d', 'M546 136L626 288M562 130L642 282'),                                                  // вилка
    P('bk-d', 'M570 244C602 224 646 224 674 246'),                                                  // крыло
    P('bk-d bk-body', 'M124 178C170 168 240 168 300 164C340 162 360 152 384 138C410 124 450 120 482 128C508 134 530 140 546 138L500 200L452 210L380 214L330 214L290 206L240 196L170 190Z'),
    P('bk-d', 'M150 176C200 170 262 170 330 166'),
    P('bk-d', 'M300 168L262 192M546 140L470 168'),
    P('bk-d', 'M540 118L560 106L592 108M548 138L546 120'),
    C('bk-d bk-body', 590, 160, 26),
    C('bk-acc', 590, 160, 12),
    P('bk-acc', 'M124 178L138 172L144 188L128 192Z'),
    P('bk-accs bk-d', 'M388 150C424 134 458 134 486 144'),
  ],
  cruiser: () => [
    ...swingarm(),
    P('bk-d', 'M310 318C250 332 160 328 96 310M310 304C250 318 160 314 96 298'),                  // двойной выхлоп
    P('bk-d', 'M82 262A95 95 0 0 1 252 234'),                                                       // заднее крыло
    P('bk-d bk-body', 'M322 236L330 308L426 308L438 236Z'),
    P('bk-d bk-body', 'M338 238L318 192L352 180L380 236'),                                          // цилиндры V-twin
    P('bk-d bk-body', 'M410 238L422 194L456 196L444 242'),
    P('bk-d', 'M552 130L636 290M570 124L652 284'),                                                  // вилка с большим вылетом
    P('bk-d', 'M570 248A70 70 0 0 1 698 236'),                                                      // переднее крыло
    P('bk-d bk-body', 'M150 220C220 232 300 222 372 208L384 222C336 248 250 256 150 246Z'),         // сиденье
    P('bk-d bk-body', 'M380 176C420 152 474 150 506 176C522 190 512 210 486 214L392 216C372 204 370 186 380 176Z'), // бак
    P('bk-d', 'M552 130C526 96 556 70 594 78'),
    P('bk-d', 'M502 180L552 132M552 134L470 214L438 236M150 246L250 238L322 236'),                                                     // руль
    C('bk-d bk-body', 606, 178, 24),
    C('bk-acc', 606, 178, 10),
    P('bk-accs bk-d', 'M392 180C426 166 466 166 494 180'),
    P('bk-acc', 'M82 262L88 246L102 250L96 268Z'),
  ],
};

export const BIKE_TYPES = Object.keys(BODIES);

function parts(type) {
  const body = BODIES[type] ?? BODIES.sport;
  // колёса рисуем первыми, чтобы кузов закрывал их линии
  return [...wheel(170, 290), ...wheel(630, 290), ...body()];
}

/** <symbol> для спрайта: используется в карточках через <use>. */
export function symbol(type) {
  return `<symbol id="bike-${type}" viewBox="0 0 800 400">${parts(type).join('')}</symbol>`;
}

export function sprite() {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="0" height="0" style="position:absolute" aria-hidden="true" focusable="false"><defs>${BIKE_TYPES.map(symbol).join('')}</defs></svg>`;
}

/** Мотоцикл-иконка для карточек. */
export function use(type, { cls = 'bike', label = '' } = {}) {
  const t = BIKE_TYPES.includes(type) ? type : 'sport';
  const a11y = label ? `role="img" aria-label="${label}"` : 'aria-hidden="true"';
  return `<svg class="${cls}" viewBox="0 0 800 400" ${a11y} focusable="false"><use href="#bike-${t}"/></svg>`;
}

/** Инлайн-версия для hero: каждому штриху задаём --k для каскадной прорисовки. */
export function inline(type, { cls = 'hero-bike', label = '' } = {}) {
  let k = 0;
  const html = parts(type)
    .join('')
    .replace(/<(path|circle) class="/g, (m, tag) => `<${tag} style="--k:${k++}" class="`);
  const a11y = label ? `role="img" aria-label="${label}"` : 'aria-hidden="true"';
  return `<svg class="${cls}" viewBox="0 0 800 400" ${a11y} focusable="false"><g class="rig">${html}</g></svg>`;
}
