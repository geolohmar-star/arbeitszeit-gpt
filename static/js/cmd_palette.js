(function() {
    var dataEl  = document.getElementById("cmd-items-data");
    if (!dataEl) { return; }
    var CMD_ITEMS = JSON.parse(dataEl.textContent);

    var palette = document.getElementById("cmd-palette");
    var input   = document.getElementById("cmd-input");
    var results = document.getElementById("cmd-results");
    var sel     = -1;

    window.cmdOpen = function() {
        palette.classList.add("cmd-open");
        input.value = "";
        render("");
        input.focus();
    };

    function close() {
        palette.classList.remove("cmd-open");
        sel = -1;
    }

    function render(q) {
        var filtered = q
            ? CMD_ITEMS.filter(function(i) {
                var needle = q.toLowerCase();
                return i.l.toLowerCase().indexOf(needle) !== -1
                    || i.g.toLowerCase().indexOf(needle) !== -1;
              })
            : CMD_ITEMS;

        results.innerHTML = filtered.map(function(i, idx) {
            return "<a href=\"" + i.u + "\" class=\"cmd-item\" data-idx=\"" + idx + "\">"
                + "<span>" + i.l + "</span>"
                + "<span class=\"cmd-gruppe\">" + i.g + "</span>"
                + "</a>";
        }).join("");
        sel = -1;
    }

    function getLinks() {
        return results.querySelectorAll(".cmd-item");
    }

    function updateSel(links) {
        links.forEach(function(l, i) { l.classList.toggle("cmd-active", i === sel); });
        if (links[sel]) { links[sel].scrollIntoView({block: "nearest"}); }
    }

    document.addEventListener("keydown", function(e) {
        if (e.key === "/" && !palette.classList.contains("cmd-open")) {
            var tag = document.activeElement ? document.activeElement.tagName : "";
            if (tag !== "INPUT" && tag !== "TEXTAREA" && tag !== "SELECT") {
                e.preventDefault();
                cmdOpen();
                return;
            }
        }
        if (!palette.classList.contains("cmd-open")) { return; }
        var links = getLinks();
        if (e.key === "Escape") {
            close();
        } else if (e.key === "ArrowDown") {
            e.preventDefault();
            sel = Math.min(sel + 1, links.length - 1);
            updateSel(links);
        } else if (e.key === "ArrowUp") {
            e.preventDefault();
            sel = Math.max(sel - 1, 0);
            updateSel(links);
        } else if (e.key === "Enter" && sel >= 0) {
            links[sel].click();
        }
    });

    palette.addEventListener("click", function(e) {
        if (e.target === palette) { close(); }
    });

    input.addEventListener("input", function() {
        render(this.value);
    });
})();
