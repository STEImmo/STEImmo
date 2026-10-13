(() => {
    const forms = document.querySelectorAll("[data-viewing-time-form]");
    const berlinClock = new Intl.DateTimeFormat("en-CA", {
        timeZone: "Europe/Berlin",
        year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit", hourCycle: "h23",
    });
    const asMinutes = (value) => value ? Number(value.slice(0, 2)) * 60 + Number(value.slice(3, 5)) : null;
    const asTime = (minutes) => `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
    const shiftDay = (day, amount) => {
        const value = new Date(`${day}T12:00:00Z`);
        value.setUTCDate(value.getUTCDate() + amount);
        return value.toISOString().slice(0, 10);
    };
    const setLimit = (input, limit, value) => {
        // Reassigning an unchanged time limit resets the browser's hour typing buffer.
        if (input[limit] !== value) input[limit] = value;
    };

    forms.forEach((form) => {
        const date = form.elements.namedItem("date");
        const start = form.elements.namedItem("start_time");
        const end = form.elements.namedItem("end_time");
        const action = form.elements.namedItem("action");
        const reason = form.elements.namedItem("reason");
        if (!date || !start || !end || !action || !reason) return;
        const parsedNow = Date.parse(form.dataset.currentTime);
        const serverNow = Number.isFinite(parsedNow) ? parsedNow : Date.now();
        const loadedAt = performance.now();
        const fields = [date, start, end, reason].map((input) => {
            const error = document.createElement("span");
            error.id = `${input.id}_live_error`;
            error.className = "uk-display-block uk-text-danger uk-text-small";
            error.setAttribute("aria-live", "polite");
            input.insertAdjacentElement("afterend", error);
            return {input, error, descriptions: input.getAttribute("aria-describedby") || ""};
        });

        const validate = () => {
            const now = new Date(serverNow + performance.now() - loadedAt);
            const parts = Object.fromEntries(berlinClock.formatToParts(now).map((part) => [part.type, part.value]));
            const today = `${parts.year}-${parts.month}-${parts.day}`;
            const currentMinute = Number(parts.hour) * 60 + Number(parts.minute);
            const record = action.value === "record";
            const sameDay = date.value === today;
            const startMinute = asMinutes(start.value);
            const endMinute = asMinutes(end.value);
            const messages = new Map();

            // A same-day appointment needs at least two distinct minute values.
            setLimit(date, "min", record ? "" : currentMinute >= 1438 ? shiftDay(today, 1) : today);
            setLimit(date, "max", record ? currentMinute === 0 ? shiftDay(today, -1) : today : "");
            setLimit(start, "min", !record && sameDay && currentMinute < 1438 ? asTime(currentMinute + 1) : "");
            setLimit(start, "max", record && sameDay && currentMinute > 0 ? asTime(Math.min(1438, currentMinute - 1)) : "23:58");
            const earliestEnd = Math.max(
                startMinute !== null ? startMinute + 1 : 1,
                !record && sameDay ? currentMinute + 2 : 1,
            );
            setLimit(end, "min", asTime(Math.min(1439, earliestEnd)));
            setLimit(end, "max", record && sameDay ? asTime(currentMinute) : "23:59");
            reason.required = record;

            if (date.value && !record && date.value < date.min) {
                messages.set(date, "Bitte wählen Sie einen Tag, an dem noch ein zukünftiger Termin möglich ist.");
            } else if (date.value && record && date.value > date.max) {
                messages.set(date, "Ein Nachtrag muss bereits vollständig vergangen sein.");
            }
            if (startMinute !== null) {
                if (!record && sameDay && startMinute <= currentMinute) {
                    messages.set(start, "Der Beginn muss nach der aktuellen Uhrzeit in Berlin liegen.");
                } else if (record && sameDay && startMinute >= currentMinute) {
                    messages.set(start, "Der Beginn einer nachgetragenen Besichtigung muss bereits vergangen sein.");
                } else if (startMinute > 1438) {
                    messages.set(start, "Für das Ende muss am selben Tag noch mindestens eine Minute verbleiben.");
                }
            }
            if (endMinute !== null) {
                if (startMinute !== null && endMinute <= startMinute) {
                    messages.set(end, "Das Ende muss nach dem Beginn liegen.");
                } else if (!record && sameDay && endMinute <= currentMinute + 1) {
                    messages.set(end, "Das Ende muss nach einem noch zukünftigen Beginn liegen.");
                } else if (record && sameDay && endMinute > currentMinute) {
                    messages.set(end, "Das Ende einer nachgetragenen Besichtigung darf nicht in der Zukunft liegen.");
                }
            }

            fields.forEach(({input, error, descriptions}) => {
                const message = messages.get(input) || "";
                input.setCustomValidity(message);
                input.classList.toggle("uk-form-danger", Boolean(message));
                if (message) input.setAttribute("aria-invalid", "true");
                else input.removeAttribute("aria-invalid");
                input.setAttribute("aria-describedby", [descriptions, message ? error.id : ""].filter(Boolean).join(" "));
                if (error.textContent !== message) error.textContent = message;
                error.hidden = !message;
            });
            form.querySelectorAll('button[type="submit"]').forEach((button) => {
                button.disabled = messages.size > 0;
            });
        };
        [start, end].forEach((input) => {
            input.addEventListener("keydown", (event) => {
                if (
                    /^\d$/.test(event.key)
                    && !event.ctrlKey && !event.metaKey && !event.altKey
                    && !input.value && !input.validity.badInput
                ) {
                    // Populate real minutes before the browser edits the hour
                    // segment; its grey placeholder is not a submitted value.
                    input.value = "00:00";
                    validate();
                }
            });
        });
        form.addEventListener("input", validate);
        form.addEventListener("change", validate);
        form.addEventListener("submit", (event) => {
            validate();
            if (!form.checkValidity()) {
                event.preventDefault();
                form.reportValidity();
            }
        });
        validate();
        // Keep a selected start time valid as the server-based clock advances.
        window.setInterval(validate, 1000);
    });
})();
