(() => {
    const form = document.querySelector("[data-proof-upload-form]");
    if (!form) {
        return;
    }

    const fields = Array.from(form.querySelectorAll("[data-proof-upload-field]"))
        .map((field) => ({
            field,
            input: field.querySelector("[data-proof-upload-input]"),
            list: field.querySelector("[data-proof-selection-list]"),
            label: field.querySelector("[data-proof-selection-label]"),
            error: field.querySelector("[data-proof-selection-error]"),
        }))
        .filter((entry) => entry.input && entry.list && entry.error);

    if (!fields.length) {
        return;
    }

    const normalizeFileName = (filename) =>
        filename.normalize("NFKC").trim().toUpperCase().toLowerCase();
    const existingNames = new Set(
        Array.from(form.querySelectorAll("[data-proof-existing-name]"))
            .map((element) => normalizeFileName(element.textContent || ""))
            .filter(Boolean),
    );

    const renderSelections = () => {
        const usedNames = new Set(existingNames);
        const duplicatesByField = new Map(fields.map((entry) => [entry, []]));
        const fileEntries = new Map();

        for (const entry of fields) {
            const files = Array.from(entry.input.files || []);
            const duplicateFlags = files.map((file) => {
                const name = normalizeFileName(file.name);
                const duplicate = usedNames.has(name);
                if (!duplicate) {
                    usedNames.add(name);
                } else {
                    duplicatesByField.get(entry).push(file.name);
                }
                return duplicate;
            });
            fileEntries.set(entry, { files, duplicateFlags });
        }

        let hasDuplicates = false;
        for (const entry of fields) {
            const { files, duplicateFlags } = fileEntries.get(entry);
            const duplicateNames = duplicatesByField.get(entry);
            hasDuplicates ||= duplicateNames.length > 0;
            entry.list.replaceChildren();
            entry.label.hidden = files.length === 0;

            files.forEach((file, index) => {
                const item = document.createElement("li");
                item.className = "uk-flex uk-flex-between uk-flex-middle uk-flex-wrap";

                const name = document.createElement("span");
                name.textContent = file.name;
                item.append(name);

                if (duplicateFlags[index]) {
                    const warning = document.createElement("span");
                    warning.className = "uk-text-danger uk-text-small uk-margin-small-left";
                    warning.textContent = "Dateiname bereits verwendet";
                    item.append(warning);
                }

                const removeButton = document.createElement("button");
                removeButton.type = "button";
                removeButton.className = "uk-button uk-button-default uk-button-small";
                removeButton.dataset.proofRemoveSelection = String(index);
                removeButton.setAttribute(
                    "aria-label",
                    `Datei ${file.name} aus der Auswahl entfernen`,
                );
                removeButton.textContent = "Aus Auswahl entfernen";
                item.append(removeButton);
                entry.list.append(item);
            });

            if (duplicateNames.length) {
                entry.error.textContent =
                    `Datei „${duplicateNames[0]}“ wird bereits in dieser Main-Bewerbung `
                    + "verwendet. Entfernen Sie die Datei aus der Auswahl oder benennen Sie sie um.";
                entry.error.hidden = false;
                entry.input.setAttribute("aria-invalid", "true");
            } else {
                entry.error.textContent = "";
                entry.error.hidden = true;
                entry.input.removeAttribute("aria-invalid");
            }
        }

        return hasDuplicates;
    };

    for (const entry of fields) {
        entry.input.addEventListener("change", renderSelections);
    }

    form.addEventListener("click", (event) => {
        const button = event.target.closest("[data-proof-remove-selection]");
        if (!button) {
            return;
        }

        const entry = fields.find(({ field }) => field.contains(button));
        if (!entry) {
            return;
        }

        const removeIndex = Number(button.dataset.proofRemoveSelection);
        try {
            const remainingFiles = new DataTransfer();
            Array.from(entry.input.files || []).forEach((file, index) => {
                if (index !== removeIndex) {
                    remainingFiles.items.add(file);
                }
            });
            entry.input.files = remainingFiles.files;
            renderSelections();
            entry.input.focus();
        } catch {
            entry.input.value = "";
            renderSelections();
            entry.error.textContent =
                "Die Auswahl wurde geleert. Wählen Sie die gewünschten Dateien bitte erneut aus.";
            entry.error.hidden = false;
        }
    });

    form.addEventListener("submit", (event) => {
        if (!renderSelections()) {
            return;
        }

        event.preventDefault();
        fields.find((entry) => duplicatesByFieldHasFiles(entry))?.input.focus();
    });

    function duplicatesByFieldHasFiles(entry) {
        return entry.error && !entry.error.hidden;
    }

    renderSelections();
})();
