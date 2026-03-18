/**
 * sicherheit_poller.js
 * Prueft alle 5 Sekunden ob ein AMOK- oder Brand-Alarm ausgeloest wurde.
 * Zeigt bei neuem Alarm ein Vollbild-Overlay mit Verhaltensregeln.
 * Wird fuer ALLE eingeloggten Nutzer geladen.
 */
document.addEventListener("DOMContentLoaded", function () {
    // Initialzustand aus data-Attributen lesen
    var amokWarAktiv  = document.body.dataset.amokBannerAktiv  === "true";
    var brandWarAktiv = document.body.dataset.brandBannerAktiv === "true";
    var overlayLaeuft = false;

    // ---------------------------------------------------------------------------
    // Alarmton
    // ---------------------------------------------------------------------------
    function spieleAmokAlarmton() {
        try {
            var ctx = new (window.AudioContext || window.webkitAudioContext)();
            var frequenzen = [1200, 800, 1200, 800, 1200, 800];
            frequenzen.forEach(function (freq, i) {
                var osc = ctx.createOscillator();
                var gain = ctx.createGain();
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.frequency.value = freq;
                osc.type = "sawtooth";
                gain.gain.setValueAtTime(0.5, ctx.currentTime + i * 0.2);
                gain.gain.exponentialRampToValueAtTime(
                    0.001, ctx.currentTime + i * 0.2 + 0.18
                );
                osc.start(ctx.currentTime + i * 0.2);
                osc.stop(ctx.currentTime + i * 0.2 + 0.19);
            });
        } catch (e) {}
    }

    function spieleBrandAlarmton() {
        try {
            var ctx = new (window.AudioContext || window.webkitAudioContext)();
            // Brand: langsames, tiefes Alarmsignal (DIN-Evakuierungshorn)
            var muster = [880, 0, 880, 0, 880, 660, 660, 0, 660];
            muster.forEach(function (freq, i) {
                if (freq === 0) { return; }
                var osc = ctx.createOscillator();
                var gain = ctx.createGain();
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.frequency.value = freq;
                osc.type = "square";
                gain.gain.setValueAtTime(0.4, ctx.currentTime + i * 0.25);
                gain.gain.exponentialRampToValueAtTime(
                    0.001, ctx.currentTime + i * 0.25 + 0.22
                );
                osc.start(ctx.currentTime + i * 0.25);
                osc.stop(ctx.currentTime + i * 0.25 + 0.23);
            });
        } catch (e) {}
    }

    // ---------------------------------------------------------------------------
    // Overlay-Keyframes (einmalig einfuegen)
    // ---------------------------------------------------------------------------
    function sicherstelleKeyframes(id, css) {
        if (!document.getElementById(id)) {
            var style = document.createElement("style");
            style.id = id;
            style.textContent = css;
            document.head.appendChild(style);
        }
    }

    // ---------------------------------------------------------------------------
    // AMOK-Overlay
    // ---------------------------------------------------------------------------
    function zeigeAmokOverlay(ort, zeit) {
        if (overlayLaeuft) { return; }
        overlayLaeuft = true;
        spieleAmokAlarmton();

        sicherstelleKeyframes("amok-overlay-style",
            "@keyframes amok-overlay-puls {" +
            "  0%, 100% { background: #8b0000; }" +
            "  50% { background: #cc0000; }" +
            "}"
        );

        var overlay = document.createElement("div");
        overlay.style.cssText = [
            "position:fixed", "inset:0", "background:#8b0000", "color:#fff",
            "display:flex", "flex-direction:column", "align-items:center",
            "justify-content:center", "z-index:99999", "font-family:inherit",
            "padding:2rem 1rem", "overflow-y:auto",
            "animation:amok-overlay-puls 1.5s infinite",
        ].join(";");

        var ortAnzeige  = ort  || "unbekannt";
        var zeitAnzeige = zeit ? (zeit + " Uhr") : "";

        overlay.innerHTML = (
            "<div style='font-size:2.5rem;font-weight:900;letter-spacing:0.06em;" +
            "text-align:center;border:4px solid #fff;padding:0.5rem 2rem;" +
            "border-radius:4px;margin-bottom:1rem;'>" +
            "!!! AMOK-ALARM !!!" +
            "</div>" +
            "<div style='font-size:1.1rem;margin-bottom:2rem;text-align:center;opacity:0.9;'>" +
            "Ort: <strong>" + ortAnzeige + "</strong>" +
            (zeitAnzeige ? " &ndash; " + zeitAnzeige : "") +
            "</div>" +
            "<div style='max-width:600px;width:100%;'>" +
            _regelBlock("1. LAUFEN",
                "Verlassen Sie das Gebaeude sofort. Tueren schliessen. Nicht zurueckkehren.") +
            _regelBlock("2. VERSTECKEN",
                "Tuer absperren. Licht aus. Handy lautlos. Nicht auf Klopfen reagieren.") +
            _regelBlock("3. KAEMPFEN",
                "Nur als letztes Mittel. Laerm machen. Gemeinsam agieren.") +
            "<div style='background:rgba(255,255,255,0.12);border:3px solid #fff;" +
            "border-radius:5px;padding:0.8rem 1rem;text-align:center;'>" +
            "<div style='font-size:0.9rem;'>Notruf &ndash; sobald sicher moeglich</div>" +
            "<div style='font-size:3rem;font-weight:900;letter-spacing:0.1em;'>110</div>" +
            "<div style='font-size:0.85rem;'>Security</div>" +
            "</div></div>" +
            "<div style='font-size:0.9rem;margin-top:2rem;opacity:0.75;'>Seite wird aktualisiert&hellip;</div>"
        );

        document.body.appendChild(overlay);
        setTimeout(function () { window.location.assign(window.location.href); }, 30000);
    }

    // ---------------------------------------------------------------------------
    // Brand-Evakuierungs-Overlay
    // ---------------------------------------------------------------------------
    function zeigeBrandOverlay(ort, zeit) {
        if (overlayLaeuft) { return; }
        overlayLaeuft = true;
        spieleBrandAlarmton();

        sicherstelleKeyframes("brand-overlay-style",
            "@keyframes brand-overlay-puls {" +
            "  0%, 100% { background: #7c2d12; }" +
            "  50% { background: #c2410c; }" +
            "}"
        );

        var overlay = document.createElement("div");
        overlay.style.cssText = [
            "position:fixed", "inset:0", "background:#7c2d12", "color:#fed7aa",
            "display:flex", "flex-direction:column", "align-items:center",
            "justify-content:center", "z-index:99999", "font-family:inherit",
            "padding:2rem 1rem", "overflow-y:auto",
            "animation:brand-overlay-puls 2s infinite",
        ].join(";");

        var ortAnzeige  = ort  || "unbekannt";
        var zeitAnzeige = zeit ? (zeit + " Uhr") : "";

        overlay.innerHTML = (
            "<div style='font-size:2.5rem;font-weight:900;letter-spacing:0.06em;" +
            "text-align:center;border:4px solid #fed7aa;padding:0.5rem 2rem;" +
            "border-radius:4px;margin-bottom:1rem;color:#fff;'>" +
            "BRAND-ALARM" +
            "</div>" +
            "<div style='font-size:1.1rem;margin-bottom:2rem;text-align:center;opacity:0.9;'>" +
            "Ort: <strong>" + ortAnzeige + "</strong>" +
            (zeitAnzeige ? " &ndash; " + zeitAnzeige : "") +
            "</div>" +
            "<div style='max-width:600px;width:100%;'>" +
            _regelBlockBrand("1. GEBAEUDE VERLASSEN",
                "Sofort alle Raeume verlassen. Aufzug NICHT benutzen. Tueren schliessen.") +
            _regelBlockBrand("2. SAMMELPLATZ",
                "Zum ausgewiesenen Sammelplatz begeben. Alle Kollegen mitnehmen.") +
            _regelBlockBrand("3. NICHT ZURUECK",
                "Nichts holen. Warten bis Entwarnung durch Security.") +
            "</div>" +
            "<div style='font-size:0.9rem;margin-top:2rem;opacity:0.75;color:#fed7aa;'>Seite wird aktualisiert&hellip;</div>"
        );

        document.body.appendChild(overlay);
        setTimeout(function () { window.location.assign(window.location.href); }, 30000);
    }

    // ---------------------------------------------------------------------------
    // Hilfsbausteine fuer Overlay-HTML
    // ---------------------------------------------------------------------------
    function _regelBlock(titel, text) {
        return (
            "<div style='background:rgba(0,0,0,0.3);border-left:5px solid #fff;" +
            "border-radius:3px;padding:0.8rem 1.2rem;margin-bottom:0.8rem;'>" +
            "<div style='font-size:1.3rem;font-weight:900;'>" + titel + "</div>" +
            "<div style='font-size:0.95rem;opacity:0.92;'>" + text + "</div>" +
            "</div>"
        );
    }

    function _regelBlockBrand(titel, text) {
        return (
            "<div style='background:rgba(0,0,0,0.25);border-left:5px solid #fed7aa;" +
            "border-radius:3px;padding:0.8rem 1.2rem;margin-bottom:0.8rem;'>" +
            "<div style='font-size:1.3rem;font-weight:900;color:#fff;'>" + titel + "</div>" +
            "<div style='font-size:0.95rem;opacity:0.92;color:#fed7aa;'>" + text + "</div>" +
            "</div>"
        );
    }

    // ---------------------------------------------------------------------------
    // ---------------------------------------------------------------------------
    // Branderkunder-Overlay
    // ---------------------------------------------------------------------------
    function zeigeBranderkunderOverlay(ort, tokenUrl) {
        if (overlayLaeuft) { return; }
        overlayLaeuft = true;
        spieleBrandAlarmton();

        sicherstelleKeyframes("erkunder-overlay-style",
            "@keyframes erkunder-overlay-puls {" +
            "  0%, 100% { background: #78350f; }" +
            "  50% { background: #b45309; }" +
            "}"
        );

        var overlay = document.createElement("div");
        overlay.style.cssText = [
            "position:fixed", "inset:0", "background:#78350f", "color:#fef3c7",
            "display:flex", "flex-direction:column", "align-items:center",
            "justify-content:center", "z-index:99999", "font-family:inherit",
            "padding:2rem 1rem", "overflow-y:auto",
            "animation:erkunder-overlay-puls 2s infinite",
        ].join(";");

        overlay.innerHTML = (
            "<div style='font-size:2rem;font-weight:900;letter-spacing:0.06em;" +
            "text-align:center;border:4px solid #fef3c7;padding:0.5rem 2rem;" +
            "border-radius:4px;margin-bottom:1rem;color:#fff;'>" +
            "BRANDMELDUNG – ERKUNDEN" +
            "</div>" +
            "<div style='font-size:1.1rem;margin-bottom:2rem;text-align:center;'>" +
            "Gemeldeter Ort: <strong style='color:#fff;'>" + (ort || "unbekannt") + "</strong>" +
            "</div>" +
            "<div style='max-width:500px;width:100%;'>" +
            "<div style='background:rgba(0,0,0,0.3);border-left:5px solid #fef3c7;" +
            "border-radius:3px;padding:0.8rem 1.2rem;margin-bottom:1rem;'>" +
            "<div style='font-size:1.2rem;font-weight:900;color:#fff;'>Ihr Auftrag</div>" +
            "<div style='font-size:0.95rem;'>Brandort aufsuchen und Rueckmeldung geben.</div>" +
            "</div>" +
            "<a href='" + tokenUrl + "' style='display:block;background:#d97706;" +
            "color:#fff;text-align:center;padding:1rem 2rem;border-radius:6px;" +
            "font-size:1.2rem;font-weight:900;text-decoration:none;margin-top:1rem;'>" +
            "Zur Rueckmeldung &rarr;" +
            "</a>" +
            "</div>" +
            "<div style='font-size:0.85rem;margin-top:2rem;opacity:0.7;'>Seite wird aktualisiert&hellip;</div>"
        );

        document.body.appendChild(overlay);
        setTimeout(function () { window.location.assign(tokenUrl); }, 8000);
    }

    // ---------------------------------------------------------------------------
    // Polling
    // ---------------------------------------------------------------------------
    // Auf Sicherheits-Detailseiten keine Evakuierungs-Overlays zeigen –
    // Security/AS verwalten den Alarm, statt zu evakuieren.
    var aufSicherheitsSeite = window.location.pathname.indexOf("/sicherheit/") === 0;

    function pruefeAmokStatus() {
        fetch("/sicherheit/status.json")
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!amokWarAktiv && data.amok_aktiv && !aufSicherheitsSeite) {
                    // Neuer AMOK-Alarm – Overlay zeigen (nicht auf Sicherheits-Seiten)
                    zeigeAmokOverlay(data.ort, data.zeit);
                } else if (amokWarAktiv && !data.amok_aktiv) {
                    // Alarm wurde beendet – Seite neu laden damit Banner verschwindet
                    window.location.assign(window.location.href);
                }
                amokWarAktiv = data.amok_aktiv;
            })
            .catch(function () {});
    }

    function pruefeeBrandStatus() {
        fetch("/sicherheit/brand/status.json")
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!brandWarAktiv && data.brand_aktiv && !aufSicherheitsSeite) {
                    // Neuer Brand-Alarm – Overlay zeigen (nicht auf Sicherheits-Seiten)
                    zeigeBrandOverlay(data.ort, data.zeit);
                } else if (brandWarAktiv && !data.brand_aktiv) {
                    // Entwarnung – Seite neu laden damit Banner verschwindet
                    window.location.assign(window.location.href);
                }
                brandWarAktiv = data.brand_aktiv;
            })
            .catch(function () {});
    }

    function pruefeErkunderStatus() {
        fetch("/sicherheit/brand/erkunder-status.json")
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.erkunder_alarm) { return; }
                // Security/AS direkt zur Einsatzleitstelle weiterleiten
                if (data.ist_security) {
                    // Auf allen Brand-Unterseiten nicht weiterleiten
                    var pfad = window.location.pathname;
                    if (pfad.indexOf("/sicherheit/brand/") === 0) {
                        return;
                    }
                    window.location.assign(data.token_url);
                    return;
                }
                zeigeBranderkunderOverlay(data.ort, data.token_url);
            })
            .catch(function () {});
    }

    // ---------------------------------------------------------------------------
    // Security-Alarm-Overlay (nur fuer Security-Personal)
    // ---------------------------------------------------------------------------
    // Bereits gesehene Alarme aus sessionStorage laden (bleibt bei Navigation erhalten)
    var gezeigteSecurityAlarme = {};
    try {
        var gespeichert = sessionStorage.getItem("prima_security_alarme_gesehen");
        if (gespeichert) { gezeigteSecurityAlarme = JSON.parse(gespeichert); }
    } catch (e) {}

    function markiereAlsGesehen(alarmId) {
        gezeigteSecurityAlarme[alarmId] = true;
        try { sessionStorage.setItem("prima_security_alarme_gesehen", JSON.stringify(gezeigteSecurityAlarme)); } catch (e) {}
    }

    function schliesseSecurityOverlay(overlayEl, alarmId) {
        if (overlayEl) { overlayEl.remove(); }
        overlayLaeuft = false;
        if (alarmId) { markiereAlsGesehen(alarmId); }
    }

    function zeigeSecurityOverlay(alarm) {
        if (overlayLaeuft) { return; }

        // Kein Overlay wenn wir bereits auf einer Seite dieses Alarms sind.
        // Fuer Brand-Alarme: alle Unterseiten (/brand/12/, /brand/12/security/ usw.)
        var aktuellePfad = window.location.pathname;
        var unterdrucken = false;
        if (alarm.typ === "brand") {
            var pk = alarm.id.replace("brand-", "");
            unterdrucken = aktuellePfad.indexOf("/sicherheit/brand/" + pk + "/") === 0;
        } else {
            unterdrucken = (aktuellePfad === alarm.detail_url ||
                            aktuellePfad.indexOf(alarm.detail_url) === 0);
        }
        if (unterdrucken) {
            markiereAlsGesehen(alarm.id);  // auf der Alarm-Seite sein = gesehen
            return;
        }

        overlayLaeuft = true;

        var istAmok = (alarm.typ === "amok");
        var hintergrund = istAmok ? "#7f1d1d" : "#1a0a00";
        var rahmen     = istAmok ? "#ef4444"  : "#ea580c";
        var textfarbe  = istAmok ? "#fecaca"  : "#fed7aa";

        var overlay = document.createElement("div");
        overlay.id = "security-overlay-" + alarm.id;
        overlay.style.cssText = [
            "position:fixed", "inset:0", "background:" + hintergrund,
            "color:" + textfarbe,
            "display:flex", "flex-direction:column", "align-items:center",
            "justify-content:center", "z-index:99998", "font-family:inherit",
            "padding:2rem 1rem", "overflow-y:auto",
            "border:4px solid " + rahmen,
        ].join(";");

        overlay.innerHTML = (
            "<div style='font-size:2rem;font-weight:900;letter-spacing:0.06em;" +
            "text-align:center;padding:0.5rem 2rem;border:3px solid " + rahmen + ";" +
            "border-radius:6px;margin-bottom:1rem;color:#fff;'>" +
            alarm.status_label +
            "</div>" +
            "<div style='font-size:1.1rem;margin-bottom:0.5rem;text-align:center;'>" +
            "Ort: <strong style='color:#fff;'>" + alarm.ort + "</strong>" +
            "</div>" +
            "<div style='font-size:0.9rem;margin-bottom:2rem;opacity:0.8;'>" +
            "Security-Meldung – sofortige Reaktion erforderlich" +
            "</div>" +
            "<div style='display:flex;gap:1rem;flex-wrap:wrap;justify-content:center;'>" +
            "<a id='sec-detail-btn-" + alarm.id + "' href='" + alarm.detail_url + "' " +
            "style='display:inline-block;background:" + rahmen + ";color:#fff;" +
            "text-align:center;padding:0.9rem 2rem;border-radius:6px;" +
            "font-size:1.1rem;font-weight:900;text-decoration:none;'>" +
            "Zur Detailseite &rarr;" +
            "</a>" +
            "<button type='button' data-action='schliessen' " +
            "style='background:transparent;color:" + textfarbe + ";" +
            "border:1px solid " + textfarbe + ";" +
            "padding:0.9rem 2rem;border-radius:6px;font-size:1rem;cursor:pointer;'>" +
            "Schliessen" +
            "</button>" +
            "</div>"
        );

        document.body.appendChild(overlay);

        // Schliessen-Button via Event Delegation auf dem Overlay selbst
        overlay.addEventListener("click", function (e) {
            if (e.target.closest("[data-action='schliessen']")) {
                schliesseSecurityOverlay(overlay, alarm.id);
            }
        });

        // Nach 30 Sekunden automatisch schliessen (ohne als "gesehen" zu markieren)
        setTimeout(function () { schliesseSecurityOverlay(overlay, null); }, 30000);
    }

    function pruefeSecurityAlarme() {
        if (document.body.dataset.istSecurityZugang !== "true") { return; }
        fetch("/sicherheit/security-alarm-status.json")
            .then(function (r) { return r.json(); })
            .then(function (data) {
                var aktuelleIds = {};
                (data.alarme || []).forEach(function (alarm) {
                    aktuelleIds[alarm.id] = true;
                    if (!gezeigteSecurityAlarme[alarm.id]) {
                        gezeigteSecurityAlarme[alarm.id] = true;
                        zeigeSecurityOverlay(alarm);
                    }
                });
                // Geschlossene Alarme aus Gedaechtnis + sessionStorage entfernen
                Object.keys(gezeigteSecurityAlarme).forEach(function (id) {
                    if (!aktuelleIds[id]) {
                        delete gezeigteSecurityAlarme[id];
                        try { sessionStorage.setItem("prima_security_alarme_gesehen", JSON.stringify(gezeigteSecurityAlarme)); } catch (e) {}
                    }
                });
            })
            .catch(function () {});
    }

    // Sofort beim Laden pruefen
    pruefeAmokStatus();
    pruefeeBrandStatus();
    pruefeErkunderStatus();
    pruefeSecurityAlarme();

    // Danach alle 5 Sekunden wiederholen
    setInterval(pruefeAmokStatus,      5000);
    setInterval(pruefeeBrandStatus,    5000);
    setInterval(pruefeErkunderStatus,  5000);
    setInterval(pruefeSecurityAlarme,  5000);
});
