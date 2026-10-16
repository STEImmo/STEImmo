(() => {
    let activeRequest;
    let requestNumber = 0;
    let searchTimer;

    const filterForms = () => document.querySelectorAll("form[data-table-filter-form]");

    function buildUrl(form) {
        const url = new URL(form.action || window.location.href, window.location.href);
        const params = new URLSearchParams();
        for (const [name, value] of new FormData(form).entries()) {
            if (typeof value === "string" && value !== "") params.append(name, value);
        }
        params.delete("page");
        url.search = params.toString();
        return url;
    }

    function updateFragments(parsedDocument) {
        let foundFragment = false;
        for (const name of ["filter-summary", "table-body", "application-count", "pagination"]) {
            const selector = `[data-table-filter-fragment="${name}"]`;
            const currentFragments = document.querySelectorAll(selector);
            const newFragment = parsedDocument.querySelector(selector);
            if (!newFragment) continue;
            foundFragment ||= currentFragments.length > 0;
            for (const current of currentFragments) current.innerHTML = newFragment.innerHTML;
        }
        return foundFragment;
    }

    function updateForms(parsedDocument) {
        for (const form of filterForms()) {
            const updatedForm = parsedDocument.getElementById(form.id);
            if (updatedForm) form.innerHTML = updatedForm.innerHTML;
        }
    }

    async function refreshResults(url, {pushHistory = true} = {}) {
        const currentNumber = ++requestNumber;
        activeRequest?.abort();
        activeRequest = new AbortController();
        const focusedId = document.activeElement?.id;
        document.querySelectorAll('[data-table-filter-fragment="table-body"]').forEach((tableBody) => {
            tableBody.setAttribute("aria-busy", "true");
        });

        try {
            const response = await fetch(url, {
                credentials: "same-origin",
                headers: {"X-Requested-With": "XMLHttpRequest"},
                signal: activeRequest.signal,
            });
            if (!response.ok || response.redirected) {
                window.location.assign(url.href);
                return;
            }
            const responseDocument = new DOMParser().parseFromString(await response.text(), "text/html");
            if (!updateFragments(responseDocument)) {
                window.location.assign(url.href);
                return;
            }
            updateForms(responseDocument);
            if (pushHistory) window.history.pushState({}, "", url.href);
            if (focusedId) document.getElementById(focusedId)?.focus({preventScroll: true});
        } catch (error) {
            if (error.name !== "AbortError") window.location.assign(url.href);
        } finally {
            if (currentNumber === requestNumber) activeRequest = undefined;
        }
    }

    function requestForm(form) {
        refreshResults(buildUrl(form));
    }

    document.addEventListener("shown", (event) => {
        if (!event.target.matches?.("[data-table-filter-dropdown]")) return;
        event.target.querySelector("select, input:not([type='hidden'])")?.focus();
    });

    document.addEventListener("change", (event) => {
        if (!(event.target instanceof Element)) return;
        const form = event.target.closest("form[data-table-filter-form]");
        if (!form || event.target.matches('input[name="q"]')) return;
        window.clearTimeout(searchTimer);
        requestForm(form);
    });

    document.addEventListener("input", (event) => {
        if (!(event.target instanceof Element) || !event.target.matches('input[name="q"]')) return;
        const form = event.target.closest("form[data-table-filter-form]");
        if (!form) return;
        window.clearTimeout(searchTimer);
        searchTimer = window.setTimeout(() => requestForm(form), 350);
    });

    document.addEventListener("submit", (event) => {
        if (!(event.target instanceof HTMLFormElement) || !event.target.matches("form[data-table-filter-form]")) return;
        event.preventDefault();
        window.clearTimeout(searchTimer);
        requestForm(event.target);
    });

    document.addEventListener("click", (event) => {
        if (!(event.target instanceof Element)) return;
        const link = event.target.closest("a[data-table-filter-navigation]");
        if (!link || link.origin !== window.location.origin) return;
        event.preventDefault();
        window.clearTimeout(searchTimer);
        refreshResults(new URL(link.href));
    });

    window.addEventListener("keydown", (event) => {
        if (event.key !== "Escape" || !(event.target instanceof Element)) return;
        const dropdown = event.target.closest("[data-table-filter-dropdown]");
        if (!dropdown) return;
        window.UIkit.dropdown(dropdown).hide(false);
        document.getElementById(dropdown.getAttribute("aria-labelledby"))?.focus();
    });

    window.addEventListener("popstate", () => refreshResults(new URL(window.location.href), {pushHistory: false}));
})();
