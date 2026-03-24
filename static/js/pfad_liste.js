// pfad_liste.js – Loesch-Bestaetigung fuer Antrags-Pfade

document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-loeschen-form]").forEach(function (form) {
        form.addEventListener("submit", function (e) {
            var name = form.dataset.name;
            var anzahl = form.dataset.anzahl;
            var meldung = 'Pfad "' + name + '" wirklich loeschen?';
            if (anzahl > 0) {
                meldung += " Alle " + anzahl + " Einreichung" + (anzahl === "1" ? "" : "en") + " werden ebenfalls geloescht.";
            }
            if (!confirm(meldung)) {
                e.preventDefault();
            }
        });
    });
});
