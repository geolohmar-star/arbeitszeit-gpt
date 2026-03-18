/**
 * dms_neu.js – Auswahl-Logik auf der "Neues Dokument"-Seite
 *
 * Klick auf eine Kachel blendet das Formular ein und setzt ggf. den Dateityp.
 * "Zurueck"-Button blendet das Formular wieder aus.
 * URL-Parameter ?typ=xlsx oeffnet das Formular sofort mit xlsx vorausgewaehlt.
 */
document.addEventListener("DOMContentLoaded", function () {
    var kacheln    = {
        "docx": document.getElementById("kachel-leer"),
        "xlsx": document.getElementById("kachel-xlsx"),
        "pptx": document.getElementById("kachel-pptx")
    };
    var form       = document.getElementById("form-leer");
    var btnZurueck = document.getElementById("btn-abbrechen-leer");
    var selectTyp  = form ? form.querySelector("select[name='dateityp_neu']") : null;

    if (!form) return;

    function zeigeFormular(dateityp) {
        if (selectTyp && dateityp) {
            selectTyp.value = dateityp;
        }
        form.style.display = "block";
        Object.entries(kacheln).forEach(function (entry) {
            if (entry[1]) {
                entry[1].style.boxShadow = entry[0] === dateityp ? "0 0 0 2px #1a4d2e" : "";
            }
        });
        form.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    Object.entries(kacheln).forEach(function (entry) {
        var typ    = entry[0];
        var kachel = entry[1];
        if (kachel) {
            kachel.addEventListener("click", function () {
                zeigeFormular(typ);
            });
        }
    });

    if (btnZurueck) {
        btnZurueck.addEventListener("click", function () {
            form.style.display = "none";
            Object.values(kacheln).forEach(function (k) {
                if (k) k.style.boxShadow = "";
            });
            var erstekachel = Object.values(kacheln).find(function (k) { return k; });
            if (erstekachel) erstekachel.scrollIntoView({ behavior: "smooth", block: "start" });
        });
    }

    // URL-Parameter ?typ=xlsx / ?typ=pptx / ?typ=docx: Formular sofort oeffnen
    var urlParams = new URLSearchParams(window.location.search);
    var typParam  = urlParams.get("typ");
    if (typParam && kacheln[typParam] !== undefined) {
        zeigeFormular(typParam);
        return;
    }

    // Nach POST-Fehler: Formular sofort einblenden
    var hatFehler = form.querySelector(".text-danger");
    if (hatFehler) {
        form.style.display = "block";
        if (kacheln["docx"]) kacheln["docx"].style.boxShadow = "0 0 0 2px #1a4d2e";
    }
});
