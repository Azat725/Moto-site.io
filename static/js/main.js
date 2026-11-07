/* Ядро: прелоадер, шапка, меню, переходы между страницами, спидометр-«наверх», тосты */
(function () {
  "use strict";
  var doc = document, root = doc.documentElement;
  var reduce = root.classList.contains("reduce");
  var $ = function (s, c) { return (c || doc).querySelector(s); };
  window.IVAX = window.IVAX || {};

  /* ---------- Тост ---------- */
  var toastEl = $("#toast"), toastTimer;
  window.IVAX.toast = function (msg) {
    if (!toastEl) return;
    toastEl.textContent = msg; toastEl.classList.add("is-on");
    clearTimeout(toastTimer); toastTimer = setTimeout(function () { toastEl.classList.remove("is-on"); }, 2600);
  };

  /* ---------- Прелоадер ---------- */
  var seen = false;
  try { seen = !!sessionStorage.getItem("ivax_seen"); } catch (e) {}
  var started = performance.now();
  var minShow = seen || reduce ? 120 : 2000; // первый визит — полный «разгон» тахометра
  var ready = false;
  function setReady() {
    if (ready) return; ready = true;
    root.classList.add("is-ready");
    try { sessionStorage.setItem("ivax_seen", "1"); } catch (e) {}
    doc.dispatchEvent(new CustomEvent("ivax:ready"));
  }
  function whenLoaded() {
    var wait = Math.max(0, minShow - (performance.now() - started));
    setTimeout(setReady, wait);
  }
  if (doc.readyState === "complete") whenLoaded(); else window.addEventListener("load", whenLoaded);
  setTimeout(setReady, 4500); // страховка: не держим посетителя на экране загрузки

  /* ---------- Шапка ---------- */
  var header = $("#site-header");
  var mbar = $("#mobile-bar");
  var gauge = $("#gauge");
  var needle = gauge && $(".g-needle", gauge);
  var lastY = 0, ticking = false, lastTs = performance.now(), vel = 0, shownNeedle = -135;

  function onScroll() {
    var y = window.scrollY || root.scrollTop;
    var h = Math.max(1, root.scrollHeight - window.innerHeight);
    var p = Math.min(1, Math.max(0, y / h));
    if (header) header.classList.toggle("is-scrolled", y > 40);
    if (gauge) {
      gauge.classList.toggle("is-on", y > 420);
      gauge.setAttribute("aria-label", "Наверх. Страница прочитана на " + Math.round(p * 100) + "%");
    }
    var now = performance.now();
    vel = Math.min(1, Math.abs(y - lastY) / Math.max(1, now - lastTs) / 3); // скорость скролла 0..1
    lastY = y; lastTs = now;
    targetNeedle = -135 + p * 270;
    if (!needleRaf) needleRaf = requestAnimationFrame(tickNeedle);
    ticking = false;
  }
  var targetNeedle = -135, needleRaf = 0;
  function tickNeedle() {
    // стрелка «газует» при быстром скролле и возвращается к прогрессу страницы
    var boosted = Math.min(135, targetNeedle + vel * 60);
    shownNeedle += (boosted - shownNeedle) * 0.18;
    vel *= 0.88;
    if (needle && !reduce) needle.style.transform = "rotate(" + shownNeedle.toFixed(2) + "deg)";
    else if (needle) needle.style.transform = "rotate(" + targetNeedle.toFixed(2) + "deg)";
    needleRaf = (Math.abs(boosted - shownNeedle) > 0.2 || vel > 0.01) ? requestAnimationFrame(tickNeedle) : 0;
  }
  window.addEventListener("scroll", function () { if (!ticking) { ticking = true; requestAnimationFrame(onScroll); } }, { passive: true });
  onScroll();
  if (gauge) gauge.addEventListener("click", function () { window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" }); });

  /* ---------- Мобильное меню ---------- */
  var burger = $(".burger"), menu = $("#mobile-menu");
  function setMenu(open) {
    if (!burger || !menu) return;
    burger.setAttribute("aria-expanded", String(open));
    burger.setAttribute("aria-label", open ? "Закрыть меню" : "Открыть меню");
    menu.classList.toggle("is-open", open);
    doc.body.classList.toggle("is-locked", open);
    if (mbar) mbar.classList.toggle("is-hidden", open);
    if (open) { var a = $("a", menu); if (a) setTimeout(function () { a.focus({ preventScroll: true }); }, 450); }
  }
  if (burger && menu) {
    burger.addEventListener("click", function () { setMenu(burger.getAttribute("aria-expanded") !== "true"); });
    doc.addEventListener("keydown", function (e) { if (e.key === "Escape") setMenu(false); });
    menu.addEventListener("click", function (e) { if (e.target.closest("a")) setMenu(false); });
    window.matchMedia("(min-width: 961px)").addEventListener("change", function (e) { if (e.matches) setMenu(false); });
  }

  /* ---------- Переходы между страницами (красная шторка) ---------- */
  var pre = $("#preloader");
  function sameOrigin(a) { return a.origin === location.origin && a.pathname.replace(/\/$/, "") + a.search !== location.pathname.replace(/\/$/, "") + location.search; }
  doc.addEventListener("click", function (e) {
    if (reduce || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target.closest && e.target.closest("a[href]");
    if (!a || a.target === "_blank" || a.hasAttribute("download") || /^(tel|mailto):/.test(a.getAttribute("href"))) return;
    if (!/^https?:$/.test(a.protocol) || a.origin !== location.origin) return;
    if (a.pathname === location.pathname && a.search === location.search) return; // якорь на этой же странице
    if (!pre) return;
    e.preventDefault();
    var url = a.href;
    pre.classList.add("is-reset"); void pre.offsetWidth; pre.classList.remove("is-reset");
    root.classList.add("is-leaving");
    setTimeout(function () { location.href = url; }, 560);
  });
  window.addEventListener("pageshow", function (e) { if (e.persisted) root.classList.remove("is-leaving"); });
})();
