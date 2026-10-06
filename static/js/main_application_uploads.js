(() => {
    const form = document.querySelector("[data-proof-upload-form]");
    if (!form) {
        return;
    }

    const fields = Array.from(form.querySelectorAll("[data-proof-upload-field]"))
        .map((field) => {
            const input = field.querySelector("[data-proof-upload-input]");
            return {
                field,
                input,
                list: field.querySelector("[data-proof-selection-list]"),
                label: field.querySelector("[data-proof-selection-label]"),
                error: field.querySelector("[data-proof-selection-error]"),
                maxFiles: Number(input?.dataset.maxFiles || 10),
                maxFileBytes: Number(input?.dataset.maxFileSize ?? 8 * 1024 * 1024),
                maxTotalBytes: Number(input?.dataset.maxTotalSize ?? 25 * 1024 * 1024),
                existingCount: field.querySelectorAll("[data-proof-existing-name]").length,
                selectedFiles: [],
                selectionError: "",
            };
        })
        .filter((entry) => entry.input && entry.list && entry.error);

    if (!fields.length) {
        return;
    }

    const normalizeFileName = (filename) =>
        filename.normalize("NFKC").trim().toUpperCase().toLowerCase();
    const existingNames = new Set(
        Array.from(document.querySelectorAll("[data-proof-existing-name]"))
            .map((element) => normalizeFileName(element.textContent || ""))
            .filter(Boolean),
    );

    const assignFiles = (input, files) => {
        const transfer = new DataTransfer();
        files.forEach((file) => transfer.items.add(file));
        input.files = transfer.files;
    };
    const totalError = form.querySelector("[data-proof-total-size-error]");
    const validationModal = document.querySelector("[data-proof-upload-modal]");
    const validationModalMessage = document.querySelector("[data-proof-upload-modal-message]");

    const renderSelections = () => {
        const usedNames = new Set(existingNames);
        const duplicatesByField = new Map(fields.map((entry) => [entry, []]));
        const fileEntries = new Map();
        let totalSelectedBytes = 0;

        for (const entry of fields) {
            const files = Array.from(entry.input.files || []);
            totalSelectedBytes += files.reduce((total, file) => total + file.size, 0);
            const oversizedFiles = files.filter((file) => file.size > entry.maxFileBytes);
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
            fileEntries.set(entry, { files, duplicateFlags, oversizedFiles });
        }

        let hasErrors = false;
        const totalSizeLimit = fields[0]?.maxTotalBytes ?? 0;
        const overTotalSizeLimit = totalSelectedBytes > totalSizeLimit;
        for (const entry of fields) {
            const { files, duplicateFlags, oversizedFiles } = fileEntries.get(entry);
            const duplicateNames = duplicatesByField.get(entry);
            const totalFiles = entry.existingCount + files.length;
            const overFileLimit = totalFiles > entry.maxFiles;
            const atFileLimit = totalFiles === entry.maxFiles;
            const fieldHasErrors =
                duplicateNames.length > 0 ||
                oversizedFiles.length > 0 ||
                overFileLimit ||
                Boolean(entry.selectionError);
            const errorMessages = [];
            hasErrors ||= fieldHasErrors;
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
                errorMessages.push(
                    `Datei „${duplicateNames[0]}“ wird bereits in dieser Main-Bewerbung `
                    + "verwendet. Entfernen Sie die Datei aus der Auswahl oder benennen Sie sie um.",
                );
            }
            if (oversizedFiles.length) {
                const fileNames = oversizedFiles.map((file) => `„${file.name}“`).join(", ");
                errorMessages.push(
                    `${fileNames} ${oversizedFiles.length === 1 ? "überschreitet" : "überschreiten"} `
                    + `das Dateilimit von ${formatMiB(entry.maxFileBytes)}.`,
                );
            }
            if (overFileLimit) {
                errorMessages.push(
                    `Pro Nachweiskategorie sind höchstens ${entry.maxFiles} Dateien erlaubt. `
                    + "Entfernen Sie eine Datei aus der Auswahl.",
                );
            } else if (atFileLimit) {
                errorMessages.push(
                    `Das Maximum von ${entry.maxFiles} Dateien für diese Kategorie ist erreicht. `
                    + "Weitere Dateien können Sie erst nach dem Entfernen einer Datei hinzufügen.",
                );
            }
            if (entry.selectionError) {
                errorMessages.push(entry.selectionError);
            }

            entry.error.textContent = errorMessages.join(" ");
            entry.error.hidden = errorMessages.length === 0;
            const informationalLimitNotice =
                atFileLimit && !overFileLimit && !duplicateNames.length && !entry.selectionError;
            entry.error.classList.toggle("uk-text-warning", informationalLimitNotice);
            entry.error.classList.toggle("uk-text-danger", !informationalLimitNotice);
            if (fieldHasErrors) {
                entry.input.setAttribute("aria-invalid", "true");
            } else {
                entry.input.removeAttribute("aria-invalid");
            }
        }

        if (totalError) {
            totalError.hidden = !overTotalSizeLimit;
            totalError.textContent = overTotalSizeLimit
                ? `Die ausgewählten Dateien überschreiten zusammen das Gesamtlimit von `
                    + `${formatMiB(totalSizeLimit)}. Entfernen Sie Dateien aus der Auswahl.`
                : "";
        }
        hasErrors ||= overTotalSizeLimit;

        return hasErrors;
    };

    const formatMiB = (bytes) => {
        const formatted = new Intl.NumberFormat("de-DE", { maximumFractionDigits: 1 })
            .format(bytes / (1024 * 1024));
        return `${formatted} MiB`;
    };

    const showValidationPopup = () => {
        const messages = fields
            .filter((entry) => !entry.error.hidden)
            .map((entry) => entry.error.textContent);
        if (totalError && !totalError.hidden) {
            messages.push(totalError.textContent);
        }
        const message = `Die Dateien wurden nicht gespeichert. ${messages.join(" ")}`;

        if (validationModal && validationModalMessage && window.UIkit?.modal) {
            validationModalMessage.textContent = message;
            window.UIkit.modal(validationModal).show();
        } else {
            window.alert(message);
        }
    };

    for (const entry of fields) {
        entry.input.addEventListener("change", () => {
            const newlySelectedFiles = Array.from(entry.input.files || []);
            const combinedFiles = [...entry.selectedFiles, ...newlySelectedFiles];

            try {
                assignFiles(entry.input, combinedFiles);
                entry.selectedFiles = combinedFiles;
                entry.selectionError = "";
                renderSelections();
            } catch {
                entry.selectedFiles = newlySelectedFiles;
                entry.selectionError =
                    "Dateien konnten nicht angehängt werden. Bitte wählen Sie alle Dateien "
                    + "gemeinsam aus oder verwenden Sie einen aktuellen Browser.";
                renderSelections();
            }
        });
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
            const remainingFiles = Array.from(entry.input.files || []).filter(
                (_file, index) => index !== removeIndex,
            );
            assignFiles(entry.input, remainingFiles);
            entry.selectedFiles = remainingFiles;
            entry.selectionError = "";
            renderSelections();
            entry.input.focus();
        } catch {
            entry.input.value = "";
            entry.selectedFiles = [];
            entry.selectionError =
                "Die Auswahl wurde geleert. Wählen Sie die gewünschten Dateien bitte erneut aus.";
            renderSelections();
        }
    });

    form.addEventListener("submit", (event) => {
        if (!renderSelections()) {
            return;
        }

        event.preventDefault();
        fields.find((entry) => entry.input.getAttribute("aria-invalid") === "true")?.input.focus();
        showValidationPopup();
    });

    renderSelections();
})();
