(function() {
    var path = window.location.pathname;
    document.querySelectorAll(".navbar-nav .nav-item").forEach(function(item) {
        var link = item.querySelector(":scope > .nav-link:not(.dropdown-toggle)");
        if (link && link.getAttribute("href") && link.getAttribute("href") !== "#") {
            try {
                var linkPath = new URL(link.href, window.location.origin).pathname;
                if (linkPath !== "/" && path.startsWith(linkPath)) {
                    item.classList.add("nav-active");
                }
            } catch(e) {}
        }
    });
})();
