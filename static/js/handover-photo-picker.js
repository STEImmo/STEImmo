(() => {
    const selections = new WeakMap();
    const key = (file) => `${file.name}:${file.size}:${file.lastModified}`;

    const update = (input, files) => {
        const previous = selections.get(input);
        previous?.urls.forEach((url) => URL.revokeObjectURL(url));
        const container = input.closest("[data-photo-selection]");
        const previews = container.querySelector("[data-photo-previews]");
        previews.replaceChildren();
        const urls = [];
        selections.set(input, {files, urls});
        container.querySelector("[data-photo-clear]").hidden = files.length === 0;
        container.querySelector("[data-photo-count]").textContent = files.length
            ? `${files.length} Foto${files.length === 1 ? "" : "s"} ausgewählt. Beim Speichern werden sie hochgeladen.`
            : "Mehrere Fotos auswählen oder nacheinander hinzufügen.";
        files.forEach((file, index) => {
            const cell = document.createElement("div");
            const figure = document.createElement("figure");
            figure.className = "uk-margin-remove";
            const url = URL.createObjectURL(file);
            urls.push(url);
            const image = document.createElement("img");
            image.className = "handover-photo-thumbnail uk-border-rounded";
            image.src = url;
            image.alt = `Vorschau: ${file.name}`;
            const caption = document.createElement("figcaption");
            caption.className = "uk-text-meta uk-text-break";
            caption.textContent = file.name;
            const remove = document.createElement("button");
            remove.type = "button";
            remove.className = "uk-button uk-button-text uk-text-danger";
            remove.textContent = "Auswahl entfernen";
            remove.setAttribute("aria-label", `${file.name} aus der Auswahl entfernen`);
            remove.addEventListener("click", () => {
                const remaining = selections.get(input).files.filter((_, i) => i !== index);
                if (replaceFiles(input, remaining)) update(input, remaining);
            });
            figure.append(image, caption, remove);
            cell.append(figure);
            previews.append(cell);
        });
    };

    const replaceFiles = (input, files) => {
        if (!files.length) {
            input.value = "";
            return true;
        }
        if (typeof DataTransfer !== "function") return false;
        const transfer = new DataTransfer();
        files.forEach((file) => transfer.items.add(file));
        input.files = transfer.files;
        return true;
    };

    document.addEventListener("change", (event) => {
        const input = event.target;
        if (input.type !== "file" || !input.closest("[data-photo-selection]")) return;
        const selected = Array.from(input.files);
        const previous = selections.get(input)?.files || [];
        const merged = Array.from(new Map([...previous, ...selected].map((file) => [key(file), file])).values());
        update(input, replaceFiles(input, merged) ? merged : selected);
    });
    document.addEventListener("click", (event) => {
        const clear = event.target.closest("[data-photo-clear]");
        if (!clear) return;
        const input = clear.closest("[data-photo-selection]").querySelector('input[type="file"]');
        input.value = "";
        update(input, []);
    });
})();
