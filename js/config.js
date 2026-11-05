/* Настройки сайта. Меняйте здесь — без правки остального кода. */
window.IVAX_CONFIG = {
  // Адрес обработчика форм (Formspree, свой API, Bitrix24/amoCRM webhook и т. п.).
  // Пока пусто — формы работают в ДЕМО-режиме: заявка никуда не уходит, посетителю это честно сообщается.
  // Ожидается POST application/json: { name, phone, model, message, way, subject, page, ts }
  formEndpoint: "",

  // Счётчики. Загружаются ТОЛЬКО после согласия на соответствующую категорию cookie.
  analytics: {
    yandexMetrikaId: "", // например 12345678
    googleAnalyticsId: "" // например G-XXXXXXXXXX
  },
  marketing: {
    // сюда можно добавить пиксели (VK, Facebook и т. п.) — они подключаются только после согласия
    scripts: [] // [{ src: "https://example.com/pixel.js" }]
  },

  // Версия политики cookie: при смене согласие запрашивается заново
  cookieVersion: 1,
  // Через сколько дней повторно спрашивать согласие
  cookieTtlDays: 365,

  // Ставка для калькулятора (в процентах годовых) — условная
  calcRate: 19.9
};
