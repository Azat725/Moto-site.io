/* Согласие на cookie: баннер, категории, отзыв. Аналитика/маркетинг грузятся только после согласия. */
(function () {
  "use strict";
  var CFG = window.IVAX_CONFIG || {};
  var KEY = "ivax_cookie_consent";
  var banner = document.getElementById("cookie");
  if (!banner) return;

  var accept = banner.querySelector("[data-cookie-accept]");
  var necessary = banner.querySelector("[data-cookie-necessary]");
  var toggle = banner.querySelector("[data-cookie-toggle]");
  var inputs = {
    analytics: banner.querySelector('[data-cookie-cat="analytics"]'),
    marketing: banner.querySelector('[data-cookie-cat="marketing"]')
  };
  var loaded = {};

  function read() {
    try {
      var v = JSON.parse(localStorage.getItem(KEY) || "null");
      if (!v || v.v !== CFG.cookieVersion) return null;
      if (Date.now() - v.ts > (CFG.cookieTtlDays || 365) * 864e5) return null;
      return v;
    } catch (e) { return null; }
  }
  function write(analytics, marketing) {
    var v = { v: CFG.cookieVersion, ts: Date.now(), necessary: true, analytics: !!analytics, marketing: !!marketing };
    try { localStorage.setItem(KEY, JSON.stringify(v)); } catch (e) { /* режим приватности — просто не запомним */ }
    apply(v);
    return v;
  }

  function addScript(src, attrs) {
    var s = document.createElement("script");
    s.async = true; s.src = src;
    if (attrs) Object.keys(attrs).forEach(function (k) { s.setAttribute(k, attrs[k]); });
    document.head.appendChild(s);
  }

  function loadMetrika(id) {
    if (!id || loaded.ym) return; loaded.ym = true;
    (function (m, e, t, r, i, k, a) {
      m[i] = m[i] || function () { (m[i].a = m[i].a || []).push(arguments); };
      m[i].l = 1 * new Date(); k = e.createElement(t); a = e.getElementsByTagName(t)[0];
      k.async = 1; k.src = r; a.parentNode.insertBefore(k, a);
    })(window, document, "script", "https://mc.yandex.ru/metrika/tag.js", "ym");
    window.ym(id, "init", { clickmap: true, trackLinks: true, accurateTrackBounce: true });
  }
  function loadGA(id) {
    if (!id || loaded.ga) return; loaded.ga = true;
    addScript("https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(id));
    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { window.dataLayer.push(arguments); };
    window.gtag("js", new Date()); window.gtag("config", id, { anonymize_ip: true });
  }

  function apply(v) {
    if (v.analytics) {
      loadMetrika((CFG.analytics || {}).yandexMetrikaId);
      loadGA((CFG.analytics || {}).googleAnalyticsId);
    }
    if (v.marketing && !loaded.mk) {
      loaded.mk = true;
      ((CFG.marketing || {}).scripts || []).forEach(function (s) { if (s && s.src) addScript(s.src); });
    }
    document.dispatchEvent(new CustomEvent("ivax:consent", { detail: v }));
  }

  function setPrefsOpen(open) {
    banner.classList.toggle("is-prefs", open);
    toggle.setAttribute("aria-expanded", String(open));
    toggle.textContent = open ? "Сохранить выбор" : "Настроить";
  }
  function show() {
    var v = read();
    inputs.analytics.checked = !!(v && v.analytics);
    inputs.marketing.checked = !!(v && v.marketing);
    banner.classList.add("is-visible");
  }
  function hide() { banner.classList.remove("is-visible"); setPrefsOpen(false); }

  accept.addEventListener("click", function () { write(true, true); hide(); toast("Настройки cookie сохранены"); });
  necessary.addEventListener("click", function () { write(false, false); hide(); toast("Сохранены только необходимые cookie"); });
  toggle.addEventListener("click", function () {
    if (banner.classList.contains("is-prefs")) { write(inputs.analytics.checked, inputs.marketing.checked); hide(); toast("Настройки cookie сохранены"); }
    else setPrefsOpen(true);
  });
  document.addEventListener("click", function (e) {
    var t = e.target.closest && e.target.closest("[data-cookie-settings]");
    if (!t) return;
    e.preventDefault(); show(); setPrefsOpen(true);
    var first = banner.querySelector("input:not([disabled])"); if (first) first.focus({ preventScroll: true });
  });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && banner.classList.contains("is-prefs")) { hide(); } });

  function toast(msg) { if (window.IVAX && window.IVAX.toast) window.IVAX.toast(msg); }

  window.IVAXConsent = { get: read, open: function () { show(); setPrefsOpen(true); } };

  var saved = read();
  if (saved) apply(saved);
  else setTimeout(show, 1800); // не перекрываем первый экран прелоадером
})();
