/**
 * DMS – Loeschplanung mit dreifacher Sicherheitsabfrage
 * CSP-konform: kein Inline-JS, alle Events per addEventListener
 */
document.addEventListener("DOMContentLoaded", function () {
    var btn = document.getElementById("loeschen-planen-btn");
    if (!btn) return;

    // Schritt-Container
    var schritt1 = document.getElementById("loeschen-schritt-1");
    var schritt2 = document.getElementById("loeschen-schritt-2");
    var schritt3 = document.getElementById("loeschen-schritt-3");
    var fehlerDiv = document.getElementById("loeschen-fehler");

    // Schritt-1-Elemente
    var datumInput    = document.getElementById("loeschen-datum");
    var begruendungInput = document.getElementById("loeschen-begruendung");
    var weiterBtn1    = document.getElementById("loeschen-weiter-1");

    // Schritt-2-Elemente
    var weiterBtn2    = document.getElementById("loeschen-weiter-2");
    var zurueckBtn2   = document.getElementById("loeschen-zurueck-2");
    var s2Datum       = document.getElementById("loeschen-s2-datum");
    var s2Begruendung = document.getElementById("loeschen-s2-begruendung");

    // Schritt-3-Elemente
    var bestaetigungInput = document.getElementById("loeschen-bestaetigung");
    var absendendBtn  = document.getElementById("loeschen-absenden");
    var zurueckBtn3   = document.getElementById("loeschen-zurueck-3");

    // Alle Abbrechen-Buttons
    var abbrechenBtns = document.querySelectorAll(".loeschen-abbrechen");

    var url = btn.dataset.url;

    function zeigeSchritt(nr) {
        schritt1.style.display = nr === 1 ? "block" : "none";
        schritt2.style.display = nr === 2 ? "block" : "none";
        schritt3.style.display = nr === 3 ? "block" : "none";
        // Footer-Buttons je Schritt ein-/ausblenden
        weiterBtn1.style.display    = nr === 1 ? "inline-block" : "none";
        weiterBtn2.style.display    = nr === 2 ? "inline-block" : "none";
        zurueckBtn2.style.display   = nr === 2 ? "inline-block" : "none";
        zurueckBtn3.style.display   = nr === 3 ? "inline-block" : "none";
        absendendBtn.style.display  = nr === 3 ? "inline-block" : "none";
        fehlerDiv.textContent = "";
        fehlerDiv.style.display = "none";
    }

    function zeigeModal() {
        zeigeSchritt(1);
        datumInput.value = "";
        begruendungInput.value = "";
        bestaetigungInput.value = "";
        var modal = new bootstrap.Modal(document.getElementById("loeschenModal"));
        modal.show();
    }

    btn.addEventListener("click", zeigeModal);

    // Schritt 1 → 2
    weiterBtn1.addEventListener("click", function () {
        var datum = datumInput.value.trim();
        var begruendung = begruendungInput.value.trim();
        if (!datum) {
            fehlerDiv.textContent = "Bitte ein Loeschdatum waehlen.";
            fehlerDiv.style.display = "block";
            return;
        }
        var heute = new Date();
        heute.setHours(0, 0, 0, 0);
        if (new Date(datum) <= heute) {
            fehlerDiv.textContent = "Das Loeschdatum muss in der Zukunft liegen.";
            fehlerDiv.style.display = "block";
            return;
        }
        if (!begruendung) {
            fehlerDiv.textContent = "Bitte eine Begruendung angeben.";
            fehlerDiv.style.display = "block";
            return;
        }
        // Zusammenfassung in Schritt 2 fuellen
        var datumObj = new Date(datum + "T00:00:00");
        s2Datum.textContent = datumObj.toLocaleDateString("de-DE");
        s2Begruendung.textContent = begruendung;
        zeigeSchritt(2);
    });

    // Schritt 2 → 3
    weiterBtn2.addEventListener("click", function () {
        zeigeSchritt(3);
        bestaetigungInput.focus();
    });

    zurueckBtn2.addEventListener("click", function () { zeigeSchritt(1); });
    zurueckBtn3.addEventListener("click", function () { zeigeSchritt(2); });

    // Abbrechen
    abbrechenBtns.forEach(function (b) {
        b.addEventListener("click", function () {
            var modalEl = document.getElementById("loeschenModal");
            var modal = bootstrap.Modal.getInstance(modalEl);
            if (modal) modal.hide();
        });
    });

    // Schritt 3: Absenden
    absendendBtn.addEventListener("click", function () {
        var bestaetigung = bestaetigungInput.value.trim();
        if (bestaetigung !== "LOESCHEN") {
            fehlerDiv.textContent = "Bitte genau 'LOESCHEN' eingeben (Grossbuchstaben).";
            fehlerDiv.style.display = "block";
            return;
        }

        var datum = datumInput.value.trim();
        var begruendung = begruendungInput.value.trim();
        var csrfInput = document.querySelector("[name=csrfmiddlewaretoken]");
        var csrf = csrfInput ? csrfInput.value : "";

        absendendBtn.disabled = true;
        absendendBtn.textContent = "...";

        var formData = new FormData();
        formData.append("loeschen_am", datum);
        formData.append("begruendung", begruendung);
        formData.append("bestaetigung", bestaetigung);

        fetch(url, {
            method: "POST",
            headers: { "X-CSRFToken": csrf },
            body: formData,
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            absendendBtn.disabled = false;
            absendendBtn.textContent = "Endgueltig loeschen planen";

            if (!data.ok) {
                fehlerDiv.textContent = data.fehler || "Fehler beim Speichern.";
                fehlerDiv.style.display = "block";
                return;
            }

            // Modal schliessen, Seite neu laden mit Erfolgs-Meldung
            var modalEl = document.getElementById("loeschenModal");
            var modal = bootstrap.Modal.getInstance(modalEl);
            if (modal) modal.hide();
            window.location.reload();
        })
        .catch(function () {
            absendendBtn.disabled = false;
            absendendBtn.textContent = "Endgueltig loeschen planen";
            fehlerDiv.textContent = "Netzwerkfehler.";
            fehlerDiv.style.display = "block";
        });
    });

    // Enter in Bestaetigungsfeld loest Absenden aus
    bestaetigungInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
            e.preventDefault();
            absendendBtn.click();
        }
    });
});
