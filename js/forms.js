/* Формы заявок: маска телефона, валидация, обязательное согласие, honeypot.
   Без formEndpoint в js/config.js форма работает в ДЕМО-режиме (данные никуда не отправляются). */
(function () {
  "use strict";
  var CFG = window.IVAX_CONFIG || {};

  /* Маска +7 (XXX) XXX-XX-XX */
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
      var digits = inp.value.replace(/\D/g, "");
      inp.value = digits.length ? formatPhone(inp.value) : "";
    });
    inp.addEventListener("focus", function () { if (!inp.value) inp.value = "+7 ("; });
    inp.addEventListener("blur", function () { if (inp.value.replace(/\D/g, "").length <= 1) inp.value = ""; });
  });

  function setInvalid(field, bad) { if (field) field.classList.toggle("is-invalid", bad); }

  document.querySelectorAll("form[data-form]").forEach(function (form) {
    var status = form.querySelector(".form-status");
    var consent = form.elements.consent;
    var consentWrap = consent.closest(".check");
    var consentErr = form.querySelector("[data-consent-error]");
    var submitBtn = form.querySelector('button[type="submit"]');

    consent.addEventListener("change", function () {
      consentWrap.classList.toggle("is-invalid", !consent.checked);
      if (consentErr) consentErr.style.display = consent.checked ? "none" : "block";
    });

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      status.className = "form-status"; status.textContent = "";
      if (form.elements.website && form.elements.website.value) return; // honeypot: бот

      var name = form.elements.name, phone = form.elements.phone, ok = true;
      var nameBad = name.value.trim().length < 2;
      var phoneBad = phone.value.replace(/\D/g, "").length !== 11;
      setInvalid(name.closest(".field"), nameBad); setInvalid(phone.closest(".field"), phoneBad);
      if (nameBad || phoneBad) ok = false;
      if (!consent.checked) {
        ok = false; consentWrap.classList.add("is-invalid");
        if (consentErr) consentErr.style.display = "block";
      }
      if (!ok) {
        var first = form.querySelector(".is-invalid input, .is-invalid select, .check.is-invalid input");
        if (first) first.focus();
        return;
      }

      var data = {
        subject: form.elements.subject.value,
        name: name.value.trim(),
        phone: phone.value,
        model: form.elements.model ? form.elements.model.value : "",
        message: form.elements.message ? form.elements.message.value.trim() : "",
        way: (form.querySelector('input[name="way"]:checked') || {}).value || "call",
        consent: true,
        consentAt: new Date().toISOString(),
        page: location.pathname,
        ts: Date.now()
      };

      submitBtn.disabled = true;
      var done = function (okMsg, isDemo) {
        submitBtn.disabled = false;
        status.className = "form-status is-ok";
        status.textContent = okMsg;
        if (!isDemo) form.reset();
        if (window.IVAX && window.IVAX.toast) window.IVAX.toast(isDemo ? "Демо-режим: заявка не отправлена" : "Заявка отправлена");
        status.scrollIntoView({ block: "nearest", behavior: "smooth" });
      };
      var fail = function () {
        submitBtn.disabled = false;
        status.className = "form-status is-err";
        status.textContent = "Не удалось отправить заявку. Позвоните нам или попробуйте позже.";
      };

      if (!CFG.formEndpoint) {
        // ДЕМО: честно сообщаем, что заявка не ушла
        setTimeout(function () {
          done("Демо-режим: форма работает, но заявка никуда не отправлена — подключите обработчик (formEndpoint в js/config.js).", true);
        }, 500);
        return;
      }
      fetch(CFG.formEndpoint, { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify(data) })
        .then(function (r) { if (!r.ok) throw new Error(r.status); done("Спасибо! Заявка принята — мы свяжемся с вами в рабочее время.", false); })
        .catch(fail);
    });
  });
})();
