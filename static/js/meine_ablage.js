// Meine Ablage – Loeschen-Bestaetigung
document.addEventListener("DOMContentLoaded", function () {
    document.body.addEventListener("click", function (e) {
        var btn = e.target.closest("[data-action='loeschen-persoenlich']");
        if (!btn) return;
        var titel = btn.dataset.titel || "dieses Dokument";
        if (!confirm("\"" + titel + "\" wirklich endgueltig loeschen?")) {
            return;
        }
        var formId = btn.dataset.formId;
        var form = document.getElementById(formId);
        if (form) form.submit();
    });
});
