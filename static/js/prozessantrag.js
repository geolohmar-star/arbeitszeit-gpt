/* Prozessantrag-Formular – CSP-konformes JavaScript */

document.addEventListener("DOMContentLoaded", function () {

    // Schritt-Zaehler fuer HTMX neue Zeile aktualisieren
    function aktualisiereSchrittzaehler() {
        var btn = document.getElementById("btn-neue-zeile");
        if (!btn) return;
        var zeilen = document.querySelectorAll(".schritt-zeile");
        var aktuellerHref = btn.getAttribute("hx-get") || "";
        var neuerHref = aktuellerHref.replace(/nr=\d+/, "nr=" + (zeilen.length + 1));
        btn.setAttribute("hx-get", neuerHref);
        // HTMX muss neu prozessiert werden damit die Aenderung greift
        if (typeof htmx !== "undefined") {
            htmx.process(btn);
        }
    }

    // Loeschen-Buttons per Event Delegation
    document.body.addEventListener("click", function (e) {
        var btn = e.target.closest("[data-action='schritt-loeschen']");
        if (!btn) return;
        var zeile = btn.closest(".schritt-zeile");
        if (!zeile) return;
        // Mindestens eine Zeile behalten
        if (document.querySelectorAll(".schritt-zeile").length <= 1) return;
        zeile.remove();
        // Schritte neu nummerieren
        document.querySelectorAll(".schritt-zeile").forEach(function (z, idx) {
            var nr = idx + 1;
            z.dataset.nr = nr;
            var anzeigefeld = z.querySelector("input[type='text'][readonly]");
            if (anzeigefeld) anzeigefeld.value = nr;
            z.querySelectorAll("input[name], textarea[name]").forEach(function (inp) {
                inp.name = inp.name.replace(/schritt_\d+_/, "schritt_" + nr + "_");
            });
        });
        aktualisiereSchrittzaehler();
    });

    // Nach HTMX-Swap neue Zeile: Zaehler aktualisieren
    document.body.addEventListener("htmx:afterSwap", function (e) {
        if (e.target && e.target.id === "schritte-container") {
            aktualisiereSchrittzaehler();
        }
    });

    // Team-Vorschlag ein-/ausblenden je nach Checkbox
    var teamCheck = document.getElementById("id_team_benoetigt");
    var teamFeld = document.getElementById("team-vorschlag-feld");
    if (teamCheck && teamFeld) {
        teamFeld.style.display = teamCheck.checked ? "block" : "none";
        teamCheck.addEventListener("change", function () {
            teamFeld.style.display = teamCheck.checked ? "block" : "none";
        });
    }
});
