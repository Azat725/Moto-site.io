/* Конфигуратор: суммирует готовые рублёвые компоненты (в копейках) и округляет вверх до шага.
   Формула совпадает с сервером (apps/catalog/pricing.py); сервер всё равно пересчитывает цену при заявке. */
(function () {
  "use strict";
  var dataEl = document.getElementById("cfg-data");
  var form = document.getElementById("configurator");
  if (!dataEl || !form) return;
  var cfg;
  try { cfg = JSON.parse(dataEl.textContent); } catch (e) { return; }
  var NBSP = " ";
  var totalEl = document.getElementById("cfg-total");
  var summaryEl = document.getElementById("order-summary");
  var leadForm = document.querySelector('[data-lead-form][data-kind="model"]');
  var reduce = document.documentElement.classList.contains("reduce");

  function fmt(rub) { return String(rub).replace(/\B(?=(\d{3})+(?!\d))/g, NBSP) + NBSP + "₽"; }

  /** Итог в рублях или null (цена по запросу). Экспортируется для тестов. */
  function computeTotal(data, variantId, optionCodes) {
    var variant = data.variants.filter(function (v) { return String(v.id) === String(variantId); })[0];
    if (!variant || variant.kop === null) return null;
    var sum = variant.kop;
    var seen = {};
    optionCodes.forEach(function (code) {
      if (seen[code]) return; seen[code] = true;
      var opt = data.options.filter(function (o) { return o.code === code; })[0];
      if (opt && !opt.included) sum += opt.kop;
    });
    var unit = data.step * 100;
    return Math.ceil(sum / unit) * data.step;
  }
  window.IVAXPricing = Object.freeze({ computeTotal: computeTotal });

  function selection() {
    var variant = form.querySelector('input[name="cfg-variant"]:checked');
    var options = Array.prototype.slice.call(form.querySelectorAll('input[name="cfg-option"]:checked:not(:disabled)'));
    var color = form.querySelector('input[name="cfg-color"]:checked');
    return Object.freeze({
      variant: variant ? variant.value : "",
      variantLabel: variant ? variant.closest("label").querySelector(".cfg-option__name").textContent.trim() : "",
      options: options.map(function (o) { return o.value; }),
      optionLabels: options.map(function (o) { return o.closest("label").querySelector(".cfg-option__name").firstChild.textContent.trim(); }),
      color: color ? color.value : "",
      colorLabel: color ? color.closest("label").querySelector("em").textContent.trim() : ""
    });
  }

  var srEl = document.getElementById("cfg-total-sr");
  var shown = null, raf = 0, timer = 0;
  function animateTo(value) {
    cancelAnimationFrame(raf);
    clearTimeout(timer);
    if (value === null) { totalEl.textContent = "по запросу"; shown = null; return; }
    if (reduce || shown === null) { totalEl.textContent = fmt(value); shown = value; return; }
    var from = shown, t0 = performance.now();
    timer = setTimeout(function () { totalEl.textContent = fmt(value); shown = value; }, 420);
    (function step(now) {
      var p = Math.min(1, (now - t0) / 380), e = 1 - Math.pow(1 - p, 3);
      totalEl.textContent = fmt(Math.round((from + (value - from) * e) / cfg.step) * cfg.step);
      if (p < 1) raf = requestAnimationFrame(step); else shown = value;
    })(t0);
    totalEl.classList.remove("is-tick"); void totalEl.offsetWidth; totalEl.classList.add("is-tick");
  }

  function update() {
    var s = selection();
    var total = computeTotal(cfg, s.variant, s.options);
    animateTo(total);
    if (srEl) srEl.textContent = "Итого: " + (total === null ? "цена по запросу" : fmt(total));
    var parts = [s.variantLabel].concat(s.optionLabels.length ? ["опции: " + s.optionLabels.join(", ")] : [], s.colorLabel ? ["цвет: " + s.colorLabel] : []);
    if (summaryEl) summaryEl.textContent = parts.join("; ") + " — " + (total === null ? "цена по запросу" : fmt(total));
    if (leadForm) {
      leadForm.elements.variant.value = s.variant;
      leadForm.elements.options.value = s.options.join(",");
      leadForm.elements.color.value = s.color;
      leadForm.elements.client_total.value = total === null ? "" : String(total);
    }
  }

  form.addEventListener("change", update);
  form.addEventListener("submit", function (e) { e.preventDefault(); });
  update();
})();
