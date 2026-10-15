(() => {
    const menu = document.getElementById("site-mobile-menu");
    const toggle = document.getElementById("site-menu-toggle");
    if (!menu || !toggle || !window.UIkit) return;
    let focusAfterClose = toggle;

    menu.addEventListener("click", (event) => {
        const link = event.target.closest("nav a[href]");
        if (!link) return;
        const target = new URL(link.href, window.location.href);
        if (target.origin === window.location.origin &&
            target.pathname === window.location.pathname &&
            target.search === window.location.search && target.hash) {
            focusAfterClose = document.getElementById(decodeURIComponent(target.hash.slice(1))) || toggle;
        }
    }, true);

    UIkit.util.on(menu, "shown", (event) => {
        if (event.target !== menu) return;
        focusAfterClose = toggle;
        toggle.setAttribute("aria-expanded", "true");
        menu.querySelector("nav a")?.focus();
    });
    UIkit.util.on(menu, "hidden", (event) => {
        if (event.target !== menu) return;
        toggle.setAttribute("aria-expanded", "false");
        // Apply the destination after UIkit restores the previous focus.
        requestAnimationFrame(() => focusAfterClose.focus());
    });
})();

(() => {
    const toggle = document.querySelector("[data-mobile-filter-toggle]");
    const body = document.getElementById("apartment-filter-body");
    if (!toggle || !body) return;
    const mobile = window.matchMedia("(max-width: 959px)");
    let expanded = body.dataset.filterErrors === "true";
    const update = () => {
        body.hidden = mobile.matches && !expanded;
        toggle.setAttribute("aria-expanded", String(!body.hidden));
        toggle.textContent = `${body.hidden ? "Filter anzeigen" : "Filter schließen"}${toggle.dataset.activeLabel || ""}`;
    };
    toggle.dataset.activeLabel = toggle.textContent.includes("Filter aktiv") ? " · Filter aktiv" : "";
    toggle.hidden = false;
    toggle.closest("aside").dataset.collapsible = "true";
    toggle.addEventListener("click", () => { expanded = !expanded; update(); });
    mobile.addEventListener("change", update);
    update();
})();
