(() => {
    const calendar = document.querySelector("[data-dashboard-calendar]");
    if (!calendar) return;

    let activeRequest;

    async function showWeek(url, {pushHistory = true, focusLabel} = {}) {
        activeRequest?.abort();
        const controller = new AbortController();
        activeRequest = controller;
        calendar.setAttribute("aria-busy", "true");

        try {
            // Reuse the protected, server-rendered dashboard; no separate calendar API.
            const response = await fetch(url, {
                credentials: "same-origin",
                cache: "no-store",
                signal: controller.signal,
            });
            if (!response.ok || response.redirected) throw new Error("Calendar unavailable");
            const page = new DOMParser().parseFromString(await response.text(), "text/html");
            if (controller.signal.aborted) return;
            const updated = page.querySelector("[data-dashboard-calendar]");
            if (!updated) throw new Error("Calendar missing");

            const restoreFocus = calendar.contains(document.activeElement);
            calendar.innerHTML = updated.innerHTML;
            if (pushHistory) window.history.pushState({}, "", url.href);
            if (restoreFocus) {
                const links = calendar.querySelectorAll("nav a");
                const target = Array.from(links).find((link) => link.textContent === focusLabel)
                    || links[0];
                target?.focus({preventScroll: true});
            }
        } catch (error) {
            if (error.name !== "AbortError") window.location.assign(url.href);
        } finally {
            if (activeRequest === controller) {
                calendar.removeAttribute("aria-busy");
                activeRequest = undefined;
            }
        }
    }

    calendar.addEventListener("click", (event) => {
        const link = event.target.closest(".dashboard-calendar-navigation a");
        if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey
            || event.ctrlKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        showWeek(new URL(link.href), {focusLabel: link.textContent});
    });

    window.addEventListener("popstate", () => {
        showWeek(new URL(window.location.href), {pushHistory: false});
    });
})();
