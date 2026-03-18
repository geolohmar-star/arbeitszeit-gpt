/**
 * eh_alarm_modal.js
 * Steuert den 2-Schritt-Erste-Hilfe-Alarm-Dialog.
 * Schritt 1: Bestaetigung – Schritt 2: Ort eingeben
 */
document.addEventListener("DOMContentLoaded", function () {
    var weiterBtn = document.getElementById("eh-weiter-btn");
    var schritt1 = document.getElementById("eh-schritt-1");
    var schritt2 = document.getElementById("eh-schritt-2");
    var modal = document.getElementById("ehAlarmModal");

    if (!weiterBtn || !schritt1 || !schritt2 || !modal) {
        return;
    }

    // Schritt 1 → Schritt 2 bei Klick auf "Ja – Alarm ausloesen"
    weiterBtn.addEventListener("click", function () {
        schritt1.style.display = "none";
        schritt2.style.display = "";
        var ortInput = document.getElementById("eh-ort");
        if (ortInput) {
            ortInput.focus();
        }
    });

    // Bei Modal-Schliessen immer auf Schritt 1 zuruecksetzen
    modal.addEventListener("hidden.bs.modal", function () {
        schritt1.style.display = "";
        schritt2.style.display = "none";
    });
});
