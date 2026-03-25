// confirm_forms.js – Globaler Bestaetigung-Handler fuer Loeschen-Formulare
// Ersetzt onsubmit="return confirm(...)" durch CSP-konformes data-confirm-Attribut

document.addEventListener("DOMContentLoaded", function () {
    document.body.addEventListener("submit", function (e) {
        var form = e.target;
        var meldung = form.dataset.confirm;
        if (meldung && !confirm(meldung)) {
            e.preventDefault();
        }
    });
});
