/**
 * datensicherung.js
 * Bestaetigung vor Backup und Restore-Test.
 * Buttons werden waehrend laufender Vorgaenge deaktiviert.
 */
document.addEventListener("DOMContentLoaded", function () {
    var formBackup  = document.getElementById("form-backup");
    var formRestore = document.getElementById("form-restore");
    var btnBackup   = document.getElementById("btn-backup");
    var btnRestore  = document.getElementById("btn-restore");

    if (formBackup) {
        formBackup.addEventListener("submit", function (e) {
            if (!confirm("Jetzt einen Datenbank-Dump erstellen?")) {
                e.preventDefault();
            } else {
                if (btnBackup) {
                    btnBackup.disabled = true;
                    btnBackup.textContent = "Laeuft...";
                }
            }
        });
    }

    if (formRestore) {
        formRestore.addEventListener("submit", function (e) {
            if (!confirm(
                "Restore-Test starten?\n\n" +
                "Es wird eine temporaere Datenbank angelegt, der letzte Dump " +
                "eingespielt und anschliessend wieder geloescht.\n" +
                "Produktionsdaten werden NICHT veraendert."
            )) {
                e.preventDefault();
            } else {
                if (btnRestore) {
                    btnRestore.disabled = true;
                    btnRestore.textContent = "Laeuft...";
                }
            }
        });
    }

    // Buttons nach HTMX-Reload wieder aktivieren falls kein Vorgang mehr laeuft
    document.body.addEventListener("htmx:afterSwap", function (e) {
        if (e.detail.target && e.detail.target.id === "dynbereich") {
            var spinner = e.detail.target.querySelector(".spinner-border");
            if (!spinner) {
                // Kein laufender Vorgang mehr
                if (btnBackup)  { btnBackup.disabled  = false; btnBackup.textContent  = "Backup jetzt erstellen"; }
                if (btnRestore) { btnRestore.disabled = false; btnRestore.textContent = "Restore-Test durchfuehren"; }
            }
        }
    });
});
