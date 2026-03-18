/**
 * brand_security.js
 * Bestaetigung fuer Security-Review-Buttons (data-confirm).
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
