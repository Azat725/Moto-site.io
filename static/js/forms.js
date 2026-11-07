/* Формы заявок и отзывов: маска телефона, проверка, согласия, отправка на сервер.
   В демо-режиме (статический сайт на GitHub Pages) данные никуда не отправляются — посетителю это сообщается. */
(function () {
  "use strict";
  var body = document.body;
  var demo = body.dataset.mode !== "live";

  /* Номера РФ форматируем маской +7 (XXX) XXX-XX-XX; номера других стран (+375, +998…) оставляем как ввели. */
  function isForeign(value) { return /^\+(?!7)/.test(value.trim()); }
  function phoneOk(value) {
    var digits = value.replace(/\D/g, "").length;
    return isForeign(value) ? digits >= 11 && digits <= 15 : digits === 11;
  }

  function formatPhone(raw) {
    var d = raw.replace(/\D/g, "");
    if (d[0] === "8" || d[0] === "7") d = d.slice(1);
    d = d.slice(0, 10);
    var out = "+7";
    if (d.length) out += " (" + d.slice(0, 3);
    if (d.length >= 3) out += ")";
    if (d.length > 3) out += " " + d.slice(3, 6);
    if (d.length > 6) out += "-" + d.slice(6, 8);
    if (d.length > 8) out += "-" + d.slice(8, 10);
    return out;
  }
  document.querySelectorAll("[data-phone]").forEach(function (inp) {
    inp.addEventListener("input", function () {
      if (isForeign(inp.value)) return;
      inp.value = inp.value.replace(/\D/g, "").length ? formatPhone(inp.value) : "";
    });
    inp.addEventListener("focus", function () { if (!inp.value) inp.value = "+7 ("; });
    inp.addEventListener("blur", function () { if (inp.value.replace(/\D/g, "").length <= 1) inp.value = ""; });
  });

  function toast(msg) { if (window.IVAX && window.IVAX.toast) window.IVAX.toast(msg); }
  function mark(el, bad) {
    if (!el || !el.closest) return;
    var f = el.closest(".field, .check");
    if (f) f.classList.toggle("is-invalid", bad);
    el.setAttribute("aria-invalid", bad ? "true" : "false");
    var err = f && f.querySelector(".field__error");
    if (err) {
      if (!err.id) err.id = (el.id || el.name) + "-error";
      el.setAttribute("aria-describedby", err.id);
    }
  }

  function validate(form) {
    var bad = [];
    Array.prototype.forEach.call(form.querySelectorAll("[required]"), function (el) {
      var wrong = el.type === "checkbox" ? !el.checked : !el.value.trim() || (el.minLength > 0 && el.value.trim().length < el.minLength);
      if (el.matches("[data-phone]")) wrong = !phoneOk(el.value);
      mark(el, wrong);
      if (wrong) bad.push(el);
    });
    var consentErr = form.querySelector("[data-consent-error]");
    if (consentErr) consentErr.hidden = !(form.elements.consent && !form.elements.consent.checked);
    return bad;
  }

  function setStatus(form, ok, text) {
    var status = form.querySelector(".form-status");
    if (!status) return;
    status.className = "form-status " + (ok ? "is-ok" : "is-err");
    status.textContent = text;
  }

  function fieldErrors(form, fields) {
    Object.keys(fields || {}).forEach(function (name) { mark(form.elements[name], true); });
  }

  function submit(form, url, okText) {
    var btn = form.querySelector('button[type="submit"]');
    if (demo) {
      setStatus(form, true, "Демо-версия: форма проверена, но данные не отправлены. На рабочем сайте заявка уйдёт менеджеру.");
      toast("Демо: заявка не отправлена");
      return;
    }
    btn.disabled = true;
    fetch(url, { method: "POST", body: new URLSearchParams(new FormData(form)), headers: { Accept: "application/json" }, credentials: "same-origin" })
      .then(function (r) {
        var isJson = (r.headers.get("content-type") || "").indexOf("application/json") !== -1;
        if (!isJson) return { status: r.status, data: { success: false, error: "Ошибка сервера. Позвоните нам или попробуйте позже." } };
        return r.json().then(function (data) { return { status: r.status, data: data }; });
      })
      .then(function (res) {
        btn.disabled = false;
        if (res.data.success) {
          var extra = res.data.data && res.data.data.price_changed ? " Цена обновилась по текущему курсу — менеджер назовёт актуальную." : "";
          setStatus(form, true, okText + extra);
          form.reset();
          toast("Отправлено");
          return;
        }
        fieldErrors(form, res.data.fields);
        setStatus(form, false, res.data.error || "Не удалось отправить. Позвоните нам.");
      })
      .catch(function () { btn.disabled = false; setStatus(form, false, "Нет связи с сервером. Попробуйте позже или позвоните нам."); });
  }

  function bind(form, url, okText) {
    form.addEventListener("change", function (e) { if (e.target.closest(".is-invalid")) mark(e.target, false); });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (form.elements.website && form.elements.website.value) return;
      var bad = validate(form);
      if (bad.length) { bad[0].focus(); return; }
      submit(form, url, okText);
    });
  }

  document.querySelectorAll("form[data-lead-form]").forEach(function (form) {
    bind(form, body.dataset.leadUrl, "Спасибо! Заявка принята — менеджер свяжется с вами в рабочее время.");
  });
  document.querySelectorAll("form[data-review-form]").forEach(function (form) {
    bind(form, body.dataset.reviewUrl, "Спасибо! Отзыв появится на сайте после проверки.");
  });
})();
