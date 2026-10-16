(() => {
    // UIkit moves dropdowns to body to escape the scrolling table. Move focus
    // with them so keyboard users reach the fields directly after opening.
    document.addEventListener("shown", (event) => {
        if (!event.target.matches?.("[data-table-filter-dropdown]")) return;
        event.target.querySelector("select, input:not([type='hidden'])")?.focus();
    });
    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape" || !(event.target instanceof Element)) return;
        const dropdown = event.target.closest("[data-table-filter-dropdown]");
        if (!dropdown) return;
        window.UIkit.dropdown(dropdown).hide(false);
        document.getElementById(dropdown.getAttribute("aria-labelledby"))?.focus();
    });
})();
