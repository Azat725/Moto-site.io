/* Анимации интерфейса: текст по буквам, появление при скролле, 3D-наклон, магнитные кнопки, параллакс, курсор.
   Всё на transform/opacity, наблюдение — через IntersectionObserver, цикл — requestAnimationFrame. */
(function () {
  "use strict";
  var doc = document, root = doc.documentElement;
  var reduce = root.classList.contains("reduce");
  var lite = root.classList.contains("is-lite");
  var fine = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
  var $$ = function (s, c) { return Array.prototype.slice.call((c || doc).querySelectorAll(s)); };

  function whenReady(fn) {
    if (root.classList.contains("is-ready") || reduce) fn();
    else doc.addEventListener("ivax:ready", fn, { once: true });
  }

  /* ---------- Текст по буквам ---------- */
  function splitNode(node, st) {
    Array.prototype.slice.call(node.childNodes).forEach(function (n) {
      if (n.nodeType === 3) {
        var frag = doc.createDocumentFragment();
        n.textContent.split(/([ \t\r\n]+)/).forEach(function (w) {
          if (!w) return;
          if (/^[ \t\r\n]+$/.test(w)) { frag.appendChild(doc.createTextNode(" ")); return; }
          var word = doc.createElement("span"); word.className = "w"; word.setAttribute("aria-hidden", "true");
          Array.from(w).forEach(function (ch) {
            var c = doc.createElement("span"); c.className = "ch"; c.style.setProperty("--i", st.i++); c.textContent = ch; word.appendChild(c);
          });
          frag.appendChild(word);
        });
        node.replaceChild(frag, n);
      } else if (n.nodeType === 1) splitNode(n, st);
    });
  }
  var splits = $$("[data-split]");
  splits.forEach(function (el) {
    el.setAttribute("aria-label", el.textContent.replace(/\s+/g, " ").trim());
    el.classList.add("split");
    var base = el.getAttribute("data-split-base"); if (base) el.style.setProperty("--base", base + "s");
    splitNode(el, { i: 0 });
  });

  /* ---------- Каскад задержек ---------- */
  $$("[data-stagger]").forEach(function (parent) {
    $$("[data-reveal]", parent).forEach(function (el, i) {
      if (!el.style.getPropertyValue("--d")) el.style.setProperty("--d", (i % 6) * 0.09 + "s");
    });
  });

  /* ---------- Появление при скролле ---------- */
  function observe() {
    var targets = $$("[data-reveal], .split");
    if (!("IntersectionObserver" in window) || reduce) { targets.forEach(function (t) { t.classList.add("is-in"); }); return; }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        en.target.classList.add("is-in"); io.unobserve(en.target);
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -6% 0px" });
    targets.forEach(function (t) { io.observe(t); });
  }

  /* ---------- 3D-наклон карточек с бликом ---------- */
  function tilt() {
    if (!fine || reduce || lite) return;
    $$(".tilt").forEach(function (card) {
      var raf = 0, ev;
      function frame() {
        raf = 0;
        var r = card.getBoundingClientRect();
        var x = (ev.clientX - r.left) / r.width, y = (ev.clientY - r.top) / r.height;
        card.style.setProperty("--ry", ((x - 0.5) * 12).toFixed(2) + "deg");
        card.style.setProperty("--rx", ((0.5 - y) * 10).toFixed(2) + "deg");
        card.style.setProperty("--mx", (x * 100).toFixed(1) + "%");
        card.style.setProperty("--my", (y * 100).toFixed(1) + "%");
      }
      card.addEventListener("pointermove", function (e) {
        if (e.pointerType !== "mouse") return;
        ev = e; card.classList.add("is-tilting"); if (!raf) raf = requestAnimationFrame(frame);
      });
      card.addEventListener("pointerleave", function () {
        card.classList.remove("is-tilting");
        card.style.setProperty("--rx", "0deg"); card.style.setProperty("--ry", "0deg");
      });
    });
  }

  /* ---------- Магнитные кнопки ---------- */
  function magnetic() {
    if (!fine || reduce) return;
    $$("[data-magnetic]").forEach(function (el) {
      el.addEventListener("pointermove", function (e) {
        if (e.pointerType !== "mouse") return;
        var r = el.getBoundingClientRect();
        el.style.setProperty("--tx", ((e.clientX - (r.left + r.width / 2)) * 0.22).toFixed(1) + "px");
        el.style.setProperty("--ty", ((e.clientY - (r.top + r.height / 2)) * 0.32).toFixed(1) + "px");
      });
      el.addEventListener("pointerleave", function () { el.style.setProperty("--tx", "0px"); el.style.setProperty("--ty", "0px"); });
    });
  }

  /* ---------- Hero: линии скорости, параллакс ---------- */
  function hero() {
    var h = $$(".hero")[0];
    if (!h) return;
    var lines = $$("[data-speed-lines]", h)[0];
    if (lines && !reduce && !lite) {
      var n = window.innerWidth < 700 ? 9 : 16, frag = doc.createDocumentFragment();
      for (var i = 0; i < n; i++) {
        var s = doc.createElement("i"), d = 1.1 + Math.random() * 1.9;
        s.style.setProperty("--y", (4 + Math.random() * 90).toFixed(1) + "%");
        s.style.setProperty("--w", (90 + Math.random() * 230).toFixed(0) + "px");
        s.style.setProperty("--dur", d.toFixed(2) + "s");
        s.style.setProperty("--dl", (-Math.random() * d * 2).toFixed(2) + "s");
        s.style.setProperty("--o", (0.25 + Math.random() * 0.55).toFixed(2));
        frag.appendChild(s);
      }
      lines.appendChild(frag);
    }
    // Параллакс слоёв от курсора (CSS-свойство translate не конфликтует с transform-анимациями)
    if (!fine || reduce || lite) return;
    var layers = $$(".hero__layer", h), tx = 0, ty = 0, cx = 0, cy = 0, raf = 0;
    h.addEventListener("pointermove", function (e) {
      var r = h.getBoundingClientRect();
      tx = (e.clientX - r.left) / r.width - 0.5; ty = (e.clientY - r.top) / r.height - 0.5;
      if (!raf) raf = requestAnimationFrame(loop);
    });
    function loop() {
      cx += (tx - cx) * 0.08; cy += (ty - cy) * 0.08;
      layers.forEach(function (l) {
        var d = parseFloat(l.getAttribute("data-depth")) || 10;
        l.style.translate = (cx * d).toFixed(2) + "px " + (cy * d * 0.7).toFixed(2) + "px";
      });
      raf = (Math.abs(tx - cx) > 0.002 || Math.abs(ty - cy) > 0.002) ? requestAnimationFrame(loop) : 0;
    }
  }

  /* ---------- Кольцо-курсор ---------- */
  function cursor() {
    var c = doc.getElementById("cursor");
    if (!c || !fine || reduce || lite) return;
    var x = 0, y = 0, tx = 0, ty = 0, s = 1, ts = 1, raf = 0;
    window.addEventListener("pointermove", function (e) {
      if (e.pointerType !== "mouse") return;
      tx = e.clientX; ty = e.clientY; c.classList.add("is-on");
      var link = e.target.closest && e.target.closest("a, button, summary, label, input, select, textarea, .tilt");
      ts = link ? 1.7 : 1; c.classList.toggle("is-link", !!link);
      if (!raf) raf = requestAnimationFrame(loop);
    }, { passive: true });
    doc.addEventListener("pointerleave", function () { c.classList.remove("is-on"); });
    function loop() {
      x += (tx - x) * 0.22; y += (ty - y) * 0.22; s += (ts - s) * 0.2;
      c.style.transform = "translate3d(" + x.toFixed(1) + "px," + y.toFixed(1) + "px,0) scale(" + s.toFixed(3) + ")";
      raf = (Math.abs(tx - x) > 0.1 || Math.abs(ty - y) > 0.1 || Math.abs(ts - s) > 0.01) ? requestAnimationFrame(loop) : 0;
    }
  }

  /* ---------- Мобильная панель: прячем у футера и при вводе ---------- */
  var bar = doc.getElementById("mobile-bar");
  if (bar) {
    doc.addEventListener("focusin", function (e) { if (/^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName)) bar.classList.add("is-hidden"); });
    doc.addEventListener("focusout", function () { bar.classList.remove("is-hidden"); });
  }

  tilt(); magnetic(); hero(); cursor();
  whenReady(function () { observe(); });
})();
