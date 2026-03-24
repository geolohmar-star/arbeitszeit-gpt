// pfad_schritt.js – Berechnungsfelder und Textblock-Variablen im Antrags-Player

document.addEventListener("DOMContentLoaded", function () {
    // Gesammelte Daten aus vorherigen Schritten (vom Server als JSON eingebettet)
    var gesammelteDaten = {};
    var gesammelteEl = document.getElementById("gesammelte-daten");
    if (gesammelteEl) {
        try { gesammelteDaten = JSON.parse(gesammelteEl.textContent); } catch (e) {}
    }

    // ---------------------------------------------------------------------------
    // Berechnungsfelder
    // ---------------------------------------------------------------------------

    function feldWerteAktuell() {
        // Alle Eingabewerte der aktuellen Seite sammeln
        var werte = Object.assign({}, gesammelteDaten);
        var form = document.querySelector("form");
        if (!form) return werte;
        var inputs = form.querySelectorAll("input, select, textarea");
        inputs.forEach(function (el) {
            if (!el.name || el.dataset.berechnungId) return;
            if (el.type === "checkbox") {
                if (el.checked) werte[el.name] = el.value || "1";
            } else if (el.type === "radio") {
                if (el.checked) werte[el.name] = el.value;
            } else {
                werte[el.name] = el.value;
            }
        });
        return werte;
    }

    function berechneFormel(formel, werte) {
        try {
            // {{feld_id}} durch Wert ersetzen
            var ausdruck = formel.replace(/\{\{(\w+)\}\}/g, function (_, id) {
                var v = werte[id];
                if (v === undefined || v === "") return "0";
                var n = parseFloat(String(v).replace(",", "."));
                return isNaN(n) ? "0" : String(n);
            });
            // Nur Zahlen und Operatoren erlaubt
            if (!/^[\d\s\.\+\-\*\/\(\)]+$/.test(ausdruck)) return null;
            // eslint-disable-next-line no-new-func
            var ergebnis = Function('"use strict"; return (' + ausdruck + ')')();
            if (!isFinite(ergebnis)) return null;
            return Math.round(ergebnis * 100) / 100;
        } catch (e) {
            return null;
        }
    }

    function aktualisiereBerechnung() {
        var werte = feldWerteAktuell();
        document.querySelectorAll("[data-berechnung-id]").forEach(function (anzeige) {
            var id = anzeige.dataset.berechnungId;
            var formel = anzeige.dataset.formel;
            if (!formel) return;
            var ergebnis = berechneFormel(formel, werte);
            if (ergebnis !== null) {
                anzeige.value = ergebnis;
                var hidden = document.getElementById("berechnung-hidden-" + id);
                if (hidden) hidden.value = ergebnis;
            } else {
                anzeige.value = "";
            }
        });
    }

    // Bei jeder Aenderung neu berechnen
    var form = document.querySelector("form");
    if (form) {
        form.addEventListener("input", aktualisiereBerechnung);
        form.addEventListener("change", aktualisiereBerechnung);
        aktualisiereBerechnung(); // Initialberechnung
    }

    // ---------------------------------------------------------------------------
    // Textblock-Variablen ersetzen
    // ---------------------------------------------------------------------------

    document.querySelectorAll("[id^='textblock-']").forEach(function (el) {
        var text = el.textContent;
        text = text.replace(/\{\{(\w+)\}\}/g, function (_, id) {
            return gesammelteDaten[id] !== undefined ? gesammelteDaten[id] : "…";
        });
        el.textContent = text;
    });
});
