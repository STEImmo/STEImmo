(() => {
    const menu = document.getElementById("site-mobile-menu");
    const toggle = document.getElementById("site-menu-toggle");
    if (!menu || !toggle || !window.UIkit) return;

    UIkit.util.on(menu, "shown", (event) => {
        if (event.target !== menu) return;
        toggle.setAttribute("aria-expanded", "true");
        menu.querySelector("nav a")?.focus();
    });
    UIkit.util.on(menu, "hidden", (event) => {
        if (event.target !== menu) return;
        toggle.setAttribute("aria-expanded", "false");
        toggle.focus();
    });
})();
