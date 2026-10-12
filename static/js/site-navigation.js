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
