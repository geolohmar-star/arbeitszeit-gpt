/**
 * brand_detail.js
 * Auto-Refresh Countdown fuer aktive Brandalarm-Detailseiten.
 */
document.addEventListener("DOMContentLoaded", function () {

    // Bestaetigung fuer Formular-Buttons mit data-confirm-Attribut
    document.body.addEventListener("click", function (e) {
        var btn = e.target.closest("button[data-confirm]");
        if (!btn) return;
        var meldung = btn.getAttribute("data-confirm");
        if (!window.confirm(meldung)) {
            e.preventDefault();
        }
    });

    var btn = document.getElementById("btn-autorefresh");
    if (!btn) return;

    var INTERVALL = 10; // Sekunden

    var countdown = INTERVALL;

    function formatzeit(sek) {
        var m = Math.floor(sek / 60);
        var s = sek % 60;
        return (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s;
    }

    function tick() {
        countdown -= 1;
        if (countdown <= 0) {
            window.location.assign(window.location.href);
        } else {
            btn.textContent = "\u21BB Aktualisierung in " + formatzeit(countdown);
        }
    }

    btn.textContent = "\u21BB Aktualisierung in " + formatzeit(countdown);
    btn.classList.remove("btn-outline-secondary");
    btn.classList.add("btn-warning");
    setInterval(tick, 1000);
});
