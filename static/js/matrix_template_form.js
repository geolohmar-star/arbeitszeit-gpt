// Blendet Felder je nach Typ-Auswahl ein/aus
document.addEventListener("DOMContentLoaded", function () {
    var typSelect = document.getElementById("id_typ");
    var rowOrgEinheit = document.getElementById("row-org-einheit");
    var rowMitglieder = document.getElementById("row-mitglieder");

    function aktualisiere() {
        if (typSelect.value === "org_einheit") {
            rowOrgEinheit.classList.remove("d-none");
            rowMitglieder.classList.add("d-none");
        } else {
            rowOrgEinheit.classList.add("d-none");
            rowMitglieder.classList.remove("d-none");
        }
    }

    typSelect.addEventListener("change", aktualisiere);
    aktualisiere();
});
