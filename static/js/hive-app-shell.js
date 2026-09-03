(() => {
    const body = document.body;
    if (!body.classList.contains("hive-consultant-mode")) return;

    const sidebar = document.getElementById("hiveSidebar");
    const openButton = document.getElementById("hiveSidebarOpen");
    const closeButton = document.getElementById("hiveSidebarClose");
    const scrim = document.getElementById("hiveSidebarScrim");

    const setNavigationOpen = (open) => {
        body.classList.toggle("hive-nav-open", open);
        openButton?.setAttribute("aria-expanded", open ? "true" : "false");
        if (open) {
            closeButton?.focus();
        } else if (document.activeElement === closeButton) {
            openButton?.focus();
        }
    };

    openButton?.addEventListener("click", () => setNavigationOpen(true));
    closeButton?.addEventListener("click", () => setNavigationOpen(false));
    scrim?.addEventListener("click", () => setNavigationOpen(false));
    sidebar?.querySelectorAll("a").forEach((link) => {
        link.addEventListener("click", () => {
            if (window.matchMedia("(max-width: 900px)").matches) setNavigationOpen(false);
        });
    });

    const dialog = document.getElementById("hiveCommandDialog");
    const trigger = document.getElementById("hiveCommandTrigger");
    const input = document.getElementById("hiveCommandInput");
    const results = document.getElementById("hiveCommandResults");
    const empty = document.getElementById("hiveCommandEmpty");
    let commandReturnFocus = null;

    const commandLinks = Array.from(results?.querySelectorAll("a") || []);

    const filterCommands = () => {
        const query = (input?.value || "").trim().toLowerCase();
        let visible = 0;
        commandLinks.forEach((link) => {
            const haystack = (link.dataset.commandLabel || link.textContent || "").toLowerCase();
            const show = !query || haystack.includes(query);
            link.hidden = !show;
            if (show) visible += 1;
        });
        if (empty) empty.hidden = visible !== 0;
    };

    const openCommand = () => {
        if (!dialog) return;
        commandReturnFocus = document.activeElement;
        dialog.hidden = false;
        body.classList.add("hive-command-open");
        if (input) {
            input.value = "";
            filterCommands();
            window.requestAnimationFrame(() => input.focus());
        }
    };

    const closeCommand = () => {
        if (!dialog || dialog.hidden) return;
        dialog.hidden = true;
        body.classList.remove("hive-command-open");
        if (commandReturnFocus instanceof HTMLElement) commandReturnFocus.focus();
    };

    trigger?.addEventListener("click", openCommand);
    input?.addEventListener("input", filterCommands);
    dialog?.addEventListener("click", (event) => {
        if (event.target === dialog) closeCommand();
    });

    document.addEventListener("keydown", (event) => {
        const commandShortcut = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k";
        if (commandShortcut) {
            event.preventDefault();
            if (dialog?.hidden) openCommand(); else closeCommand();
            return;
        }

        if (event.key === "Escape") {
            if (dialog && !dialog.hidden) {
                event.preventDefault();
                closeCommand();
                return;
            }
            if (body.classList.contains("hive-nav-open")) {
                event.preventDefault();
                setNavigationOpen(false);
            }
        }
    });

    window.addEventListener("resize", () => {
        if (!window.matchMedia("(max-width: 900px)").matches) setNavigationOpen(false);
    });
})();
