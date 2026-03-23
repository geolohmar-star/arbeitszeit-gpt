/**
 * formulare_dashboard.js – Suche mit Vorschlagsliste fuer das Formulare-Dashboard
 * CSP-konform, kein Inline-JS.
 */
(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        var sucheInput = document.getElementById("formular-suche");
        var dropdown = document.getElementById("suche-dropdown");
        var keineTreffer = document.getElementById("suche-keine-treffer");
        var rubrikenContainer = document.getElementById("rubriken-container");
        if (!sucheInput) return;

        // Suchdaten aus json_script laden
        var datenEl = document.getElementById("suche-daten");
        var alleFormulare = datenEl ? JSON.parse(datenEl.textContent) : [];

        // Alle Karten und Rubriken
        var karten = document.querySelectorAll(".antrag-karte");
        var rubriken = document.querySelectorAll(".rubrik");

        function zeigeDropdown(treffer) {
            if (treffer.length === 0) {
                dropdown.style.display = "none";
                return;
            }
            var html = "";
            treffer.forEach(function (f) {
                html += '<a href="' + esc(f.url) + '" class="dropdown-item py-2">'
                    + '<span class="fw-semibold">' + esc(f.name) + '</span>'
                    + ' <span class="text-muted small ms-1">' + esc(f.rubrik) + '</span>'
                    + '</a>';
            });
            dropdown.innerHTML = html;
            dropdown.style.display = "block";
        }

        function filterKarten(query) {
            var q = query.toLowerCase().trim();

            if (!q) {
                // Alles zeigen
                karten.forEach(function (k) { k.style.display = ""; });
                rubriken.forEach(function (r) { r.style.display = ""; });
                if (keineTreffer) keineTreffer.style.display = "none";
                dropdown.style.display = "none";
                return;
            }

            // Vorschlagsliste
            var treffer = alleFormulare.filter(function (f) {
                return f.name.toLowerCase().indexOf(q) !== -1
                    || (f.rubrik && f.rubrik.toLowerCase().indexOf(q) !== -1);
            }).slice(0, 8);
            zeigeDropdown(treffer);

            // Karten ein-/ausblenden
            var irgendwasSichtbar = false;
            karten.forEach(function (k) {
                var name = (k.dataset.name || "").toLowerCase();
                var sichtbar = name.indexOf(q) !== -1;
                k.style.display = sichtbar ? "" : "none";
                if (sichtbar) irgendwasSichtbar = true;
            });

            // Rubriken ausblenden wenn alle Karten darin versteckt sind
            rubriken.forEach(function (r) {
                var sichtbareKarten = r.querySelectorAll(".antrag-karte");
                var hatSichtbare = false;
                sichtbareKarten.forEach(function (k) {
                    if (k.style.display !== "none") hatSichtbare = true;
                });
                r.style.display = hatSichtbare ? "" : "none";
            });

            if (keineTreffer) {
                keineTreffer.style.display = irgendwasSichtbar ? "none" : "";
            }
        }

        sucheInput.addEventListener("input", function () {
            filterKarten(this.value);
        });

        // Dropdown schliessen bei Klick ausserhalb
        document.addEventListener("click", function (e) {
            if (!sucheInput.contains(e.target) && !dropdown.contains(e.target)) {
                dropdown.style.display = "none";
            }
        });

        // ESC: Suche leeren
        sucheInput.addEventListener("keydown", function (e) {
            if (e.key === "Escape") {
                this.value = "";
                filterKarten("");
            }
            // Pfeiltasten fuer Dropdown-Navigation
            if (e.key === "ArrowDown") {
                var erster = dropdown.querySelector(".dropdown-item");
                if (erster) { e.preventDefault(); erster.focus(); }
            }
        });

        // Tastaturnavigation im Dropdown
        dropdown.addEventListener("keydown", function (e) {
            var items = dropdown.querySelectorAll(".dropdown-item");
            var aktiv = document.activeElement;
            var idx = Array.prototype.indexOf.call(items, aktiv);
            if (e.key === "ArrowDown" && idx < items.length - 1) {
                e.preventDefault(); items[idx + 1].focus();
            } else if (e.key === "ArrowUp") {
                e.preventDefault();
                if (idx > 0) { items[idx - 1].focus(); } else { sucheInput.focus(); }
            } else if (e.key === "Escape") {
                sucheInput.value = "";
                filterKarten("");
                sucheInput.focus();
            }
        });

        function esc(str) {
            return String(str)
                .replace(/&/g, "&amp;").replace(/</g, "&lt;")
                .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
        }
    });
})();
