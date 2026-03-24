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

    // ---------------------------------------------------------------------------
    // Signatur-Pad (Handschrift-Canvas)
    // ---------------------------------------------------------------------------

    document.querySelectorAll("[data-sig-id]").forEach(function (canvas) {
        var id = canvas.dataset.sigId;
        var hidden = document.getElementById("sig-input-" + id);
        var ctx = canvas.getContext("2d");
        var zeichnet = false;
        var letzterX = 0, letzterY = 0;

        ctx.strokeStyle = "#1a1a1a";
        ctx.lineWidth = 2;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";

        function pos(e) {
            var r = canvas.getBoundingClientRect();
            var scaleX = canvas.width / r.width;
            var scaleY = canvas.height / r.height;
            var src = e.touches ? e.touches[0] : e;
            return {
                x: (src.clientX - r.left) * scaleX,
                y: (src.clientY - r.top) * scaleY
            };
        }

        function startZeichnen(e) {
            e.preventDefault();
            zeichnet = true;
            var p = pos(e);
            letzterX = p.x;
            letzterY = p.y;
            ctx.beginPath();
            ctx.arc(p.x, p.y, 1, 0, Math.PI * 2);
            ctx.fillStyle = "#1a1a1a";
            ctx.fill();
        }

        function weiterZeichnen(e) {
            if (!zeichnet) return;
            e.preventDefault();
            var p = pos(e);
            ctx.beginPath();
            ctx.moveTo(letzterX, letzterY);
            ctx.lineTo(p.x, p.y);
            ctx.stroke();
            letzterX = p.x;
            letzterY = p.y;
        }

        function stopZeichnen(e) {
            if (!zeichnet) return;
            zeichnet = false;
            // PNG als base64 in Hidden-Input schreiben
            if (hidden) hidden.value = canvas.toDataURL("image/png");
        }

        canvas.addEventListener("mousedown", startZeichnen);
        canvas.addEventListener("mousemove", weiterZeichnen);
        canvas.addEventListener("mouseup", stopZeichnen);
        canvas.addEventListener("mouseleave", stopZeichnen);
        canvas.addEventListener("touchstart", startZeichnen, { passive: false });
        canvas.addEventListener("touchmove", weiterZeichnen, { passive: false });
        canvas.addEventListener("touchend", stopZeichnen);

        // Loeschen-Button
        var clearBtn = document.querySelector("[data-sig-clear='" + id + "']");
        if (clearBtn) {
            clearBtn.addEventListener("click", function () {
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                if (hidden) hidden.value = "";
            });
        }
    });
});
