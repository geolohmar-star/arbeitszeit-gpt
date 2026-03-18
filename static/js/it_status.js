document.addEventListener("DOMContentLoaded", function () {
    // Klick auf Tabellenzeilen navigiert zur Detailseite
    document.querySelectorAll("tr[data-href]").forEach(function (row) {
        row.addEventListener("click", function () {
            window.location = row.dataset.href;
        });
    });

    // System-Vorauswahl per URL-Parameter (?system=<pk>)
    var params = new URLSearchParams(window.location.search);
    var systemPk = params.get("system");
    if (systemPk) {
        var select = document.querySelector("select[name='system']");
        if (select) {
            select.value = systemPk;
        }
    }
});
