/* Калькулятор платежа (аннуитет). Расчёт ориентировочный. */
(function () {
  "use strict";
  var fmt = function (n) { return Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ") + " ₽"; };
  var reduce = document.documentElement.classList.contains("reduce");

  document.querySelectorAll("[data-calc]").forEach(function (box) {
    var rate = parseFloat(box.getAttribute("data-rate")) || (window.IVAX_CONFIG || {}).calcRate || 19.9;
    var price = box.querySelector("[data-calc-price]"), down = box.querySelector("[data-calc-down]"), term = box.querySelector("[data-calc-term]");
    var outMonth = box.querySelector("[data-calc-month]"), outDown = box.querySelector("[data-calc-downsum]"),
        outLoan = box.querySelector("[data-calc-loan]"), outOver = box.querySelector("[data-calc-over]"), outRate = box.querySelector("[data-calc-rate]");
    var shownMonth = 0, raf = 0;

    // Подставляем цену из ?price= (например, со страницы модели)
    var qp = new URLSearchParams(location.search).get("price");
    if (qp && +qp >= +price.min && +qp <= +price.max) price.value = qp;

    function paintRange(input) {
      var p = ((input.value - input.min) / (input.max - input.min)) * 100;
      input.style.setProperty("--p", p + "%");
    }
    function animateMonth(to) {
      if (reduce) { outMonth.textContent = fmt(to); shownMonth = to; return; }
      cancelAnimationFrame(raf);
      var from = shownMonth, t0 = performance.now();
      (function step(now) {
        var p = Math.min(1, (now - t0) / 400), e = 1 - Math.pow(1 - p, 3);
        shownMonth = from + (to - from) * e; outMonth.textContent = fmt(shownMonth);
        if (p < 1) raf = requestAnimationFrame(step);
      })(t0);
    }
    function calc() {
      var cost = +price.value, d = +down.value, n = +term.value;
      var downSum = cost * d / 100, loan = cost - downSum, r = rate / 100 / 12;
      var monthly = loan <= 0 ? 0 : (r === 0 ? loan / n : loan * r / (1 - Math.pow(1 + r, -n)));
      var over = monthly * n - loan;
      box.querySelector('[data-out="price"]').textContent = fmt(cost);
      box.querySelector('[data-out="down"]').textContent = d + "%";
      box.querySelector('[data-out="term"]').textContent = n + " мес.";
      [price, down, term].forEach(paintRange);
      animateMonth(monthly);
      outDown.textContent = fmt(downSum); outLoan.textContent = fmt(loan);
      outOver.textContent = fmt(Math.max(0, over));
      outRate.textContent = String(rate).replace(".", ",") + "% годовых (условно)";
    }
    [price, down, term].forEach(function (i) { i.addEventListener("input", calc); });
    calc();
  });
})();
