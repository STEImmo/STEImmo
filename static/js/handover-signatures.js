(() => {
    const form = document.getElementById("handover-signing-form");
    if (!form) return;
    const pads = new Map();
    let submitting = false, completed = false, stale = false;
    form.querySelectorAll("[data-signature-pad]").forEach(element => {
        const canvas = element.querySelector("canvas"), context = canvas.getContext("2d");
        const pad = {canvas, dirty: false, active: null, previous: null};
        pad.clear = () => {
            context.fillStyle = "white";
            context.fillRect(0, 0, canvas.width, canvas.height);
            pad.dirty = false;
            pad.active = null;
        };
        pad.clear();
        context.strokeStyle = "#14202e";
        context.lineWidth = 4;
        context.lineCap = "round";
        context.lineJoin = "round";
        const point = event => {
            const rect = canvas.getBoundingClientRect();
            return [(event.clientX - rect.left) * canvas.width / rect.width,
                (event.clientY - rect.top) * canvas.height / rect.height];
        };
        canvas.addEventListener("pointerdown", event => {
            if (submitting || stale || pad.active !== null || event.button !== 0) return;
            event.preventDefault();
            pad.active = event.pointerId;
            pad.previous = point(event);
            canvas.setPointerCapture(event.pointerId);
        });
        canvas.addEventListener("pointermove", event => {
            if (pad.active !== event.pointerId || submitting || stale) return;
            const current = point(event);
            context.beginPath();
            context.moveTo(...pad.previous);
            context.lineTo(...current);
            context.stroke();
            pad.previous = current;
            pad.dirty = true;
        });
        for (const eventName of ["pointerup", "pointercancel", "lostpointercapture"]) {
            canvas.addEventListener(eventName, event => {
                if (pad.active === event.pointerId) pad.active = null;
            });
        }
        element.querySelector("[data-signature-clear]").addEventListener("click", () => {
            if (!submitting) pad.clear();
        });
        pads.set(element.dataset.signaturePad, pad);
    });
    const mode = document.getElementById("tenant-mode"), reason = form.elements.reason;
    mode.addEventListener("change", () => {
        pads.get("mieter").clear();
        reason.value = "";
        const missing = mode.value === "missing";
        document.getElementById("tenant-signature").hidden = missing;
        document.getElementById("tenant-reason").hidden = !missing;
        reason.required = missing;
    });
    window.addEventListener("beforeunload", event => {
        if (!completed && [...pads.values()].some(p => p.dirty)) {
            event.preventDefault();
            event.returnValue = "";
        }
    });
    const error = document.getElementById("signature-error");
    const submit = document.getElementById("signature-submit");
    const reload = document.getElementById("signature-reload");
    const showError = message => { error.textContent = message; error.hidden = false; error.focus(); };
    reload.addEventListener("click", () => { completed = true; window.location.reload(); });
    submit.disabled = false;
    form.addEventListener("submit", async event => {
        event.preventDefault();
        if (submitting || stale) return;
        if (!pads.get("mitarbeiter").dirty || (mode.value === "signed" && !pads.get("mieter").dirty)) {
            showError("Bitte leisten Sie die erforderlichen Unterschriften.");
            return;
        }
        submitting = true;
        submit.disabled = true;
        error.hidden = true;
        const data = new FormData(form);
        const controls = [...form.querySelectorAll("button, input, select, textarea")];
        controls.forEach(control => { control.disabled = true; });
        try {
            for (const [role, pad] of pads) {
                if (role === "mieter" && data.get("tenant_mode") === "missing") continue;
                const blob = await new Promise(resolve => pad.canvas.toBlob(resolve, "image/png"));
                if (!blob) throw new Error("Die Unterschrift konnte nicht gelesen werden.");
                data.append(role, blob, `${role}.png`);
            }
            const response = await fetch(form.action, {method: "POST", body: data, credentials: "same-origin", headers: {"Accept": "application/json"}});
            if (!response.headers.get("content-type")?.includes("application/json")) {
                throw new Error("Die Sitzung oder Verbindung ist unterbrochen. Bitte prüfen Sie Ihre Anmeldung und versuchen Sie es erneut.");
            }
            const result = await response.json();
            if (response.ok && result.redirect) {
                completed = true;
                window.location.assign(result.redirect);
                return;
            }
            if (result.reload) {
                stale = true;
                pads.forEach(pad => pad.clear());
                reload.hidden = false;
            }
            showError(result.error || "Der Abschluss ist fehlgeschlagen. Bitte erneut versuchen.");
        } catch {
            showError("Übertragung unterbrochen. Bitte Verbindung und Anmeldung prüfen und erneut versuchen. Die Unterschriften bleiben auf dieser Seite erhalten.");
        } finally {
            submitting = false;
            controls.forEach(control => { control.disabled = false; });
            submit.disabled = stale || completed;
        }
    });
})();
