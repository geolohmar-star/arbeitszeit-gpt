/**
 * sos_modal.js
 * Steuert das unified SOS-Modal mit 5 Screens:
 *   Screen 0:  Auswahl (EH / AMOK / Stiller Alarm / Brand)
 *   Screen 1a: Erste-Hilfe Flow (Schritt 1 + 2)
 *   Screen 1b: AMOK-Bestaetigungsflow
 *   Screen 1c: Stiller Alarm (fetch()-POST, keine Seitenneuladung)
 *   Screen 1d: Brandalarm (FEUER-Eingabe + optionaler Ort)
 */
document.addEventListener("DOMContentLoaded", function () {
    // Screen-Elemente
    var screen0  = document.getElementById("sos-screen-0");
    var screen1a = document.getElementById("sos-screen-1a");
    var screen1b = document.getElementById("sos-screen-1b");
    var screen1c = document.getElementById("sos-screen-1c");
    var screen1d = document.getElementById("sos-screen-1d");

    if (!screen0) {
        return; // SOS-Modal nicht vorhanden (z.B. nicht eingeloggt)
    }

    var modal = document.getElementById("sosModal");

    // EH-Schritt-1/2 innerhalb von 1a
    var ehSchritt1  = document.getElementById("eh-schritt-1");
    var ehSchritt2  = document.getElementById("eh-schritt-2");
    var ehWeiterBtn = document.getElementById("eh-weiter-btn");

    // AMOK-Bestaetigung
    var amokBestaetigungInput = document.getElementById("amok-bestaetigung");
    var amokSubmitBtn         = document.getElementById("amok-submit-btn");
    var amokFehler            = document.getElementById("amok-bestaetigung-fehler");

    // Brand-Bestaetigung
    var brandBestaetigungInput = document.getElementById("brand-bestaetigung");
    var brandSubmitBtn         = document.getElementById("brand-submit-btn");
    var brandFehler            = document.getElementById("brand-bestaetigung-fehler");

    // Hilfsfunktion: alle Screens ausblenden
    function alleScreensAusblenden() {
        screen0.style.display  = "none";
        screen1a.style.display = "none";
        screen1b.style.display = "none";
        screen1c.style.display = "none";
        if (screen1d) { screen1d.style.display = "none"; }
    }

    function zeigeScreen(screen) {
        alleScreensAusblenden();
        screen.style.display = "";
    }

    // ---------------------------------------------------------------------------
    // Screen 0: Kachel-Buttons
    // ---------------------------------------------------------------------------
    document.getElementById("sos-btn-eh").addEventListener("click", function () {
        zeigeScreen(screen1a);
    });

    document.getElementById("sos-btn-amok").addEventListener("click", function () {
        zeigeScreen(screen1b);
    });

    document.getElementById("sos-btn-still").addEventListener("click", function () {
        // Ort-Feld zuruecksetzen
        var ortFeld = document.getElementById("still-ort");
        if (ortFeld) { ortFeld.value = ""; }
        zeigeScreen(screen1c);
    });

    var brandBtn = document.getElementById("sos-btn-brand");
    if (brandBtn && screen1d) {
        brandBtn.addEventListener("click", function () {
            // Brand-Felder zuruecksetzen
            if (brandBestaetigungInput) { brandBestaetigungInput.value = ""; }
            if (brandSubmitBtn) { brandSubmitBtn.disabled = true; }
            if (brandFehler) { brandFehler.style.display = "none"; }
            var ortFeld = document.getElementById("brand-ort");
            if (ortFeld) { ortFeld.value = ""; }
            zeigeScreen(screen1d);
        });
    }

    // ---------------------------------------------------------------------------
    // Screen 1a: Erste Hilfe (Schritt 1 -> 2)
    // ---------------------------------------------------------------------------
    if (ehWeiterBtn) {
        ehWeiterBtn.addEventListener("click", function () {
            if (ehSchritt1) { ehSchritt1.style.display = "none"; }
            if (ehSchritt2) {
                ehSchritt2.style.display = "";
                var ortInput = document.getElementById("eh-ort");
                if (ortInput) { ortInput.focus(); }
            }
        });
    }

    // Zurueck-Button in 1a
    var backBtn1a = document.getElementById("sos-back-1a");
    if (backBtn1a) {
        backBtn1a.addEventListener("click", function () {
            // EH-Schritte zuruecksetzen
            if (ehSchritt1) { ehSchritt1.style.display = ""; }
            if (ehSchritt2) { ehSchritt2.style.display = "none"; }
            zeigeScreen(screen0);
        });
    }

    // ---------------------------------------------------------------------------
    // Screen 1b: AMOK-Bestaetigung
    // ---------------------------------------------------------------------------
    if (amokBestaetigungInput && amokSubmitBtn) {
        amokBestaetigungInput.addEventListener("input", function () {
            var wert = amokBestaetigungInput.value.trim();
            if (wert === "AMOK") {
                amokSubmitBtn.disabled = false;
                if (amokFehler) { amokFehler.style.display = "none"; }
            } else {
                amokSubmitBtn.disabled = true;
                if (amokFehler) {
                    amokFehler.style.display = wert.length > 0 ? "" : "none";
                }
            }
        });
    }

    var backBtn1b = document.getElementById("sos-back-1b");
    if (backBtn1b) {
        backBtn1b.addEventListener("click", function () {
            if (amokBestaetigungInput) { amokBestaetigungInput.value = ""; }
            if (amokSubmitBtn) { amokSubmitBtn.disabled = true; }
            if (amokFehler) { amokFehler.style.display = "none"; }
            zeigeScreen(screen0);
        });
    }

    // ---------------------------------------------------------------------------
    // Screen 1c: Stiller Alarm (fetch-POST, kein sichtbares Feedback)
    // ---------------------------------------------------------------------------
    var stillBtn = document.getElementById("still-bestaetigen-btn");
    if (stillBtn) {
        stillBtn.addEventListener("click", function () {
            var ortFeld = document.getElementById("still-ort");
            var ort = ortFeld ? ortFeld.value.trim() : "";

            var csrfMeta = document.querySelector("meta[name='csrf-token']");
            var csrfToken = csrfMeta ? csrfMeta.content : "";

            var formData = new FormData();
            formData.append("typ", "still");
            formData.append("ort", ort);

            // Diskret im Hintergrund senden – keine sichtbare Reaktion
            fetch("/sicherheit/ausloesen/", {
                method: "POST",
                headers: { "X-CSRFToken": csrfToken },
                body: formData,
            }).catch(function () {});

            // Modal sofort schliessen ohne Feedback
            var bsModal = bootstrap.Modal.getInstance(modal);
            if (bsModal) { bsModal.hide(); }
        });
    }

    var backBtn1c = document.getElementById("sos-back-1c");
    if (backBtn1c) {
        backBtn1c.addEventListener("click", function () {
            zeigeScreen(screen0);
        });
    }

    // ---------------------------------------------------------------------------
    // Screen 1d: Brand-Bestaetigung (FEUER)
    // ---------------------------------------------------------------------------
    if (brandBestaetigungInput && brandSubmitBtn) {
        brandBestaetigungInput.addEventListener("input", function () {
            var wert = brandBestaetigungInput.value.trim();
            if (wert === "FEUER") {
                brandSubmitBtn.disabled = false;
                if (brandFehler) { brandFehler.style.display = "none"; }
            } else {
                brandSubmitBtn.disabled = true;
                if (brandFehler) {
                    brandFehler.style.display = wert.length > 0 ? "" : "none";
                }
            }
        });
    }

    var backBtn1d = document.getElementById("sos-back-1d");
    if (backBtn1d) {
        backBtn1d.addEventListener("click", function () {
            if (brandBestaetigungInput) { brandBestaetigungInput.value = ""; }
            if (brandSubmitBtn) { brandSubmitBtn.disabled = true; }
            if (brandFehler) { brandFehler.style.display = "none"; }
            zeigeScreen(screen0);
        });
    }

    // ---------------------------------------------------------------------------
    // Modal-Reset: bei Schliessen immer auf Screen 0 zurueck
    // ---------------------------------------------------------------------------
    if (modal) {
        modal.addEventListener("hidden.bs.modal", function () {
            // EH-Schritte zuruecksetzen
            if (ehSchritt1) { ehSchritt1.style.display = ""; }
            if (ehSchritt2) { ehSchritt2.style.display = "none"; }
            // AMOK-Felder zuruecksetzen
            if (amokBestaetigungInput) { amokBestaetigungInput.value = ""; }
            if (amokSubmitBtn) { amokSubmitBtn.disabled = true; }
            if (amokFehler) { amokFehler.style.display = "none"; }
            // Brand-Felder zuruecksetzen
            if (brandBestaetigungInput) { brandBestaetigungInput.value = ""; }
            if (brandSubmitBtn) { brandSubmitBtn.disabled = true; }
            if (brandFehler) { brandFehler.style.display = "none"; }
            // Screen 0 wiederherstellen
            alleScreensAusblenden();
            screen0.style.display = "";
        });
    }
});
