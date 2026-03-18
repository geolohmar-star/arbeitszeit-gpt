// Korrespondenz – Brief-Detailseite
// Bestaetigung vor dem Loeschen eines Briefvorgangs

document.addEventListener("DOMContentLoaded", function () {
    var btnLoeschen = document.getElementById("btn-loeschen");
    if (btnLoeschen) {
        btnLoeschen.addEventListener("click", function (e) {
            if (!confirm("Brief endgueltig loeschen? Diese Aktion kann nicht rueckgaengig gemacht werden.")) {
                e.preventDefault();
            }
        });
    }
});
