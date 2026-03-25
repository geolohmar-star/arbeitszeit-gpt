// meine_antraege.js – Bestaetigung vor dem Loeschen einer Antragssitzung

document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-confirm]").forEach(function (btn) {
        btn.addEventListener("click", function (e) {
            if (!window.confirm(btn.dataset.confirm)) {
                e.preventDefault();
            }
        });
    });
});
