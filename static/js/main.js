// ---- Toasts ------------------------------------------------------------
function showToast(message, type) {
    var container = document.getElementById("toast-container");
    if (!container) return;
    var toast = document.createElement("div");
    toast.className = "toast toast-" + (type || "info");
    toast.setAttribute("role", "status");
    toast.textContent = message;
    container.appendChild(toast);
    scheduleToastRemoval(toast);
}

function scheduleToastRemoval(toast) {
    setTimeout(function () {
        toast.classList.add("toast-hide");
        setTimeout(function () { toast.remove(); }, 300);
    }, 4000);
}

document.querySelectorAll(".toast").forEach(scheduleToastRemoval);

// ---- Show / hide password ---------------------------------------------
document.querySelectorAll("[data-toggle-password]").forEach(function (btn) {
    btn.addEventListener("click", function () {
        var field = btn.closest(".password-field");
        var input = field.querySelector("input");
        var show = input.type === "password";
        input.type = show ? "text" : "password";
        field.classList.toggle("is-visible", show);
        btn.setAttribute("aria-pressed", show ? "true" : "false");
        btn.setAttribute("aria-label", show ? "Hide password" : "Show password");
    });
});

// ---- Password strength validation -------------------------------------
var PASSWORD_RULES = {
    length: function (p) { return p.length >= 8; },
    upper: function (p) { return /[A-Z]/.test(p); },
    lower: function (p) { return /[a-z]/.test(p); },
    number: function (p) { return /[0-9]/.test(p); },
    special: function (p) { return /[^A-Za-z0-9]/.test(p); }
};

var PASSWORD_MESSAGES = {
    length: "Password must be at least 8 characters.",
    upper: "Password must contain an uppercase letter.",
    lower: "Password must contain a lowercase letter.",
    number: "Password must contain a number.",
    special: "Password must contain a special character."
};

document.querySelectorAll("[data-password-form]").forEach(function (form) {
    var password = form.querySelector("[data-password-new]");
    var confirm = form.querySelector("[data-password-confirm]");
    var rules = form.querySelectorAll("[data-rule]");
    var errorBox = form.parentElement.querySelector("[data-form-error]");

    function updateRules() {
        rules.forEach(function (li) {
            li.classList.toggle("is-met", PASSWORD_RULES[li.dataset.rule](password.value));
        });
    }

    function showError(message) {
        errorBox.textContent = message;
        errorBox.hidden = false;
    }

    password.addEventListener("input", updateRules);
    updateRules();

    form.addEventListener("submit", function (event) {
        var message = null;
        form.querySelectorAll("input[required]").forEach(function (input) {
            if (!message && !input.value.trim()) message = "All fields are required.";
        });
        if (!message) {
            Object.keys(PASSWORD_RULES).forEach(function (key) {
                if (!message && !PASSWORD_RULES[key](password.value)) message = PASSWORD_MESSAGES[key];
            });
        }
        if (!message && confirm.value !== password.value) message = "Passwords do not match.";
        if (message) {
            event.preventDefault();
            showError(message);
        }
    });
});

// ---- Back/forward cache -----------------------------------------------
// A page restored from the browser's back/forward cache skips the server, so
// reload it to re-check the session (e.g. Back to /profile after signing out).
window.addEventListener("pageshow", function (event) {
    if (event.persisted) window.location.reload();
});
