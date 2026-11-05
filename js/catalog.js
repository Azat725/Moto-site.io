/* Каталог: фильтры, поиск, сортировка поверх статических карточек (контент виден поисковикам и без JS). */
(function () {
  "use strict";
  var grid = document.getElementById("catalog-grid");
  if (!grid) return;
  var reduce = document.documentElement.classList.contains("reduce");
  var items = Array.prototype.slice.call(grid.querySelectorAll(".bike-item"));
  items.forEach(function (el, i) { el.dataset.order = i; });

  var chips = Array.prototype.slice.call(document.querySelectorAll("[data-filter-type]"));
  var search = document.getElementById("f-search"), cond = document.getElementById("f-cond"), sort = document.getElementById("f-sort");
  var reset = document.getElementById("f-reset"), count = document.getElementById("catalog-count"), empty = document.getElementById("catalog-empty");
  var state = { type: "all", cond: "all", q: "", sort: "default" };

  function plural(n) { var a = n % 10, b = n % 100; return (a === 1 && b !== 11) ? "модель" : (a >= 2 && a <= 4 && (b < 10 || b >= 20)) ? "модели" : "моделей"; }

  function apply(animate) {
    var shown = 0;
    var q = state.q.trim().toLowerCase();
    items.forEach(function (el) {
      var ok = (state.type === "all" || el.dataset.type === state.type) &&
               (state.cond === "all" || el.dataset.condition === state.cond) &&
               (!q || el.dataset.name.indexOf(q) !== -1);
      if (ok) shown++;
      el.hidden = !ok;
      if (ok && animate && !reduce) {
        el.classList.remove("is-showing"); void el.offsetWidth;
        el.style.setProperty("--sd", Math.min(shown, 8) * 0.05 + "s");
        el.classList.add("is-showing");
      }
    });
    var sorted = items.slice().sort(function (a, b) {
      var A = a.dataset, B = b.dataset;
      switch (state.sort) {
        case "price-asc": return A.price - B.price;
        case "price-desc": return B.price - A.price;
        case "cc-desc": return B.cc - A.cc;
        case "year-desc": return B.year - A.year;
        default: return A.order - B.order;
      }
    });
    sorted.forEach(function (el) { grid.appendChild(el); });
    count.textContent = "Найдено: " + shown + " " + plural(shown);
    empty.classList.toggle("is-on", shown === 0);
    chips.forEach(function (c) { c.setAttribute("aria-pressed", String(c.dataset.filterType === state.type)); });
    // Ссылка отражает фильтры (можно делиться)
    var p = new URLSearchParams();
    if (state.type !== "all") p.set("type", state.type);
    if (state.cond !== "all") p.set("condition", state.cond);
    if (q) p.set("q", q);
    if (state.sort !== "default") p.set("sort", state.sort);
    try { history.replaceState(null, "", location.pathname + (p.toString() ? "?" + p : "")); } catch (e) {}
  }

  chips.forEach(function (c) { c.addEventListener("click", function () { state.type = c.dataset.filterType; apply(true); }); });
  search.addEventListener("input", function () { state.q = search.value; apply(false); });
  cond.addEventListener("change", function () { state.cond = cond.value; apply(true); });
  sort.addEventListener("change", function () { state.sort = sort.value; apply(true); });
  reset.addEventListener("click", function () {
    state = { type: "all", cond: "all", q: "", sort: "default" };
    search.value = ""; cond.value = "all"; sort.value = "default"; apply(true);
  });

  // Начальное состояние из адреса (?type=sport&condition=used&q=yamaha&sort=price-asc)
  var qs = new URLSearchParams(location.search);
  if (qs.get("type")) state.type = qs.get("type");
  if (qs.get("condition")) { state.cond = qs.get("condition"); cond.value = state.cond; }
  if (qs.get("q")) { state.q = qs.get("q"); search.value = state.q; }
  if (qs.get("sort")) { state.sort = qs.get("sort"); sort.value = state.sort; }
  apply(false);
})();
