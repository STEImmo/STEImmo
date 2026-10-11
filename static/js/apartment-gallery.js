(() => {
    if (!document.querySelector("[data-apartment-gallery]")) return;

    document.addEventListener("hide", (event) => {
        const panel = event.target;
        if (!(panel instanceof Element) || !panel.matches(".uk-lightbox")) return;

        // UIkit 3.25.24 can cancel its hidden event when a loading slide is closed.
        // Finish the normal UIkit cleanup after animations settle, unless it already ran.
        requestAnimationFrame(async () => {
            await Promise.allSettled(panel.getAnimations().map((animation) => animation.finished));
            if (panel.isConnected && !panel.classList.contains("uk-open")
                && getComputedStyle(panel).display === "none") {
                UIkit.util.trigger(panel, "hidden");
            }
        });
    });
})();
