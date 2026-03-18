// Blendet Wochentag-Feld ein/aus je nach Wiederkehrend-Checkbox
document.addEventListener("DOMContentLoaded", function () {
    var checkbox = document.getElementById("id_ist_wiederkehrend");
    var rowWochentag = document.getElementById("row-wochentag");

    function aktualisiere() {
        if (checkbox.checked) {
            rowWochentag.classList.remove("d-none");
        } else {
            rowWochentag.classList.add("d-none");
        }
    }

    checkbox.addEventListener("change", aktualisiere);
    aktualisiere();
});
