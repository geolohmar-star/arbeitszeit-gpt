document.addEventListener("DOMContentLoaded", function () {
    // Lauftext-Banner ausblenden – wer die Vorfall-Seite sieht braucht ihn nicht
    var banner = document.querySelector(".eh-einsatz-banner");
    if (banner) { banner.style.display = "none"; }

    var btn = document.getElementById("btn-autorefresh");
    if (!btn) return;

    var INTERVALL = 10; // Sekunden
    var countdown = INTERVALL;

    function formatzeit(sek) {
        var m = Math.floor(sek / 60);
        var s = sek % 60;
        return (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s;
    }

    function countdownTick() {
        countdown -= 1;
        if (countdown <= 0) {
            window.location.assign(window.location.href);
        } else {
            btn.textContent = "\u21BB Jetzt aktualisieren (" + formatzeit(countdown) + ")";
        }
    }

    // Countdown laeuft immer im Hintergrund und aktualisiert automatisch
    btn.textContent = "\u21BB Jetzt aktualisieren (" + formatzeit(countdown) + ")";
    btn.classList.remove("btn-outline-secondary");
    btn.classList.add("btn-warning");
    setInterval(countdownTick, 1000);
});
