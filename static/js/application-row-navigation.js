(() => {
    const table = document.querySelector(".application-table");
    if (!table) return;

    table.addEventListener("click", (event) => {
        if (!(event.target instanceof Element)) return;
        const row = event.target.closest("[data-application-row]");
        if (!row || event.target.closest("a, button, input, select, textarea, label, summary")) return;
        if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        if (window.getSelection()?.toString()) return;
        row.querySelector("[data-application-detail]")?.click();
    });
})();
