/**
 * sicherheit_dashboard.js
 * Bestaetigung fuer Buttons mit data-confirm-Attribut im Sicherheits-Dashboard.
 */
document.addEventListener("DOMContentLoaded", function () {
    document.body.addEventListener("click", function (e) {
        var btn = e.target.closest("button[data-confirm]");
        if (!btn) return;
        var meldung = btn.getAttribute("data-confirm");
        if (!window.confirm(meldung)) {
            e.preventDefault();
        }
    });
});
