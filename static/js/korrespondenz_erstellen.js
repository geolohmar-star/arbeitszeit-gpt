/**
 * korrespondenz_erstellen.js
 *
 * Wenn der User eine andere Briefvorlage waehlt, werden die Absender-Felder
 * automatisch mit den Vorlage-Defaults vorbelegt – sofern das Feld noch leer
 * oder noch unveraendert gegenueber der vorherigen Vorausfuellung ist.
 * Felder die der User bereits selbst bearbeitet hat, werden NICHT ueberschrieben.
 */
document.addEventListener("DOMContentLoaded", function () {
    var defaults = JSON.parse(document.getElementById("vorlagen-defaults").textContent);

    var vorlageSelect = document.getElementById("id_vorlage");
    if (!vorlageSelect) return;

    // Felder die automatisch vorbelegt werden koennen
    var feldMap = {
        "absender_name":    "id_absender_name",
        "absender_strasse": "id_absender_strasse",
        "absender_ort":     "id_absender_ort",
        "absender_telefon": "id_absender_telefon",
        "absender_email":   "id_absender_email",
        "ort":              "id_ort",
        "grussformel":      "id_grussformel",
    };

    // Merkt sich welche Werte automatisch eingetragen wurden (kein Ueberschreiben
    // von Feldern die der User selbst bearbeitet hat)
    var autogefuellt = {};

    function fuelleMitDefaults(vorlagePk) {
        var data = defaults[vorlagePk] || {};
        Object.keys(feldMap).forEach(function (key) {
            var input = document.getElementById(feldMap[key]);
            if (!input) return;
            var wert = data[key] || "";
            // Nur vorbelegen wenn: Feld leer ODER noch den alten Auto-Wert enthaelt
            if (input.value === "" || input.value === (autogefuellt[key] || "")) {
                input.value = wert;
                autogefuellt[key] = wert;
            }
        });
    }

    vorlageSelect.addEventListener("change", function () {
        fuelleMitDefaults(this.value);
    });

    // Beim ersten Laden: Defaults fuer die bereits ausgewaehlte Vorlage einfuellen
    // (aber nur in leere Felder – Server-seitig befuellte Felder nicht ueberschreiben)
    if (vorlageSelect.value) {
        var data = defaults[vorlageSelect.value] || {};
        Object.keys(feldMap).forEach(function (key) {
            var input = document.getElementById(feldMap[key]);
            if (!input) return;
            if (input.value === "") {
                input.value = data[key] || "";
                autogefuellt[key] = data[key] || "";
            } else {
                // Feld hat bereits einen Wert (vom Server) – als "auto" merken
                autogefuellt[key] = input.value;
            }
        });
    }
});
