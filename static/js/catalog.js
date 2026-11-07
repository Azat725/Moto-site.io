/* Каталог: фильтры по типу, мощности, линейке, поиск и сортировка поверх готовых карточек (видны и без JS). */
(function () {
  "use strict";
  var grid = document.getElementById("catalog-grid");
  if (!grid) return;
  var reduce = document.documentElement.classList.contains("reduce");
  var items = Array.prototype.slice.call(grid.querySelectorAll(".bike-item"));
  items.forEach(function (el, i) { el.dataset.order = i; });
  var chips = Array.prototype.slice.call(document.querySelectorAll("[data-filter]"));
  var search = document.getElementById("f-search");
  var line = document.getElementById("f-line");
  var sort = document.getElementById("f-sort");
  var reset = document.getElementById("f-reset");
  var count = document.getElementById("catalog-count");
  var empty = document.getElementById("catalog-empty");
  var form = document.getElementById("catalog-filters");
  var DEFAULTS = Object.freeze({ type: "all", power: "", line: "all", q: "", sort: "default" });
  var state = DEFAULTS;

  function plural(n) {
    var a = n % 10, b = n % 100;
    if (a === 1 && b !== 11) return "модель";
    if (a >= 2 && a <= 4 && (b < 10 || b >= 20)) return "модели";
    return "моделей";
  }
  function num(v, fallback) { var n = parseFloat(v); return isNaN(n) ? fallback : n; }
  function matches(el, s) {
    var d = el.dataset, q = s.q.trim().toLowerCase();
    return (s.type === "all" || d.type === s.type) &&
      (!s.power || (" " + d.power + " ").indexOf(" " + s.power + " ") !== -1) &&
      (s.line === "all" || d.line === s.line) &&
      (!q || d.name.indexOf(q) !== -1);
  }
  function comparator(kind) {
    return {
      "price-asc": function (a, b) { return num(a.dataset.price, 1e12) - num(b.dataset.price, 1e12); },
      "price-desc": function (a, b) { return num(b.dataset.price, 0) - num(a.dataset.price, 0); },
      "speed-desc": function (a, b) { return num(b.dataset.speed, 0) - num(a.dataset.speed, 0); },
      "range-desc": function (a, b) { return num(b.dataset.range, 0) - num(a.dataset.range, 0); }
    }[kind] || function (a, b) { return a.dataset.order - b.dataset.order; };
  }
  function syncUrl(s) {
    var p = new URLSearchParams();
    if (s.type !== "all") p.set("type", s.type);
    if (s.power) p.set("power", s.power);
    if (s.line !== "all") p.set("line", s.line);
    if (s.q) p.set("q", s.q);
    if (s.sort !== "default") p.set("sort", s.sort);
    try { history.replaceState(null, "", location.pathname + (p.toString() ? "?" + p : "") + location.hash); } catch (e) {}
  }
  function render(animate) {
    var shown = 0;
    items.forEach(function (el) {
      var ok = matches(el, state);
      el.hidden = !ok;
      if (!ok) return;
      shown += 1;
      if (animate && !reduce) {
        el.classList.remove("is-showing"); void el.offsetWidth;
        el.style.setProperty("--sd", Math.min(shown, 8) * 0.05 + "s");
        el.classList.add("is-showing");
      }
    });
    items.slice().sort(comparator(state.sort)).forEach(function (el) { grid.appendChild(el); });
    if (count) count.textContent = "Найдено: " + shown + " " + plural(shown);
    if (empty) empty.classList.toggle("is-on", shown === 0);
    chips.forEach(function (c) {
      var key = c.dataset.filter, val = c.dataset.value;
      c.setAttribute("aria-pressed", String(key === "type" ? state.type === val : state.power === val));
    });
    syncUrl(state);
  }
  function update(patch, animate) { state = Object.freeze(Object.assign({}, state, patch)); render(animate); }

  chips.forEach(function (c) {
    c.addEventListener("click", function () {
      if (c.dataset.filter === "type") update({ type: c.dataset.value }, true);
      else update({ power: state.power === c.dataset.value ? "" : c.dataset.value }, true);
    });
  });
  if (search) search.addEventListener("input", function () { update({ q: search.value }, false); });
  if (line) line.addEventListener("change", function () { update({ line: line.value }, true); });
  if (sort) sort.addEventListener("change", function () { update({ sort: sort.value }, true); });
  if (reset) reset.addEventListener("click", function () {
    if (search) search.value = ""; if (line) line.value = "all"; if (sort) sort.value = "default";
    state = DEFAULTS; render(true);
  });
  if (form) form.addEventListener("submit", function (e) { e.preventDefault(); });
  var moreBtn = document.querySelector(".toolbar__more-btn");
  var more = document.getElementById("toolbar-more");
  if (moreBtn && more) moreBtn.addEventListener("click", function () {
    var open = moreBtn.getAttribute("aria-expanded") !== "true";
    moreBtn.setAttribute("aria-expanded", String(open));
    more.classList.toggle("is-open", open);
  });

  /* Параметры из адреса принимаем, только если такое значение реально есть в фильтрах. */
  function allowed(value, values, fallback) { return values.indexOf(value) !== -1 ? value : fallback; }
  function chipValues(kind) { return chips.filter(function (c) { return c.dataset.filter === kind; }).map(function (c) { return c.dataset.value; }); }
  function optionValues(select) { return select ? Array.prototype.map.call(select.options, function (o) { return o.value; }) : []; }
  var qs = new URLSearchParams(location.search);
  var initial = {
    type: allowed(qs.get("type") || "all", chipValues("type"), "all"),
    power: allowed(qs.get("power") || "", chipValues("power"), ""),
    line: allowed(qs.get("line") || "all", optionValues(line), "all"),
    q: (qs.get("q") || "").slice(0, 60),
    sort: allowed(qs.get("sort") || "default", optionValues(sort), "default")
  };
  if (search) search.value = initial.q;
  if (line) line.value = initial.line;
  if (sort) sort.value = initial.sort;
  update(initial, false);
})();
