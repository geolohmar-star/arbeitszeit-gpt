// Korrespondenz – OnlyOffice-Editor
// Alle Daten-Elemente stehen im DOM bevor dieses Script geladen wird (Template-Reihenfolge).

// Konfiguration aus json_script-Elementen lesen
var _ooConfig  = JSON.parse(document.getElementById("onlyoffice-config").textContent);
var _ooTokenEl = document.getElementById("onlyoffice-token");
var _ooUrls    = JSON.parse(document.getElementById("korrespondenz-urls").textContent);
var _ooVersion = JSON.parse(document.getElementById("brief-version").textContent);

// JWT-Token einhaengen (falls vorhanden)
if (_ooTokenEl) {
    _ooConfig.token = JSON.parse(_ooTokenEl.textContent);
}
_ooConfig.height = "100%";
_ooConfig.width  = "100%";

// OnlyOffice-Editor starten
var _ooEditor = new DocsAPI.DocEditor("editor", _ooConfig);

// ---- Speichern & Zurueck ----
document.getElementById("btn-speichern").addEventListener("click", function () {
    var btn = this;
    btn.disabled = true;
    btn.textContent = "Wird gespeichert...";

    fetch(_ooUrls.forcesave, {
        method: "POST",
        headers: { "X-CSRFToken": _ooUrls.csrf },
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
        if (data.ok) {
            btn.textContent = "Warte auf Speicherung...";
            _warteAufNeueVersion(0);
        } else {
            btn.disabled = false;
            btn.textContent = "Speichern & zurueck";
            alert("Speichern fehlgeschlagen: " + (data.fehler || "unbekannt"));
        }
    })
    .catch(function () {
        btn.disabled = false;
        btn.textContent = "Speichern & zurueck";
        alert("Verbindungsfehler beim Speichern.");
    });
});

// Pollen bis PRIMA die neue Version empfangen hat, dann weiterleiten
function _warteAufNeueVersion(versuch) {
    if (versuch > 20) {
        window.location.href = _ooUrls.zurueck;
        return;
    }
    fetch(_ooUrls.version)
    .then(function (r) { return r.json(); })
    .then(function (data) {
        if (data.version > _ooVersion) {
            window.location.href = _ooUrls.zurueck;
        } else {
            setTimeout(function () { _warteAufNeueVersion(versuch + 1); }, 200);
        }
    })
    .catch(function () {
        setTimeout(function () { _warteAufNeueVersion(versuch + 1); }, 200);
    });
}
