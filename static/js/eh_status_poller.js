/**
 * EH-Status-Poller: Prueft alle 5 Sekunden ob ein Erste-Hilfe-Einsatz
 * gestartet wurde und zeigt einen Alarm-Banner + laedt die Seite neu.
 * Wird nur fuer EH-Verantwortliche und Ersthelfer geladen.
 */
document.addEventListener("DOMContentLoaded", function () {
    // Initialzustand aus Data-Attribut lesen (unabhaengig von Banner-Sichtbarkeit)
    var warAktiv = document.body.dataset.ehBannerAktiv === "true";
    var alarmLaeuft = false; // Verhindert doppelten Aufruf

    function spieleAlarmton() {
        // Kurzer Alarmton per Web Audio API (kein externer Datei-Aufruf)
        try {
            var ctx = new (window.AudioContext || window.webkitAudioContext)();
            [880, 660, 880, 660].forEach(function (freq, i) {
                var osc = ctx.createOscillator();
                var gain = ctx.createGain();
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.frequency.value = freq;
                osc.type = "square";
                gain.gain.setValueAtTime(0.4, ctx.currentTime + i * 0.25);
                gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + i * 0.25 + 0.22);
                osc.start(ctx.currentTime + i * 0.25);
                osc.stop(ctx.currentTime + i * 0.25 + 0.23);
            });
        } catch (e) { /* Audio nicht verfuegbar – kein Fehler */ }
    }

    function zeigeAlarmUndLade(ort, zeit) {
        if (alarmLaeuft) { return; }
        alarmLaeuft = true;

        spieleAlarmton();

        // Vollbild-Alert erstellen
        var overlay = document.createElement("div");
        overlay.id = "eh-alarm-overlay";
        overlay.style.cssText = [
            "position:fixed",
            "inset:0",
            "background:#dc3545",
            "color:#fff",
            "display:flex",
            "flex-direction:column",
            "align-items:center",
            "justify-content:center",
            "z-index:99999",
            "font-family:inherit",
            "animation:eh-puls 1.6s infinite",
        ].join(";");

        overlay.innerHTML = (
            "<div style='font-size:3rem;font-weight:900;letter-spacing:0.05em;text-align:center;'>" +
            "!!! ERSTE HILFE ALARM !!!" +
            "</div>" +
            "<div style='font-size:1.5rem;margin-top:1rem;text-align:center;'>" +
            "Einsatzort: <strong>" + ort + "</strong> &ndash; Alarmzeit: <strong>" + zeit + " Uhr</strong>" +
            "</div>" +
            "<div style='font-size:1rem;margin-top:2rem;opacity:0.85;'>Seite wird aktualisiert&hellip;</div>"
        );
        document.body.appendChild(overlay);

        // Nach 3 Sekunden Seite neu laden damit Lauftext erscheint
        setTimeout(function () {
            window.location.assign(window.location.href);
        }, 3000);
    }

    function pruefeStatus() {
        fetch("/ersthelfe/status.json")
            .then(function (r) { return r.json(); })
            .then(function (data) {
                // Nur reagieren wenn Einsatz NEU gestartet wurde
                if (!warAktiv && data.aktiv) {
                    zeigeAlarmUndLade(data.ort, data.zeit);
                }
                warAktiv = data.aktiv;
            })
            .catch(function () {}); // Netzwerkfehler stillschweigend ignorieren
    }

    // Sofort beim Laden pruefen (kein initialer Delay)
    pruefeStatus();

    // Danach alle 5 Sekunden wiederholen
    setInterval(pruefeStatus, 5000);
});
