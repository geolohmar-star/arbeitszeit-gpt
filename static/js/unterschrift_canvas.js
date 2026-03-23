/**
 * unterschrift_canvas.js – Unterschriften-Canvas fuer externe Formulare
 * CSP-konform: kein Inline-JS, kein eval.
 * Unterstuetzt Maus und Touch (Kiosk-Betrieb).
 */
(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        var canvas = document.getElementById("unterschrift-canvas");
        if (!canvas) return;

        var ctx = canvas.getContext("2d");
        var dataInput = document.getElementById("unterschrift-data");
        var statusEl = document.getElementById("unterschrift-status");
        var loeschenBtn = document.getElementById("btn-unterschrift-loeschen");
        var form = document.getElementById("extern-form");

        var zeichnen = false;
        var hatInhalt = false;

        // Canvas-Groesse an tatsaechliche CSS-Groesse anpassen
        function resizeCanvas() {
            var rect = canvas.getBoundingClientRect();
            var dpr = window.devicePixelRatio || 1;
            // Inhalt sichern
            var bildData = hatInhalt ? canvas.toDataURL() : null;
            canvas.width = Math.floor(rect.width * dpr);
            canvas.height = Math.floor(rect.height * dpr);
            ctx.scale(dpr, dpr);
            ctx.strokeStyle = "#1a1a1a";
            ctx.lineWidth = 2;
            ctx.lineCap = "round";
            ctx.lineJoin = "round";
            // Inhalt wiederherstellen
            if (bildData) {
                var img = new Image();
                img.onload = function () { ctx.drawImage(img, 0, 0, rect.width, rect.height); };
                img.src = bildData;
            }
        }

        resizeCanvas();
        window.addEventListener("resize", resizeCanvas);

        function getPos(e) {
            var rect = canvas.getBoundingClientRect();
            if (e.touches) {
                return {
                    x: e.touches[0].clientX - rect.left,
                    y: e.touches[0].clientY - rect.top
                };
            }
            return { x: e.clientX - rect.left, y: e.clientY - rect.top };
        }

        function startZeichnen(e) {
            e.preventDefault();
            zeichnen = true;
            var pos = getPos(e);
            ctx.beginPath();
            ctx.moveTo(pos.x, pos.y);
            canvas.classList.add("aktiv");
        }

        function weiterZeichnen(e) {
            if (!zeichnen) return;
            e.preventDefault();
            var pos = getPos(e);
            ctx.lineTo(pos.x, pos.y);
            ctx.stroke();
            hatInhalt = true;
        }

        function stopZeichnen(e) {
            if (!zeichnen) return;
            zeichnen = false;
            if (hatInhalt) {
                dataInput.value = canvas.toDataURL("image/png");
                if (statusEl) statusEl.textContent = "Unterschrift erfasst.";
            }
        }

        // Maus-Events
        canvas.addEventListener("mousedown", startZeichnen);
        canvas.addEventListener("mousemove", weiterZeichnen);
        canvas.addEventListener("mouseup", stopZeichnen);
        canvas.addEventListener("mouseleave", stopZeichnen);

        // Touch-Events (Kiosk / Tablet)
        canvas.addEventListener("touchstart", startZeichnen, { passive: false });
        canvas.addEventListener("touchmove", weiterZeichnen, { passive: false });
        canvas.addEventListener("touchend", stopZeichnen);

        // Loeschen
        if (loeschenBtn) {
            loeschenBtn.addEventListener("click", function () {
                var rect = canvas.getBoundingClientRect();
                ctx.clearRect(0, 0, rect.width, rect.height);
                hatInhalt = false;
                dataInput.value = "";
                canvas.classList.remove("aktiv");
                if (statusEl) statusEl.textContent = "";
            });
        }

        // Vor Absenden: Unterschrift in hidden input sichern
        if (form) {
            form.addEventListener("submit", function () {
                if (hatInhalt) {
                    dataInput.value = canvas.toDataURL("image/png");
                }
            });
        }
    });
})();
