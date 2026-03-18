/**
 * brand_einsatz.js
 * Auto-Refresh fuer die Einsatzleitstelle – Countdown-Button alle 10 Sekunden,
 * dann vollstaendiger Seitenreload (kein AJAX-Polling, kein Flackern).
 * Identisches Prinzip wie eh_vorfall_detail.js.
 */
document.addEventListener("DOMContentLoaded", function () {

    // data-confirm Handler fuer Formular-Buttons
    document.body.addEventListener("click", function (e) {
        var btn = e.target.closest("button[data-confirm]");
        if (!btn) return;
        if (!window.confirm(btn.getAttribute("data-confirm"))) {
            e.preventDefault();
        }
    });

    // Auto-Refresh-Button (nur auf aktiven Alarmen vorhanden)
    var btn = document.getElementById("btn-autorefresh");
    if (!btn) { return; }

    var INTERVALL = 10;
    var countdown = INTERVALL;

    function formatzeit(sek) {
        return sek + "s";
    }

    function countdownTick() {
        countdown -= 1;
        if (countdown <= 0) {
            window.location.assign(window.location.href);
        } else {
            btn.textContent = "\u21BB Aktualisieren (" + formatzeit(countdown) + ")";
        }
    }

    btn.textContent = "\u21BB Aktualisieren (" + formatzeit(countdown) + ")";
    setInterval(countdownTick, 1000);
});
