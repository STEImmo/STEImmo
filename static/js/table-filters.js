(() => {
    let activeRequest;
    let requestNumber = 0;
    let searchTimer;
    let currentParams = new URLSearchParams(window.location.search);

    const filterForms = () => document.querySelectorAll("form[data-table-filter-form]");

    function updateNavigationLinks() {
        for (const link of document.querySelectorAll("a[data-application-segment]")) {
            const url = new URL(link.href, window.location.href);
            const params = new URLSearchParams(currentParams);
            params.set("segment", link.dataset.applicationSegment);
            params.delete("page");
            url.search = params.toString();
            link.href = url.href;
        }

        for (const link of document.querySelectorAll('[data-table-filter-fragment="pagination"] a')) {
            const url = new URL(link.href, window.location.href);
            const page = url.searchParams.get("page");
            url.search = currentParams.toString();
            if (page) url.searchParams.set("page", page);
            link.href = url.href;
        }

        const sortField = document.querySelector('#application-search-filter-form select[name="sort"]');
        for (const link of document.querySelectorAll("a[data-table-filter-navigation]")) {
            const url = new URL(link.href, window.location.href);
            if (link.hasAttribute("data-remove-filter")) {
                url.search = currentParams.toString();
                url.searchParams.delete(link.dataset.removeFilter);
                url.searchParams.delete("page");
            } else if (sortField) {
                // Reset links retain the application context and the latest valid sort.
                const sort = Array.from(sortField.options).find(
                    (option) => option.value === currentParams.get("sort"),
                ) || sortField.options[0];
                url.searchParams.set("sort", sort.value);
            }
            link.href = url.href;
        }
    }

    function updateCurrentParamsFromForm(form, changedControl = null) {
        const formData = new FormData(form);
        const editableControls = Array.from(form.elements).filter(
            (control) => control.name && control.type !== "hidden" && !control.disabled,
        );
        const names = changedControl
            ? new Set([changedControl.name])
            : new Set(editableControls.map((control) => control.name));

        for (const name of names) {
            currentParams.delete(name);
            for (const value of formData.getAll(name)) {
                if (typeof value === "string" && value !== "") currentParams.append(name, value);
            }
        }
        currentParams.delete("page");
        updateNavigationLinks();
    }

    function buildUrl(form) {
        const url = new URL(form.action || window.location.href, window.location.href);
        url.search = currentParams.toString();
        return url;
    }

    function updateFragments(parsedDocument) {
        let foundFragment = false;
        for (const name of [
            "filter-summary", "table-body", "application-count", "pagination",
            "application-breadcrumb", "application-segments",
        ]) {
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

    function setResultsBusy(isBusy) {
        document.querySelectorAll('[data-table-filter-fragment="table-body"]').forEach((tableBody) => {
            if (isBusy) tableBody.setAttribute("aria-busy", "true");
            else tableBody.removeAttribute("aria-busy");
        });
    }

    function cancelPendingRequest() {
        requestNumber += 1;
        activeRequest?.abort();
        activeRequest = undefined;
        setResultsBusy(false);
    }

    async function refreshResults(url, {pushHistory = true} = {}) {
        currentParams = new URLSearchParams(url.searchParams);
        updateNavigationLinks();
        const currentNumber = ++requestNumber;
        activeRequest?.abort();
        const controller = new AbortController();
        activeRequest = controller;
        setResultsBusy(true);

        try {
            const response = await fetch(url, {
                credentials: "same-origin",
                headers: {"X-Requested-With": "XMLHttpRequest"},
                signal: controller.signal,
            });
            if (currentNumber !== requestNumber) return;
            if (!response.ok || response.redirected) {
                window.location.assign(url.href);
                return;
            }
            const responseDocument = new DOMParser().parseFromString(await response.text(), "text/html");
            if (currentNumber !== requestNumber) return;
            // Preserve the focus at response time, including a text field's selection.
            const focusedElement = document.activeElement;
            const selectionStart = focusedElement?.selectionStart;
            const selectionEnd = focusedElement?.selectionEnd;
            const selectionDirection = focusedElement?.selectionDirection;
            if (!updateFragments(responseDocument)) {
                window.location.assign(url.href);
                return;
            }
            updateForms(responseDocument);
            if (pushHistory) window.history.pushState({}, "", url.href);
            updateNavigationLinks();
            if (focusedElement?.id && !focusedElement.isConnected) {
                const replacement = document.getElementById(focusedElement.id);
                replacement?.focus({preventScroll: true});
                if (typeof selectionStart === "number" && replacement?.setSelectionRange) {
                    replacement.setSelectionRange(selectionStart, selectionEnd, selectionDirection);
                }
            }
        } catch (error) {
            if (error.name !== "AbortError" && currentNumber === requestNumber) {
                window.location.assign(url.href);
            }
        } finally {
            if (currentNumber === requestNumber) {
                activeRequest = undefined;
                setResultsBusy(false);
            }
        }
    }

    function requestForm(form) {
        refreshResults(buildUrl(form));
    }

    updateNavigationLinks();

    document.addEventListener("shown", (event) => {
        if (!event.target.matches?.("[data-table-filter-dropdown]")) return;
        event.target.querySelector("select, input:not([type='hidden'])")?.focus();
    });

    document.addEventListener("change", (event) => {
        if (!(event.target instanceof Element)) return;
        const form = event.target.closest("form[data-table-filter-form]");
        if (!form || event.target.matches('input[name="q"]')) return;
        window.clearTimeout(searchTimer);
        updateCurrentParamsFromForm(form, event.target);
        requestForm(form);
    });

    document.addEventListener("input", (event) => {
        if (!(event.target instanceof Element) || !event.target.matches('input[name="q"]')) return;
        const form = event.target.closest("form[data-table-filter-form]");
        if (!form) return;
        window.clearTimeout(searchTimer);
        updateCurrentParamsFromForm(form, event.target);
        cancelPendingRequest();
        searchTimer = window.setTimeout(() => requestForm(form), 350);
    });

    document.addEventListener("submit", (event) => {
        if (!(event.target instanceof HTMLFormElement) || !event.target.matches("form[data-table-filter-form]")) return;
        event.preventDefault();
        window.clearTimeout(searchTimer);
        updateCurrentParamsFromForm(event.target);
        requestForm(event.target);
    });

    document.addEventListener("click", (event) => {
        if (!(event.target instanceof Element)) return;
        if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
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

    window.addEventListener("popstate", () => {
        window.clearTimeout(searchTimer);
        refreshResults(new URL(window.location.href), {pushHistory: false});
    });
})();
