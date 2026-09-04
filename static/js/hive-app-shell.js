(() => {
    const body = document.body;
    if (!body.classList.contains("hive-consultant-mode")) return;

    const sidebar = document.getElementById("hiveSidebar");
    const openButton = document.getElementById("hiveSidebarOpen");
    const closeButton = document.getElementById("hiveSidebarClose");
    const scrim = document.getElementById("hiveSidebarScrim");
    const isClientsPage = window.location.pathname === "/clients";

    const primaryNavGroup = sidebar?.querySelector(".hive-app-nav-group");
    if (primaryNavGroup && !primaryNavGroup.querySelector('a[href="/clients"]')) {
        const clientsLink = document.createElement("a");
        clientsLink.href = "/clients";
        clientsLink.className = `hive-app-nav-item${isClientsPage ? " is-active" : ""}`;
        if (isClientsPage) clientsLink.setAttribute("aria-current", "page");
        clientsLink.innerHTML = `
            <span class="hive-app-nav-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
                    <path d="M5 20V7l7-3 7 3v13"/><path d="M9 10h2m2 0h2M9 14h2m2 0h2M10 20v-3h4v3"/>
                </svg>
            </span>
            <span>Clients</span>`;
        const appsLink = Array.from(primaryNavGroup.querySelectorAll("a")).find((link) =>
            (link.textContent || "").trim().startsWith("Apps")
        );
        if (appsLink) primaryNavGroup.insertBefore(clientsLink, appsLink);
        else primaryNavGroup.appendChild(clientsLink);
    }

    if (isClientsPage) {
        const pageName = document.querySelector(".hive-app-page-name");
        if (pageName) pageName.textContent = "Clients";
    }

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
    let searchTimer = null;
    let searchSequence = 0;
    let activeResultIndex = -1;

    if (input) input.placeholder = "Search HIVE records or navigation…";

    if (results && !results.querySelector('a[href="/clients"]')) {
        const clientsCommand = document.createElement("a");
        clientsCommand.href = "/clients";
        clientsCommand.dataset.commandLabel = "Clients client accounts EllipseCRM";
        clientsCommand.innerHTML = "Clients <span>Connected client overview</span>";
        const appsCommand = results.querySelector('a[href="/apps"]');
        if (appsCommand) results.insertBefore(clientsCommand, appsCommand);
        else results.appendChild(clientsCommand);
    }

    const staticLinks = Array.from(results?.querySelectorAll("a") || []);
    const remoteContainer = document.createElement("div");
    remoteContainer.dataset.commandRemoteResults = "true";
    results?.appendChild(remoteContainer);

    const visibleLinks = () => Array.from(results?.querySelectorAll("a") || []).filter((link) => !link.hidden);

    const setEmptyState = (message, visibleCount) => {
        if (!empty) return;
        empty.textContent = message;
        empty.hidden = visibleCount !== 0;
    };

    const clearActiveResult = () => {
        visibleLinks().forEach((link) => link.removeAttribute("data-command-active"));
        activeResultIndex = -1;
    };

    const focusResult = (index) => {
        const links = visibleLinks();
        if (!links.length) return;
        activeResultIndex = ((index % links.length) + links.length) % links.length;
        links.forEach((link, linkIndex) => {
            if (linkIndex === activeResultIndex) {
                link.dataset.commandActive = "true";
                link.focus();
                link.scrollIntoView({ block: "nearest" });
            } else {
                link.removeAttribute("data-command-active");
            }
        });
    };

    const renderRemoteResults = (items) => {
        remoteContainer.replaceChildren();
        for (const item of items) {
            if (!item || !item.url || !item.title) continue;
            const link = document.createElement("a");
            link.href = item.url;
            link.dataset.commandRemote = "true";
            link.dataset.commandLabel = `${item.kind || "record"} ${item.title} ${item.subtitle || ""}`;
            link.append(document.createTextNode(item.title));
            const meta = document.createElement("span");
            meta.textContent = item.subtitle || item.kind || "HIVE record";
            link.append(meta);
            remoteContainer.appendChild(link);
        }
    };

    const filterStaticLinks = (query) => {
        let visible = 0;
        staticLinks.forEach((link) => {
            const haystack = (link.dataset.commandLabel || link.textContent || "").toLowerCase();
            const show = !query || haystack.includes(query);
            link.hidden = !show;
            if (show) visible += 1;
        });
        return visible;
    };

    const performSearch = async (query, sequence) => {
        try {
            const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`, {
                method: "GET",
                credentials: "same-origin",
                headers: { Accept: "application/json" },
            });
            if (sequence !== searchSequence) return;
            if (!response.ok) throw new Error(`Search returned ${response.status}`);

            const payload = await response.json();
            const items = payload && payload.ok && Array.isArray(payload.results) ? payload.results : [];
            renderRemoteResults(items);
            clearActiveResult();
            const visibleCount = filterStaticLinks(query.toLowerCase()) + items.length;
            setEmptyState("No matching HIVE records or destinations.", visibleCount);
        } catch (error) {
            if (sequence !== searchSequence) return;
            renderRemoteResults([]);
            clearActiveResult();
            const visibleCount = filterStaticLinks(query.toLowerCase());
            setEmptyState("Record search is temporarily unavailable. Navigation search still works.", visibleCount);
            console.warn("HIVE command search failed", error);
        }
    };

    const updateCommands = () => {
        const query = (input?.value || "").trim();
        const normalised = query.toLowerCase();
        const staticVisible = filterStaticLinks(normalised);
        clearActiveResult();

        if (searchTimer) window.clearTimeout(searchTimer);
        searchSequence += 1;
        const sequence = searchSequence;

        if (query.length < 2) {
            renderRemoteResults([]);
            setEmptyState("No matching navigation destination.", staticVisible);
            return;
        }

        setEmptyState("Searching HIVE…", 0);
        searchTimer = window.setTimeout(() => performSearch(query, sequence), 180);
    };

    const openCommand = () => {
        if (!dialog) return;
        commandReturnFocus = document.activeElement;
        dialog.hidden = false;
        body.classList.add("hive-command-open");
        if (input) {
            input.value = "";
            updateCommands();
            window.requestAnimationFrame(() => input.focus());
        }
    };

    const closeCommand = () => {
        if (!dialog || dialog.hidden) return;
        dialog.hidden = true;
        body.classList.remove("hive-command-open");
        if (searchTimer) window.clearTimeout(searchTimer);
        searchSequence += 1;
        renderRemoteResults([]);
        clearActiveResult();
        if (commandReturnFocus instanceof HTMLElement) commandReturnFocus.focus();
    };

    trigger?.addEventListener("click", openCommand);
    input?.addEventListener("input", updateCommands);
    input?.addEventListener("keydown", (event) => {
        if (event.key === "ArrowDown") {
            event.preventDefault();
            focusResult(activeResultIndex + 1);
        } else if (event.key === "ArrowUp") {
            event.preventDefault();
            focusResult(activeResultIndex <= 0 ? -1 : activeResultIndex - 1);
        } else if (event.key === "Enter") {
            const links = visibleLinks();
            if (links.length) {
                event.preventDefault();
                links[Math.max(activeResultIndex, 0)].click();
            }
        }
    });
    results?.addEventListener("keydown", (event) => {
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            const links = visibleLinks();
            const currentIndex = links.indexOf(document.activeElement);
            focusResult(currentIndex + (event.key === "ArrowDown" ? 1 : -1));
        }
    });
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
