/**
 * arbeitsschutz_dashboard.js
 * Suchfilter fuer die Mitarbeiter-Tabelle im Arbeitsschutz-Dashboard.
 */
document.addEventListener("DOMContentLoaded", function () {
    var suche = document.getElementById("suche");
    if (!suche) { return; }

    suche.addEventListener("input", function () {
        var q = suche.value.toLowerCase().trim();
        var zeilen = document.querySelectorAll("#ma-tabelle tbody tr");
        zeilen.forEach(function (zeile) {
            var text = zeile.dataset.suche || "";
            zeile.style.display = (!q || text.includes(q)) ? "" : "none";
        });
    });

    // HTMX: nach Toggle Fokus halten
    document.body.addEventListener("htmx:afterSwap", function (evt) {
        var zelle = evt.detail.target;
        if (zelle && zelle.id && zelle.id.startsWith("zelle-")) {
            var btn = zelle.querySelector(".cb-label");
            if (btn) { btn.focus(); }
        }
    });
});
