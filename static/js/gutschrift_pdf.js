document.addEventListener("DOMContentLoaded", function () {
    var btn = document.getElementById("btn-print");
    if (btn) {
        btn.addEventListener("click", function () {
            window.print();
        });
    }
});
