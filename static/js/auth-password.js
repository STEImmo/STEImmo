(() => {
    document.querySelectorAll("[data-password-toggle]").forEach((button) => {
        const input = document.getElementById(button.dataset.passwordToggle);
        if (!input) return;
        button.hidden = false;
        button.addEventListener("click", () => {
            const show = input.type === "password";
            input.type = show ? "text" : "password";
            button.textContent = show ? "Verbergen" : "Anzeigen";
            button.setAttribute("aria-pressed", String(show));
            button.setAttribute("aria-label", `${button.dataset.passwordLabel} ${show ? "verbergen" : "anzeigen"}`);
        });
    });
})();
