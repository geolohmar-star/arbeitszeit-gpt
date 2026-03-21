// OnlyOffice-Editor: Initialisierung und Speichern-Logik
// CSP-konform: keine Inline-Scripts, alle Daten ueber json_script / data-Attribute

document.addEventListener("DOMContentLoaded", function () {
    var ooData = document.getElementById("oo-data");
    var configEl = document.getElementById("oo-config");

    if (!configEl || !ooData) {
        return;
    }

    var config = JSON.parse(configEl.textContent);
    var token = ooData.dataset.token;

    if (token) {
        config.token = token;
    }
    config.height = "100%";
    config.width  = "100%";

    // eslint-disable-next-line no-undef
    new DocsAPI.DocEditor("editor", config);

    // Speichern-Button nur im Bearbeitungsmodus vorhanden
    var btnSpeichern = document.getElementById("btn-speichern");
    if (!btnSpeichern) {
        return;
    }

    var aktuelleVersion  = parseInt(ooData.dataset.version, 10);
    var urlForcesave     = ooData.dataset.urlForcesave;
    var urlVersionCheck  = ooData.dataset.urlVersionCheck;
    var urlBack          = ooData.dataset.urlBack;
    var csrfMeta         = document.querySelector("meta[name='csrf-token']");
    var csrfToken        = csrfMeta ? csrfMeta.content : "";

    btnSpeichern.addEventListener("click", function () {
        btnSpeichern.disabled = true;
        btnSpeichern.textContent = "Wird gespeichert...";

        fetch(urlForcesave, {
            method: "POST",
            headers: {"X-CSRFToken": csrfToken},
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.ok) {
                btnSpeichern.textContent = "Warte auf Speicherung...";
                warteAufNeueVersion(0);
            } else {
                btnSpeichern.disabled = false;
                btnSpeichern.textContent = "Speichern & zurueck";
                alert("Speichern fehlgeschlagen: " + (data.fehler || "unbekannt"));
            }
        })
        .catch(function () {
            btnSpeichern.disabled = false;
            btnSpeichern.textContent = "Speichern & zurueck";
            alert("Verbindungsfehler beim Speichern.");
        });
    });

    function warteAufNeueVersion(versuch) {
        if (versuch > 20) {
            window.location.href = urlBack;
            return;
        }
        fetch(urlVersionCheck)
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.version > aktuelleVersion) {
                window.location.href = urlBack;
            } else {
                setTimeout(function () { warteAufNeueVersion(versuch + 1); }, 500);
            }
        })
        .catch(function () {
            setTimeout(function () { warteAufNeueVersion(versuch + 1); }, 500);
        });
    }
});
