// Freitext-Feld: "Senden"-Button einblenden sobald Text eingegeben wird
document.addEventListener("DOMContentLoaded", function () {
    var notizInput = document.getElementById("id-notiz");
    var freitextBtn = document.getElementById("btn-freitext-senden");

    if (!notizInput || !freitextBtn) return;

    notizInput.addEventListener("input", function () {
        if (notizInput.value.trim().length > 0) {
            freitextBtn.style.display = "block";
        } else {
            freitextBtn.style.display = "none";
        }
    });
});
