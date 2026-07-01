// Function to toggle social media platforms ON/OFF
function togglePlatform(platformId) {
    const btn = document.getElementById(`plat-${platformId}`);
    const span = btn.querySelector('span');
    
    if (btn.classList.contains('off')) {
        btn.classList.remove('off');
        btn.classList.add('on');
        span.innerText = 'ON';
    } else {
        btn.classList.remove('on');
        btn.classList.add('off');
        span.innerText = 'OFF';
    }
}

// Function to switch between sidebar tabs
function switchTab(tabName) {
    const links = document.querySelectorAll('.nav-links li');
    links.forEach(link => link.classList.remove('active'));

    if (window.event && window.event.currentTarget) {
        window.event.currentTarget.classList.add('active');
    }

    const resourcesPanel = document.getElementById('resources-panel');
    const sessionsSection = document.getElementById('sessions-section');
    const pcControlSection = document.getElementById('pc-control-section');
    const analyticsSection = document.getElementById('analytics-section');
    const targetsSection = document.getElementById('targets-section');

    if (tabName === 'pc-control') {
        if (resourcesPanel) resourcesPanel.style.display = 'none';
        if (sessionsSection) sessionsSection.style.display = 'none';
        if (analyticsSection) analyticsSection.style.display = 'none';
        if (targetsSection) targetsSection.style.display = 'none';
        if (pcControlSection) pcControlSection.style.display = 'flex';
        refreshWorkerTable();
        if (typeof showPcControlSubtab === 'function') {
            showPcControlSubtab(window.__pcControlSubtab || 'devices');
        }
    } else if (tabName === 'analytics') {
        if (resourcesPanel) resourcesPanel.style.display = 'none';
        if (sessionsSection) sessionsSection.style.display = 'none';
        if (pcControlSection) pcControlSection.style.display = 'none';
        if (targetsSection) targetsSection.style.display = 'none';
        if (analyticsSection) analyticsSection.style.display = 'flex';
        refreshAnalytics();
    } else if (tabName === 'targets') {
        if (resourcesPanel) resourcesPanel.style.display = 'none';
        if (sessionsSection) sessionsSection.style.display = 'none';
        if (pcControlSection) pcControlSection.style.display = 'none';
        if (analyticsSection) analyticsSection.style.display = 'none';
        if (targetsSection) targetsSection.style.display = 'none';
        if (targetsSection) targetsSection.style.display = 'flex';
        updateTargetTypeOptions();
        refreshPlatformTargets();
    } else if (tabName === 'web-agent') {
        if (resourcesPanel) resourcesPanel.style.display = 'none';
        if (sessionsSection) sessionsSection.style.display = 'none';
        if (pcControlSection) pcControlSection.style.display = 'none';
        if (analyticsSection) analyticsSection.style.display = 'none';
        if (targetsSection) targetsSection.style.display = 'none';
        const waSection = document.getElementById('web-agent-section');
        if (waSection) waSection.style.display = 'flex';
        waInit();
    } else {
        if (resourcesPanel) resourcesPanel.style.display = '';
        if (sessionsSection) sessionsSection.style.display = 'flex';
        if (pcControlSection) pcControlSection.style.display = 'none';
        if (analyticsSection) analyticsSection.style.display = 'none';
        if (targetsSection) targetsSection.style.display = 'none';
        const waSection = document.getElementById('web-agent-section');
        if (waSection) waSection.style.display = 'none';
    }

    console.log(`Switched to ${tabName} tab`);
}

function updateSystemMetrics(cpu, ramPercent, ramUsed, gpu, gpuName, safeLimit, activeProfiles, availableProfiles, netType, dlSpeed, ulSpeed) {
    // 1. Progress Bars
    document.getElementById('cpu-fill').style.width = `${cpu}%`;
    document.getElementById('cpu-val').innerText = `${cpu}%`;
    document.getElementById('ram-fill').style.width = `${ramPercent}%`;
    document.getElementById('ram-val').innerText = `${ramUsed}GB`;
    document.getElementById('gpu-fill').style.width = `${gpu}%`;
    document.getElementById('gpu-val').innerText = `${gpu}%`;
    document.getElementById('gpu-label').innerText = `GPU LOAD (${gpuName})`;

    // 2. Fleet State (Fixed Math)
    document.getElementById('safe-limit').innerText = safeLimit;
    document.getElementById('in-use-prof').innerText = activeProfiles;
    document.getElementById('avail-prof').innerText = availableProfiles;

    // 3. Network Rings
    document.getElementById('network-type').innerText = netType;
    document.getElementById('dl-val').innerHTML = `${dlSpeed}<br><span style="font-size:10px; color:#8892b0;">Mbps</span>`;
    document.getElementById('ul-val').innerHTML = `${ulSpeed}<br><span style="font-size:10px; color:#8892b0;">Mbps</span>`;

    const maxMbps = 1000; 
    let dlDeg = Math.min(360, (dlSpeed / maxMbps) * 360);
    let ulDeg = Math.min(360, (ulSpeed / maxMbps) * 360);
    document.getElementById('dl-circle').style.background = `conic-gradient(#00e5ff ${dlDeg}deg, #111 ${dlDeg}deg)`;
    document.getElementById('ul-circle').style.background = `conic-gradient(#ffea00 ${ulDeg}deg, #111 ${ulDeg}deg)`;
}

// --- PROFILE MANAGEMENT CONTROLS ---

function getProfileCreateCount() {
    const input = document.getElementById('profile-create-count');
    let count = parseInt(input && input.value ? input.value : '1', 10);
    if (Number.isNaN(count)) count = 1;
    count = Math.max(1, Math.min(500, count));
    if (input) input.value = String(count);
    return count;
}

function refreshProfilesAfterCreate() {
    if (
        window.pywebview &&
        window.pywebview.api &&
        typeof window.pywebview.api.get_profile_data === 'function'
    ) {
        window.pywebview.api.get_profile_data().then(profiles => {
            renderProfileTable(Array.isArray(profiles) ? profiles : []);
        }).catch(err => {
            console.log('[Ghost UI] Profile refresh after create failed:', err);
        });
    }
}

function createProfile() {
    const btn = document.getElementById('btn-create');
    const count = getProfileCreateCount();
    const originalText = btn.innerText;
    
    // Add a satisfying visual loading state
    btn.innerText = count === 1 ? "GENERATING..." : `GENERATING ${count}...`;
    btn.style.opacity = "0.7";
    btn.disabled = true;

    // Tell Python to build the profile in the database
    if (window.pywebview) {
        const createCall = (
            window.pywebview.api &&
            typeof window.pywebview.api.trigger_create_profiles === 'function'
        )
            ? pywebview.api.trigger_create_profiles(count)
            : pywebview.api.trigger_create_profile();

        createCall.then(function(response) {
            const ok = response === "SUCCESS" || (response && response.ok !== false && response.code === "SUCCESS");
            if(ok) {
                const created = response && typeof response === 'object' ? (response.created || count) : 1;
                const extensionReady = response && typeof response === 'object' ? response.extension_ready !== false : true;
                const assignment = response && typeof response === 'object' ? response.proton_assignment : null;
                const assignedCount = assignment && assignment.assigned !== undefined ? assignment.assigned : null;

                // Flash the button to show it worked
                btn.innerText = created === 1 ? "CREATED!" : `CREATED ${created}!`;
                btn.style.background = "linear-gradient(145deg, #ffffff, #00ff7f)";

                const statusBits = [];
                if (!extensionReady) statusBits.push("Proton extension path missing");
                if (assignedCount !== null) statusBits.push(`Proton assigned: ${assignedCount}`);
                if (statusBits.length) {
                    console.log(`[Ghost UI] Profile create status: ${statusBits.join(' | ')}`);
                }

                refreshProfilesAfterCreate();
                if (window.__pcControlSubtab === 'proton' && typeof refreshProtonAccountPanel === 'function') {
                    refreshProtonAccountPanel();
                }
                
                setTimeout(() => {
                    btn.innerText = originalText;
                    btn.style.background = ""; // Reset to CSS default
                    btn.style.opacity = "1";
                    btn.disabled = false;
                }, 1000);
            } else {
                btn.innerText = "CREATE FAILED";
                console.log("[Ghost UI] Create profile failed:", response);
                setTimeout(() => {
                    btn.innerText = originalText;
                    btn.style.background = "";
                    btn.style.opacity = "1";
                    btn.disabled = false;
                }, 1400);
            }
        }).catch(function(err) {
            console.log("[Ghost UI] Create profile error:", err);
            btn.innerText = "CREATE FAILED";
            setTimeout(() => {
                btn.innerText = originalText;
                btn.style.background = "";
                btn.style.opacity = "1";
                btn.disabled = false;
            }, 1400);
        });
    }
}

function checkAndFixDuplicateFingerprints() {
    const btn = document.getElementById('btn-check');
    if (!btn) return;
    const originalText = btn.innerText;
    btn.innerText = 'CHECKING...';
    btn.disabled = true;
    btn.style.opacity = '0.7';

    if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.fix_duplicate_fingerprints !== 'function') {
        alert('Backend bridge missing: fix_duplicate_fingerprints');
        btn.innerText = originalText;
        btn.disabled = false;
        btn.style.opacity = '1';
        return;
    }

    window.pywebview.api.fix_duplicate_fingerprints().then(function(response) {
        if (response && response.ok) {
            const fixed = response.fixed || 0;
            const msg = response.message || (fixed === 0 ? 'All fingerprints are unique.' : `Fixed ${fixed} duplicate(s).`);
            btn.innerText = fixed === 0 ? 'ALL UNIQUE ✓' : `FIXED ${fixed} ✓`;
            btn.style.background = fixed === 0
                ? 'linear-gradient(145deg, #00ff7f, #009944)'
                : 'linear-gradient(145deg, #ffea00, #b3a400)';
            if (response.errors && response.errors.length) {
                console.warn('[Ghost UI] Fix fingerprint errors:', response.errors);
            }
            console.log('[Ghost UI] Fingerprint check:', msg);
            if (fixed > 0) {
                setTimeout(() => refreshSessions(), 800);
            }
        } else {
            btn.innerText = 'CHECK FAILED';
            console.error('[Ghost UI] fix_duplicate_fingerprints failed:', response);
        }
        setTimeout(() => {
            btn.innerText = originalText;
            btn.style.background = '';
            btn.style.opacity = '1';
            btn.disabled = false;
        }, 2500);
    }).catch(function(err) {
        console.error('[Ghost UI] fix_duplicate_fingerprints error:', err);
        btn.innerText = 'CHECK FAILED';
        setTimeout(() => {
            btn.innerText = originalText;
            btn.style.background = '';
            btn.style.opacity = '1';
            btn.disabled = false;
        }, 2000);
    });
}

document.addEventListener('DOMContentLoaded', function() {
    const btnCheck = document.getElementById('btn-check');
    if (btnCheck) btnCheck.addEventListener('click', checkAndFixDuplicateFingerprints);
});

// Function to collect checked IDs and send to Python
function openSelected() {
    const selectedIds = getSelectedProfileIds();

    if (selectedIds.length === 0) {
        alert("Please select at least one profile.");
        return;
    }

    console.log("[Ghost UI] OPEN SELECTED manual launch:", selectedIds);

    if (window.pywebview && window.pywebview.api) {
        // Empty platform list forces MANUAL open.
        pywebview.api.trigger_open_selected(selectedIds, []).then(res => {
            console.log("[Ghost UI] Open Selected result:", res);
        });
    }
}

// New Function for Double-Clicking a row to open it instantly
function handleRowDoubleClick(profileId) {
    const id = parseInt(profileId);

    if (!id || Number.isNaN(id)) {
        console.log("[Ghost UI] Invalid double-click profile ID:", profileId);
        return;
    }

    const now = Date.now();

    if (!window.__ghostDoubleClickLock) {
        window.__ghostDoubleClickLock = {
            id: null,
            time: 0
        };
    }

    // Prevent duplicate launches from the same double-click.
    if (
        window.__ghostDoubleClickLock.id === id &&
        now - window.__ghostDoubleClickLock.time < 2500
    ) {
        console.log("[Ghost UI] Duplicate double-click blocked for profile:", id);
        return;
    }

    window.__ghostDoubleClickLock.id = id;
    window.__ghostDoubleClickLock.time = now;

    console.log("[Ghost UI] DOUBLE-CLICK manual launch:", id);

    if (window.pywebview && window.pywebview.api) {
        pywebview.api.trigger_open_selected([id], []).then(res => {
            console.log("[Ghost UI] Double-click open result:", res);
        });
    } else {
        console.log("[Ghost UI] pywebview API not ready.");
    }
}

function deleteSelected() {
    console.log("Delete Selected Triggered");
    // Will permanently erase checked profiles from SQLite vault
}

function deleteHistory() {
    console.log("Delete History Triggered");
    // Will wipe Comet cache/cookies for selected profiles
}

// --- PROFILE TABLE PAGINATION ---
const PROFILE_PAGE_SIZE = 50;
window.__ghostProfilePage = window.__ghostProfilePage || 1;
window.__ghostSelectedProfileIds = window.__ghostSelectedProfileIds || new Set();
window.__ghostLatestProfiles = window.__ghostLatestProfiles || [];

function normalizeProfileId(value) {
    const id = parseInt(value);
    return Number.isNaN(id) ? null : id;
}

function syncProfileSelectionsFromVisibleCheckboxes() {
    if (!window.__ghostSelectedProfileIds) {
        window.__ghostSelectedProfileIds = new Set();
    }

    document.querySelectorAll('#profile-table-body .profile-select').forEach(cb => {
        const idText = String(cb.value);
        if (cb.checked) {
            window.__ghostSelectedProfileIds.add(idText);
        } else {
            window.__ghostSelectedProfileIds.delete(idText);
        }
    });
}

function handleProfileCheckboxChange(checkbox) {
    if (!window.__ghostSelectedProfileIds) {
        window.__ghostSelectedProfileIds = new Set();
    }

    const idText = String(checkbox.value);
    if (checkbox.checked) {
        window.__ghostSelectedProfileIds.add(idText);
    } else {
        window.__ghostSelectedProfileIds.delete(idText);
    }

    updateVisibleProfileSelectAllState();
    renderProfilePaginationControlsFromCache();
}

function getSelectedProfileIds() {
    syncProfileSelectionsFromVisibleCheckboxes();

    return Array.from(window.__ghostSelectedProfileIds || [])
        .map(id => parseInt(id))
        .filter(id => !Number.isNaN(id));
}

function clearProfileSelections() {
    window.__ghostSelectedProfileIds = new Set();
    document.querySelectorAll('#profile-table-body .profile-select').forEach(cb => {
        cb.checked = false;
    });
    updateVisibleProfileSelectAllState();
    renderProfilePaginationControlsFromCache();
}

function setProfilePage(pageNumber) {
    syncProfileSelectionsFromVisibleCheckboxes();

    const profiles = Array.isArray(window.__ghostLatestProfiles) ? window.__ghostLatestProfiles : [];
    const totalPages = Math.max(1, Math.ceil(profiles.length / PROFILE_PAGE_SIZE));

    let page = parseInt(pageNumber);
    if (Number.isNaN(page)) page = 1;
    page = Math.max(1, Math.min(totalPages, page));

    window.__ghostProfilePage = page;
    renderProfileTable(profiles);
}

function goToProfilePageFromInput() {
    const input = document.getElementById('profile-page-input');
    if (!input) return;
    setProfilePage(input.value);
}

function updateVisibleProfileSelectAllState() {
    const headerCheckbox = document.getElementById('profile-select-visible');
    if (!headerCheckbox) return;

    const visibleChecks = Array.from(document.querySelectorAll('#profile-table-body .profile-select'));
    if (visibleChecks.length === 0) {
        headerCheckbox.checked = false;
        headerCheckbox.indeterminate = false;
        return;
    }

    const checkedCount = visibleChecks.filter(cb => cb.checked).length;
    headerCheckbox.checked = checkedCount === visibleChecks.length;
    headerCheckbox.indeterminate = checkedCount > 0 && checkedCount < visibleChecks.length;
}

function toggleVisibleProfileCheckboxes(checked) {
    if (!window.__ghostSelectedProfileIds) {
        window.__ghostSelectedProfileIds = new Set();
    }

    document.querySelectorAll('#profile-table-body .profile-select').forEach(cb => {
        cb.checked = checked;
        const idText = String(cb.value);
        if (checked) {
            window.__ghostSelectedProfileIds.add(idText);
        } else {
            window.__ghostSelectedProfileIds.delete(idText);
        }
    });

    updateVisibleProfileSelectAllState();
    renderProfilePaginationControlsFromCache();
}

function ensureProfilePaginationControls() {
    let controls = document.getElementById('profile-pagination-controls');
    if (controls) return controls;

    const table = document.querySelector('#profile-table-body')?.closest('table');
    if (!table) return null;

    controls = document.createElement('div');
    controls.id = 'profile-pagination-controls';
    controls.className = 'profile-pagination-controls';
    table.insertAdjacentElement('afterend', controls);
    return controls;
}

function renderProfilePaginationControls(totalProfiles, currentPage, totalPages, startNumber, endNumber) {
    const controls = ensureProfilePaginationControls();
    if (!controls) return;

    const selectedCount = (window.__ghostSelectedProfileIds || new Set()).size;
    const disabledPrev = currentPage <= 1 ? 'disabled' : '';
    const disabledNext = currentPage >= totalPages ? 'disabled' : '';

    controls.innerHTML = `
        <div class="profile-pagination-left">
            <span class="profile-pagination-summary">
                Showing <strong>${startNumber}</strong>-<strong>${endNumber}</strong> of <strong>${totalProfiles}</strong>
            </span>
            <span class="profile-pagination-selected">
                Selected: <strong>${selectedCount}</strong>
            </span>
            <button class="btn btn-secondary pagination-clear-btn" onclick="clearProfileSelections()" ${selectedCount === 0 ? 'disabled' : ''}>CLEAR SELECTED</button>
        </div>

        <div class="profile-pagination-right">
            <button class="btn btn-secondary pagination-btn" onclick="setProfilePage(1)" ${disabledPrev}>FIRST</button>
            <button class="btn btn-secondary pagination-btn" onclick="setProfilePage(${currentPage - 1})" ${disabledPrev}>PREV</button>
            <span class="profile-pagination-page-label">Page</span>
            <input
                id="profile-page-input"
                class="profile-page-input"
                type="number"
                min="1"
                max="${totalPages}"
                value="${currentPage}"
                onkeydown="if(event.key === 'Enter') goToProfilePageFromInput();"
            >
            <span class="profile-pagination-page-label">/ ${totalPages}</span>
            <button class="btn btn-secondary pagination-btn" onclick="goToProfilePageFromInput()">GO</button>
            <button class="btn btn-secondary pagination-btn" onclick="setProfilePage(${currentPage + 1})" ${disabledNext}>NEXT</button>
            <button class="btn btn-secondary pagination-btn" onclick="setProfilePage(${totalPages})" ${disabledNext}>LAST</button>
        </div>
    `;
}

function renderProfilePaginationControlsFromCache() {
    const profiles = Array.isArray(window.__ghostLatestProfiles) ? window.__ghostLatestProfiles : [];
    const totalProfiles = profiles.length;
    const totalPages = Math.max(1, Math.ceil(totalProfiles / PROFILE_PAGE_SIZE));
    const currentPage = Math.max(1, Math.min(window.__ghostProfilePage || 1, totalPages));
    const startIndex = totalProfiles === 0 ? 0 : (currentPage - 1) * PROFILE_PAGE_SIZE;
    const endIndexExclusive = Math.min(startIndex + PROFILE_PAGE_SIZE, totalProfiles);
    const startNumber = totalProfiles === 0 ? 0 : startIndex + 1;
    const endNumber = endIndexExclusive;
    renderProfilePaginationControls(totalProfiles, currentPage, totalPages, startNumber, endNumber);
}

function renderProfileTable(profiles) {
    const tbody = document.getElementById('profile-table-body');
    if (!tbody) return;

    syncProfileSelectionsFromVisibleCheckboxes();

    if (!Array.isArray(profiles)) {
        profiles = [];
    }

    window.__ghostLatestProfiles = profiles;

    const HOME_IP = "190.110.36.47";

    const logo = document.querySelector(".logo");
    if (logo) {
        logo.innerText = "Ghost HQ";
        logo.style.color = "";
    }

    const totalProf = document.getElementById('total-prof');
    if (totalProf) totalProf.innerText = profiles.length;

    const totalProfiles = profiles.length;
    const totalPages = Math.max(1, Math.ceil(totalProfiles / PROFILE_PAGE_SIZE));
    let currentPage = parseInt(window.__ghostProfilePage || 1);
    if (Number.isNaN(currentPage)) currentPage = 1;
    currentPage = Math.max(1, Math.min(totalPages, currentPage));
    window.__ghostProfilePage = currentPage;

    const startIndex = totalProfiles === 0 ? 0 : (currentPage - 1) * PROFILE_PAGE_SIZE;
    const endIndexExclusive = Math.min(startIndex + PROFILE_PAGE_SIZE, totalProfiles);
    const pageProfiles = profiles.slice(startIndex, endIndexExclusive);
    const startNumber = totalProfiles === 0 ? 0 : startIndex + 1;
    const endNumber = endIndexExclusive;

    function getIpText(p) {
        return String(
            p.ip_origin ||
            p.ipOrigin ||
            p.last_ip ||
            p.ip ||
            p.live_ip ||
            p.liveIp ||
            "Checking..."
        ).trim();
    }

    function extractIpOnly(ipText) {
        const raw = String(ipText || "").trim();
        const match = raw.match(/\b\d{1,3}(?:\.\d{1,3}){3}\b/);
        return match ? match[0] : "";
    }

    function isUnknownIp(ipText) {
        const raw = String(ipText || "").trim().toLowerCase();

        return (
            !raw ||
            raw === "checking..." ||
            raw === "checking" ||
            raw === "unknown" ||
            raw === "not verified" ||
            raw === "none" ||
            raw === "null"
        );
    }

    function buildIpCountMap(profileList) {
        const counts = {};

        profileList.forEach(p => {
            const ipOnly = extractIpOnly(getIpText(p));
            if (!ipOnly) return;

            counts[ipOnly] = (counts[ipOnly] || 0) + 1;
        });

        return counts;
    }

    const ipCounts = buildIpCountMap(profiles);

    function getIpState(ipText) {
        const raw = String(ipText || "").trim();
        const lower = raw.toLowerCase();
        const ipOnly = extractIpOnly(raw);

        if (isUnknownIp(raw) || !ipOnly) {
            return "UNKNOWN";
        }

        if (ipOnly === HOME_IP) {
            return "HOME";
        }

        if (ipCounts[ipOnly] && ipCounts[ipOnly] > 1) {
            return "DUPLICATE";
        }

        if (
            lower.includes("duplicate") ||
            lower.includes("blocked") ||
            lower.includes("blacklist") ||
            lower.includes("blacklisted") ||
            lower.includes("bad") ||
            lower.includes("failed")
        ) {
            return "DUPLICATE";
        }

        return "OK";
    }

    function getIpTextStyle(ipState) {
        const base = [
            "font-weight:800",
            "letter-spacing:0.15px",
            "line-height:1.35",
            "background:transparent",
            "border:none",
            "outline:none",
            "box-shadow:none",
            "padding:0",
            "margin:0",
            "border-radius:0"
        ];

        if (ipState === "HOME") {
            return [
                ...base,
                "color:#e6cf3a",
                "text-shadow:0 0 3px rgba(230,207,58,0.35)"
            ].join(";");
        }

        if (ipState === "DUPLICATE") {
            return [
                ...base,
                "color:#d85a5a",
                "text-shadow:0 0 3px rgba(216,90,90,0.30)"
            ].join(";");
        }

        if (ipState === "OK") {
            return [
                ...base,
                "color:#38d98a",
                "text-shadow:0 0 3px rgba(56,217,138,0.28)"
            ].join(";");
        }

        return [
            ...base,
            "color:#aeb7c9",
            "text-shadow:none"
        ].join(";");
    }

    function getStatusTextStyle(statusText) {
        const status = String(statusText || "").toUpperCase();

        const base = [
            "font-weight:900",
            "letter-spacing:0.35px",
            "background:transparent",
            "border:none",
            "outline:none",
            "box-shadow:none",
            "padding:0",
            "margin:0",
            "border-radius:0"
        ];

        if (status === "RUNNING") {
            return [...base, "color:#38d98a", "text-shadow:0 0 3px rgba(56,217,138,0.35)"].join(";");
        }

        if (status === "STARTING" || status === "LAUNCHING") {
            return [...base, "color:#d9c84a", "text-shadow:0 0 3px rgba(217,200,74,0.30)"].join(";");
        }

        if (status === "BLACKLISTED" || status === "FAILED" || status === "ERROR" || status === "BLOCKED" || status === "CLOSED") {
            return [...base, "color:#d85a5a", "text-shadow:0 0 3px rgba(216,90,90,0.30)"].join(";");
        }

        return [...base, "color:#aeb7c9", "text-shadow:none"].join(";");
    }

    tbody.innerHTML = "";

    if (pageProfiles.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" style="color:#aeb7c9; font-weight:700; text-align:center; padding:25px;">
                    No profiles found.
                </td>
            </tr>
        `;
    }

    pageProfiles.forEach(p => {
        const id = p.id;
        const idText = String(id);

        const status = String(p.status || "OFFLINE").toUpperCase();
        const statusStyle = getStatusTextStyle(status);
        const target = p.target || p.current_target || p.currentTarget || p.target_platform || "None";
        const hardware = p.hardware_cloak || p.hardwareCloak || "Pending Execution";

        const ipText = getIpText(p);
        const ipState = getIpState(ipText);
        const ipStyle = getIpTextStyle(ipState);

        const checked = (window.__ghostSelectedProfileIds || new Set()).has(idText) ? "checked" : "";

        const row = document.createElement('tr');
        row.dataset.profileId = idText;
        row.style.cursor = "pointer";

        row.addEventListener("dblclick", function (event) {
            if (event.target && event.target.tagName === "INPUT") {
                return;
            }

            handleRowDoubleClick(id);
        });

        row.innerHTML = `
            <td>
                <input
                    type="checkbox"
                    class="profile-select"
                    value="${id}"
                    ${checked}
                    onchange="handleProfileCheckboxChange(this);"
                    onclick="event.stopPropagation();"
                    ondblclick="event.stopPropagation();"
                >
            </td>
            <td>${p.name || `Profile ${id}`}</td>
            <td id="status-cell-${id}">
                <span style="${statusStyle}">${status}</span>
            </td>
            <td id="target-cell-${id}">${target}</td>
            <td>${hardware}</td>
            <td
                id="ip-cell-${id}"
                title="IP STATE: ${ipState}"
                style="background:transparent !important; border:none !important; border-left:none !important; box-shadow:none !important;"
            >
                <span style="${ipStyle}">${ipText}</span>
            </td>
        `;

        tbody.appendChild(row);
    });

    renderProfilePaginationControls(totalProfiles, currentPage, totalPages, startNumber, endNumber);
    updateVisibleProfileSelectAllState();
}

// Triggers the physical deletion of profiles
function deleteSelected() {
    const selectedIds = getSelectedProfileIds();

    if (selectedIds.length === 0) {
        alert("Commander, select at least one profile to delete.");
        return;
    }

    // Double-check so you don't accidentally wipe a good profile
    if(confirm(`WARNING: Are you sure you want to permanently vaporize ${selectedIds.length} profile(s)? This cannot be undone.`)) {
        if (window.pywebview) {
            pywebview.api.trigger_delete_selected(selectedIds).then(res => {
                console.log("Purge complete.");
                selectedIds.forEach(id => window.__ghostSelectedProfileIds.delete(String(id)));
                renderProfilePaginationControlsFromCache();
                // The resource_monitor_thread will automatically remove them from the table!
            });
        }
    }
}

// Helper function to read exactly what is turned ON in the dashboard
function getActivePlatforms() {
    let active = [];
    const toggles = document.querySelectorAll('.platform-toggles .toggle-btn, .platform-toggles span');
    toggles.forEach(el => {
        const text = el.innerText.toUpperCase();
        if (text.includes("ON")) {
            if (text.includes("TWITCH")) active.push("twitch");
            if (text.includes("YOUTUBE")) active.push("youtube");
            if (text.includes("SPOTIFY")) active.push("spotify");
            if (text.includes("DEEZER")) active.push("deezer");
        }
    });
    return [...new Set(active)]; // Return unique list
}

// ==============================
// LAUNCH ELIGIBILITY GUARD
// ==============================

function normalizeLaunchSummary(result) {
    if (result && typeof result === "object") {
        result.skipped = result.skipped || {};
        result.skipped_counts = result.skipped_counts || {};
        result.warnings = result.warnings || [];
        result.launchable_ids = Array.isArray(result.launchable_ids) ? result.launchable_ids : [];
        result.launched_ids = Array.isArray(result.launched_ids) ? result.launched_ids : [];
        return result;
    }

    const code = String(result || "UNKNOWN");
    return {
        ok: code === "SUCCESS",
        code: code,
        mode: "unknown",
        message: code,
        active_platforms: getActivePlatforms(),
        requested_count: 0,
        launchable_count: 0,
        launched_count: code === "SUCCESS" ? 1 : 0,
        launchable_ids: [],
        launched_ids: [],
        skipped_counts: {
            running: 0,
            quarantined: 0,
            locked: 0,
            invalid: 0,
            preflight: 0
        },
        skipped: {
            running: [],
            quarantined: [],
            locked: [],
            invalid: [],
            preflight: []
        },
        warnings: []
    };
}

function renderLaunchSummary(result) {
    const summary = normalizeLaunchSummary(result);
    window.__lastLaunchSummary = summary;
    console.log("[Launch Summary]", summary);
    return summary;
}

// Triggers the global launch for all profiles
function startAll() {
    const activePlatforms = getActivePlatforms();

    if (activePlatforms.length === 0) {
        renderLaunchSummary({
            ok: false,
            code: "NO_PLATFORMS",
            message: "Turn ON at least one platform before starting the fleet.",
            active_platforms: activePlatforms,
            skipped: { preflight: ["No platforms toggled ON"] },
            skipped_counts: { preflight: 1 },
            warnings: []
        });
        alert("Commander, you must turn ON at least one platform before starting the automated fleet.");
        return;
    }

    const startBtn = document.getElementById('start-all-btn');
    const stopBtn = document.getElementById('stop-all-btn');
    if (startBtn) startBtn.disabled = true;
    if (stopBtn) stopBtn.disabled = false;

    if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.trigger_start_all !== "function") {
        renderLaunchSummary({
            ok: false,
            code: "API_MISSING",
            message: "trigger_start_all API is not available. Restart the dashboard.",
            active_platforms: activePlatforms,
            skipped: { preflight: ["Backend API missing"] },
            skipped_counts: { preflight: 1 },
            warnings: []
        });
        if (startBtn) startBtn.disabled = false;
        if (stopBtn) stopBtn.disabled = true;
        return;
    }

    window.pywebview.api.trigger_start_all(activePlatforms).then(res => {
        const summary = normalizeLaunchSummary(res);
        renderLaunchSummary(summary);

        if (!summary.ok || summary.code !== "SUCCESS") {
            if (startBtn) startBtn.disabled = false;
            if (stopBtn) stopBtn.disabled = true;
        }

        console.log("[Launch Summary]", summary);
    }).catch(err => {
        renderLaunchSummary({
            ok: false,
            code: "ERROR",
            message: String(err || "START ALL failed."),
            active_platforms: activePlatforms,
            skipped: { preflight: [String(err || "Unknown error")] },
            skipped_counts: { preflight: 1 },
            warnings: []
        });

        if (startBtn) startBtn.disabled = false;
        if (stopBtn) stopBtn.disabled = true;
    });
}


function profileIsActiveOrClosing(profile) {
    const status = String(profile && profile.status ? profile.status : '').toUpperCase();
    return ['RUNNING', 'STARTING', 'LAUNCHING', 'STOPPING'].includes(status);
}

function monitorStopAllShutdown() {
    const startBtn = document.getElementById('start-all-btn');
    const stopBtn = document.getElementById('stop-all-btn');
    const originalStopText = stopBtn ? (stopBtn.dataset.originalText || 'STOP ALL') : 'STOP ALL';
    const startedAt = Date.now();

    const timer = setInterval(() => {
        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_profile_data !== 'function') {
            clearInterval(timer);
            if (startBtn) startBtn.disabled = false;
            if (stopBtn) {
                stopBtn.disabled = true;
                stopBtn.innerText = originalStopText;
            }
            return;
        }

        window.pywebview.api.get_profile_data().then(profiles => {
            const rows = Array.isArray(profiles) ? profiles : [];
            renderProfileTable(rows);

            const stillActive = rows.some(profileIsActiveOrClosing);
            const timedOut = Date.now() - startedAt > (8 * 60 * 60 * 1000);

            if (!stillActive || timedOut) {
                clearInterval(timer);
                if (startBtn) startBtn.disabled = false;
                if (stopBtn) {
                    stopBtn.disabled = true;
                    stopBtn.innerText = originalStopText;
                }
            }
        }).catch(err => {
            console.log('[Ghost UI] STOP ALL monitor failed:', err);
        });
    }, 5000);
}

// Triggers the global kill switch and waits while the randomized shutdown drains
function stopAll() {
    const startBtn = document.getElementById('start-all-btn');
    const stopBtn = document.getElementById('stop-all-btn');
    if (startBtn) startBtn.disabled = true;
    if (stopBtn) {
        stopBtn.dataset.originalText = stopBtn.dataset.originalText || stopBtn.innerText || 'STOP ALL';
        stopBtn.innerText = 'CLOSING...';
        stopBtn.disabled = true;
    }

    if (window.pywebview && window.pywebview.api && typeof window.pywebview.api.trigger_stop_all === 'function') {
        pywebview.api.trigger_stop_all().then(res => {
            console.log("Random STOP ALL signal sent.", res);
            const scheduled = res && typeof res === 'object' ? parseInt(res.scheduled || 0, 10) : 0;
            if (scheduled > 0) {
                monitorStopAllShutdown();
            } else {
                if (startBtn) startBtn.disabled = false;
                if (stopBtn) {
                    stopBtn.innerText = stopBtn.dataset.originalText || 'STOP ALL';
                    stopBtn.disabled = true;
                }
            }
        }).catch(err => {
            console.log("STOP ALL failed:", err);
            if (startBtn) startBtn.disabled = false;
            if (stopBtn) {
                stopBtn.innerText = stopBtn.dataset.originalText || 'STOP ALL';
                stopBtn.disabled = false;
            }
        });
    } else {
        console.log("trigger_stop_all API is not available.");
        if (startBtn) startBtn.disabled = false;
        if (stopBtn) {
            stopBtn.innerText = stopBtn.dataset.originalText || 'STOP ALL';
            stopBtn.disabled = false;
        }
    }
}

// --- DEVICE HEALTH / PC CONTROL TAB ---

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// --- TARGETS TAB / PLATFORM FOCUS LISTS ---

const TARGET_TYPE_OPTIONS = {
    youtube: [
        ['channel', 'Channel'],
        ['video', 'Video'],
        ['playlist', 'Playlist'],
        ['search', 'Search Term'],
        ['keyword', 'Keyword'],
        ['url', 'URL'],
        ['other', 'Other']
    ],
    twitch: [
        ['channel', 'Channel'],
        ['category', 'Category'],
        ['search', 'Search Term'],
        ['keyword', 'Keyword'],
        ['url', 'URL'],
        ['other', 'Other']
    ],
    spotify: [
        ['artist', 'Artist'],
        ['song', 'Song'],
        ['track', 'Track'],
        ['album', 'Album'],
        ['playlist', 'Playlist'],
        ['search', 'Search Term'],
        ['url', 'URL'],
        ['other', 'Other']
    ],
    deezer: [
        ['artist', 'Artist'],
        ['song', 'Song'],
        ['track', 'Track'],
        ['album', 'Album'],
        ['playlist', 'Playlist'],
        ['search', 'Search Term'],
        ['url', 'URL'],
        ['other', 'Other']
    ]
};

function targetStatus(message, isBad = false) {
    const el = document.getElementById('target-action-status');
    if (!el) return;
    el.textContent = message || '';
    el.classList.toggle('bad', Boolean(isBad));
}

function targetValidationStatus(message, level = '') {
    const el = document.getElementById('target-validation-summary');
    if (!el) return;
    el.textContent = message || '';
    el.classList.toggle('bad', level === 'bad');
    el.classList.toggle('warn', level === 'warn');
}

function updateTargetTypeOptions() {
    const platformEl = document.getElementById('target-platform');
    const typeEl = document.getElementById('target-type');
    if (!platformEl || !typeEl) return;

    const platform = String(platformEl.value || 'youtube').toLowerCase();
    const current = String(typeEl.value || '').toLowerCase();
    const options = TARGET_TYPE_OPTIONS[platform] || TARGET_TYPE_OPTIONS.youtube;

    typeEl.innerHTML = '';
    options.forEach(([value, label]) => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = label;
        typeEl.appendChild(option);
    });

    if (options.some(([value]) => value === current)) {
        typeEl.value = current;
    }
}

function collectTargetPayload() {
    const enabledEl = document.getElementById('target-enabled');

    return {
        platform: (document.getElementById('target-platform') || {}).value || 'youtube',
        target_type: (document.getElementById('target-type') || {}).value || 'channel',
        title: ((document.getElementById('target-title') || {}).value || '').trim(),
        url: ((document.getElementById('target-url') || {}).value || '').trim(),
        identifier: ((document.getElementById('target-identifier') || {}).value || '').trim(),
        priority: parseInt(((document.getElementById('target-priority') || {}).value || '5'), 10) || 5,
        notes: ((document.getElementById('target-notes') || {}).value || '').trim(),
        enabled: enabledEl && enabledEl.checked ? 1 : 0
    };
}

function clearTargetForm() {
    const ids = ['target-edit-id', 'target-title', 'target-url', 'target-identifier', 'target-notes'];
    ids.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });

    const platformEl = document.getElementById('target-platform');
    const priorityEl = document.getElementById('target-priority');
    const enabledEl = document.getElementById('target-enabled');
    const saveBtn = document.getElementById('target-save-btn');

    if (platformEl) platformEl.value = 'youtube';
    updateTargetTypeOptions();
    if (priorityEl) priorityEl.value = '5';
    if (enabledEl) enabledEl.checked = true;
    if (saveBtn) saveBtn.textContent = 'ADD TARGET';
    targetValidationStatus('');

    targetStatus('Ready. Add a platform focus entry and it will be saved locally.');
}

function getTargetFilters() {
    const platform = ((document.getElementById('target-filter-platform') || {}).value || '').trim();
    const targetType = ((document.getElementById('target-filter-type') || {}).value || '').trim();
    const enabledRaw = ((document.getElementById('target-filter-enabled') || {}).value || '').trim();
    const enabled = enabledRaw === '' ? null : parseInt(enabledRaw, 10);

    return { platform, targetType, enabled };
}

function renderPlatformTargets(targets) {
    const body = document.getElementById('target-table-body');
    if (!body) return;

    const rows = Array.isArray(targets) ? targets : [];

    if (!rows.length) {
        body.innerHTML = '<tr><td colspan="9">No targets saved yet.</td></tr>';
        return;
    }

    body.innerHTML = '';

    rows.forEach(row => {
        const tr = document.createElement('tr');
        const enabled = Number(row.enabled || 0) === 1;
        const linkText = row.url || row.identifier || '-';

        tr.innerHTML = `
            <td>${escapeHtml(row.platform || '')}</td>
            <td>${escapeHtml(row.target_type || '')}</td>
            <td>${escapeHtml(row.title || '')}</td>
            <td class="target-url-cell" title="${escapeHtml(linkText)}">${escapeHtml(linkText)}</td>
            <td>${escapeHtml(row.priority || 5)}</td>
            <td><span class="${enabled ? 'identity-status-ok' : 'identity-status-warn'}">${enabled ? 'ENABLED' : 'DISABLED'}</span></td>
            <td>${escapeHtml(row.notes || '')}</td>
            <td>${escapeHtml(row.updated_at || row.created_at || '')}</td>
            <td></td>
        `;

        const actions = tr.querySelector('td:last-child');

        const editBtn = document.createElement('button');
        editBtn.className = 'btn btn-secondary btn-mini';
        editBtn.type = 'button';
        editBtn.textContent = 'EDIT';
        editBtn.addEventListener('click', () => editPlatformTarget(row));
        actions.appendChild(editBtn);

        const toggleBtn = document.createElement('button');
        toggleBtn.className = 'btn btn-secondary btn-mini';
        toggleBtn.type = 'button';
        toggleBtn.textContent = enabled ? 'DISABLE' : 'ENABLE';
        toggleBtn.addEventListener('click', () => togglePlatformTargetEnabled(row.id, !enabled));
        actions.appendChild(toggleBtn);

        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'btn btn-secondary btn-mini';
        deleteBtn.type = 'button';
        deleteBtn.textContent = 'DELETE';
        deleteBtn.addEventListener('click', () => deletePlatformTarget(row.id));
        actions.appendChild(deleteBtn);

        body.appendChild(tr);
    });
}

function refreshPlatformTargets() {
    if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_platform_targets !== 'function') {
        targetStatus('Targets backend is not ready. Restart the dashboard.', true);
        return;
    }

    const filters = getTargetFilters();
    targetStatus('Loading targets...');

    window.pywebview.api.get_platform_targets(
        filters.platform || null,
        filters.targetType || null,
        filters.enabled
    ).then(res => {
        if (!res || res.ok === false) {
            targetStatus((res && res.error) || 'Could not load targets.', true);
            renderPlatformTargets([]);
            return;
        }

        renderPlatformTargets(res.targets || []);
        targetStatus(`Loaded ${(res.targets || []).length} target(s).`);
    }).catch(err => {
        targetStatus(`Could not load targets: ${err}`, true);
    });
}

function savePlatformTarget() {
    if (!window.pywebview || !window.pywebview.api) {
        targetStatus('Targets backend is not ready. Restart the dashboard.', true);
        return;
    }

    const payload = collectTargetPayload();
    if (!payload.title) {
        targetStatus('Name / Title is required.', true);
        return;
    }

    const editId = ((document.getElementById('target-edit-id') || {}).value || '').trim();
    const isEdit = Boolean(editId);
    const apiName = isEdit ? 'update_platform_target' : 'add_platform_target';

    if (typeof window.pywebview.api[apiName] !== 'function') {
        targetStatus(`Targets API missing: ${apiName}. Restart the dashboard.`, true);
        return;
    }

    targetStatus(isEdit ? 'Updating target...' : 'Saving target...');

    const request = isEdit
        ? window.pywebview.api.update_platform_target(parseInt(editId, 10), payload)
        : window.pywebview.api.add_platform_target(payload);

    request.then(res => {
        if (!res || res.ok === false) {
            targetStatus((res && res.error) || 'Target save failed.', true);
            return;
        }

        clearTargetForm();
        targetStatus(isEdit ? 'Target updated.' : 'Target added.');
        refreshPlatformTargets();
    }).catch(err => {
        targetStatus(`Target save failed: ${err}`, true);
    });
}

function editPlatformTarget(row) {
    row = row || {};
    const editId = document.getElementById('target-edit-id');
    const platformEl = document.getElementById('target-platform');
    const titleEl = document.getElementById('target-title');
    const urlEl = document.getElementById('target-url');
    const identifierEl = document.getElementById('target-identifier');
    const priorityEl = document.getElementById('target-priority');
    const notesEl = document.getElementById('target-notes');
    const enabledEl = document.getElementById('target-enabled');
    const saveBtn = document.getElementById('target-save-btn');

    if (editId) editId.value = row.id || '';
    if (platformEl) platformEl.value = row.platform || 'youtube';
    updateTargetTypeOptions();

    const typeEl = document.getElementById('target-type');
    if (typeEl) typeEl.value = row.target_type || 'channel';
    if (titleEl) titleEl.value = row.title || '';
    if (urlEl) urlEl.value = row.url || '';
    if (identifierEl) identifierEl.value = row.identifier || '';
    if (priorityEl) priorityEl.value = String(row.priority || 5);
    if (notesEl) notesEl.value = row.notes || '';
    if (enabledEl) enabledEl.checked = Number(row.enabled || 0) === 1;
    if (saveBtn) saveBtn.textContent = 'UPDATE TARGET';

    targetStatus(`Editing target #${row.id || ''}.`);
}

function togglePlatformTargetEnabled(targetId, enabled) {
    if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.set_platform_target_enabled !== 'function') {
        targetStatus('Targets enable/disable API is not ready. Restart the dashboard.', true);
        return;
    }

    window.pywebview.api.set_platform_target_enabled(parseInt(targetId, 10), Boolean(enabled)).then(res => {
        if (!res || res.ok === false) {
            targetStatus((res && res.error) || 'Could not update target status.', true);
            return;
        }
        targetStatus(enabled ? 'Target enabled.' : 'Target disabled.');
        refreshPlatformTargets();
    }).catch(err => {
        targetStatus(`Could not update target status: ${err}`, true);
    });
}

function deletePlatformTarget(targetId) {
    if (!confirm(`Delete target #${targetId}?`)) {
        return;
    }

    if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.delete_platform_target !== 'function') {
        targetStatus('Targets delete API is not ready. Restart the dashboard.', true);
        return;
    }

    window.pywebview.api.delete_platform_target(parseInt(targetId, 10)).then(res => {
        if (!res || res.ok === false) {
            targetStatus((res && res.error) || 'Could not delete target.', true);
            return;
        }
        targetStatus('Target deleted.');
        refreshPlatformTargets();
    }).catch(err => {
        targetStatus(`Could not delete target: ${err}`, true);
    });
}

function renderTargetValidation(response) {
    const el = document.getElementById('target-validation-summary');
    if (!el) return;

    const summary = response && response.summary ? response.summary : {};
    const rows = response && Array.isArray(response.rows) ? response.rows : [];
    const errors = Number(summary.errors || 0);
    const warnings = Number(summary.warnings || 0);
    const valid = Number(summary.valid || 0);
    const total = Number(summary.total || rows.length || 0);

    const problemRows = rows.filter(row => {
        const issues = Array.isArray(row.validation_issues) ? row.validation_issues : [];
        return issues.some(issue => issue.level === 'error' || issue.level === 'warning');
    }).slice(0, 8);

    const level = errors > 0 ? 'bad' : (warnings > 0 ? 'warn' : '');
    el.classList.toggle('bad', level === 'bad');
    el.classList.toggle('warn', level === 'warn');

    const details = problemRows.map(row => {
        const issues = Array.isArray(row.validation_issues) ? row.validation_issues : [];
        const issueText = issues
            .filter(issue => issue.level === 'error' || issue.level === 'warning')
            .map(issue => issue.message)
            .join(' ');
        return `<li><strong>${escapeHtml(row.title || ('Target #' + row.id))}</strong>: ${escapeHtml(issueText)}</li>`;
    }).join('');

    el.innerHTML = `
        <div class="target-validation-line">
            Checked ${escapeHtml(total)} target(s): ${escapeHtml(valid)} valid, ${escapeHtml(warnings)} warning(s), ${escapeHtml(errors)} error(s).
        </div>
        ${details ? `<ul>${details}</ul>` : '<div class="target-validation-line">No blocking target issues found.</div>'}
    `;
}

function validatePlatformTargets() {
    if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.validate_platform_targets !== 'function') {
        targetValidationStatus('Target validation API is not ready. Restart the dashboard.', 'bad');
        return;
    }

    const filters = getTargetFilters();
    targetValidationStatus('Checking saved targets...');

    window.pywebview.api.validate_platform_targets(filters.platform || null).then(response => {
        if (!response || response.ok === false) {
            targetValidationStatus((response && response.error) || 'Target validation failed.', 'bad');
            return;
        }

        renderTargetValidation(response);
        const summary = response.summary || {};
        if (Number(summary.errors || 0) > 0) {
            targetStatus('Target validation found errors.', true);
        } else if (Number(summary.warnings || 0) > 0) {
            targetStatus('Target validation found warnings.');
        } else {
            targetStatus('Target validation passed.');
        }
    }).catch(err => {
        targetValidationStatus(`Target validation failed: ${err}`, 'bad');
    });
}

function formatWorkerLastSeen(secondsSinceSeen) {
    if (secondsSinceSeen === null || secondsSinceSeen === undefined || secondsSinceSeen === '') {
        return 'Never';
    }

    const seconds = parseInt(secondsSinceSeen);
    if (Number.isNaN(seconds)) return 'Unknown';
    if (seconds < 5) return 'Now';
    if (seconds < 60) return `${seconds}s ago`;

    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;

    const hours = Math.floor(minutes / 60);
    return `${hours}h ago`;
}

function getDeviceType(worker) {
    const raw = `${worker.pc_id || ''} ${worker.hostname || ''} ${worker.device_type || ''}`.toLowerCase();

    if (
        raw.includes('phone') ||
        raw.includes('android') ||
        raw.includes('iphone') ||
        raw.includes('ios') ||
        raw.includes('mobile')
    ) {
        return 'Phone';
    }

    if (
        raw.includes('tablet') ||
        raw.includes('ipad')
    ) {
        return 'Tablet';
    }

    if (
        raw.includes('laptop') ||
        raw.includes('notebook') ||
        raw.includes('legion')
    ) {
        return 'Laptop';
    }

    if (
        raw.includes('desktop') ||
        raw.includes('pc') ||
        raw.includes('tower')
    ) {
        return 'PC';
    }

    return 'Unknown';
}

function getDeviceRole(worker) {
    const type = getDeviceType(worker);
    const raw = `${worker.pc_id || ''} ${worker.hostname || ''} ${worker.device_role || ''}`.toLowerCase();

    if (
        raw.includes('controller') ||
        raw.includes('main') ||
        raw.includes('master')
    ) {
        return 'Controller';
    }

    if (type === 'Phone') {
        return 'Worker Phone';
    }

    if (type === 'Tablet') {
        return 'Worker Tablet';
    }

    if (type === 'Laptop') {
        return 'Worker Laptop';
    }

    if (type === 'PC') {
        return 'Worker PC';
    }

    return 'Monitor Only';
}

function getDeviceCapabilities(worker) {
    const type = getDeviceType(worker);
    const role = getDeviceRole(worker);
    const blocked = worker.blocked === true || worker.blocked === 1 || String(worker.blocked).toLowerCase() === 'true';
    const status = String(worker.display_status || worker.status || 'UNKNOWN').toUpperCase();

    const isPhone = type === 'Phone' || type === 'Tablet';
    const isComputer = type === 'PC' || type === 'Laptop';

    let canLaunchProfiles = false;
    let canRunMobileTasks = false;
    let canControlFleet = false;
    let canBeBlocked = true;

    if (!blocked && isComputer) {
        canLaunchProfiles = true;
    }

    if (!blocked && isPhone) {
        canRunMobileTasks = true;
    }

    if (!blocked && role === 'Controller') {
        canControlFleet = true;
    }

    if (role === 'Controller') {
        canBeBlocked = false;
    }

    // Backend-enforced capability overrides.
    // These keep the UI display aligned with actual START ALL permission checks.
    if (worker.can_launch_profiles !== undefined && worker.can_launch_profiles !== null) {
        canLaunchProfiles = (
            worker.can_launch_profiles === true ||
            worker.can_launch_profiles === 1 ||
            String(worker.can_launch_profiles).toLowerCase() === 'true'
        );
    }

    if (worker.can_run_mobile_tasks !== undefined && worker.can_run_mobile_tasks !== null) {
        canRunMobileTasks = (
            worker.can_run_mobile_tasks === true ||
            worker.can_run_mobile_tasks === 1 ||
            String(worker.can_run_mobile_tasks).toLowerCase() === 'true'
        );
    }

    if (worker.can_control_fleet !== undefined && worker.can_control_fleet !== null) {
        canControlFleet = (
            worker.can_control_fleet === true ||
            worker.can_control_fleet === 1 ||
            String(worker.can_control_fleet).toLowerCase() === 'true'
        );
    }

    if (worker.can_be_blocked !== undefined && worker.can_be_blocked !== null) {
        canBeBlocked = (
            worker.can_be_blocked === true ||
            worker.can_be_blocked === 1 ||
            String(worker.can_be_blocked).toLowerCase() === 'true'
        );
    }

    if (status === 'OFFLINE' || status === 'UNKNOWN') {
        canLaunchProfiles = false;
        canRunMobileTasks = false;
        canControlFleet = false;
    }

    return {
        role: worker.device_role || role,
        canLaunchProfiles,
        canRunMobileTasks,
        canControlFleet,
        canBeBlocked
    };
}

function capabilityBadge(value, yesLabel = 'YES', noLabel = 'NO') {
    if (value) {
        return `<span class="capability-badge capability-yes">${yesLabel}</span>`;
    }

    return `<span class="capability-badge capability-no">${noLabel}</span>`;
}

function getDeviceRoleClass(role) {
    const r = String(role || '').toLowerCase();

    if (r.includes('controller')) return 'device-role-controller';
    if (r.includes('phone')) return 'device-role-phone';
    if (r.includes('tablet')) return 'device-role-tablet';
    if (r.includes('laptop')) return 'device-role-laptop';
    if (r.includes('pc')) return 'device-role-pc';

    return 'device-role-monitor';
}

function getWorkerStatusStyle(status, blocked) {
    const s = String(status || '').toUpperCase();

    if (blocked || s === 'BLOCKED') {
        return 'color:#d85a5a; font-weight:900; text-shadow:0 0 3px rgba(216,90,90,0.35);';
    }

    if (s === 'ONLINE') {
        return 'color:#38d98a; font-weight:900; text-shadow:0 0 3px rgba(56,217,138,0.35);';
    }

    if (s === 'LOCAL ONLY') {
        return 'color:#d9c84a; font-weight:900; text-shadow:0 0 3px rgba(217,200,74,0.30);';
    }

    if (s === 'OFFLINE') {
        return 'color:#d85a5a; font-weight:900;';
    }

    return 'color:#aeb7c9; font-weight:800;';
}

function calculateDeviceHealth(worker) {
    const status = String(worker.display_status || worker.status || 'UNKNOWN').toUpperCase();
    const blocked = worker.blocked === true || worker.blocked === 1 || String(worker.blocked).toLowerCase() === 'true';
    const activeProfiles = Number(worker.active_profiles || 0);
    const secondsSinceSeen = Number(worker.seconds_since_seen || 0);

    let score = 100;
    const issues = [];

    if (blocked || status === 'BLOCKED') {
        score -= 35;
        issues.push('Blocked by coordinator');
    }

    if (status === 'OFFLINE') {
        score -= 30;
        issues.push('Offline');
    }

    if (status === 'UNKNOWN') {
        score -= 15;
        issues.push('Unknown status');
    }

    if (Number.isFinite(secondsSinceSeen) && secondsSinceSeen > 120) {
        score -= 15;
        issues.push('Stale heartbeat');
    }

    if (status === 'LOCAL ONLY') {
        score -= 5;
        issues.push('Coordinator local mode');
    }

    if (activeProfiles > 0) {
        score += 5;
    }

    if (status === 'ONLINE') {
        score += 5;
    }

    score = Math.max(0, Math.min(100, Math.round(score)));

    let gradeClass = 'device-score-good';
    if (score < 30) {
        gradeClass = 'device-score-bad';
    } else if (score < 60) {
        gradeClass = 'device-score-weak';
    } else if (score < 85) {
        gradeClass = 'device-score-watch';
    }

    return {
        score,
        gradeClass,
        issue: issues.length ? issues[0] : 'Healthy'
    };
}

function renderDeviceHealthSummary(workers) {
    const summary = document.getElementById('device-health-summary');
    if (!summary) return;

    const total = workers.length;
    const online = workers.filter(w => String(w.display_status || w.status || '').toUpperCase() === 'ONLINE').length;
    const localOnly = workers.filter(w => String(w.display_status || w.status || '').toUpperCase() === 'LOCAL ONLY').length;
    const blocked = workers.filter(w => w.blocked === true || w.blocked === 1 || String(w.blocked).toLowerCase() === 'true').length;

    const phones = workers.filter(w => getDeviceType(w) === 'Phone').length;
    const tablets = workers.filter(w => getDeviceType(w) === 'Tablet').length;
    const laptops = workers.filter(w => getDeviceType(w) === 'Laptop').length;
    const pcs = workers.filter(w => getDeviceType(w) === 'PC').length;

    summary.innerHTML = `
        <div class="device-health-card">
            <span>Total Devices</span>
            <strong>${escapeHtml(total)}</strong>
        </div>
        <div class="device-health-card">
            <span>Online</span>
            <strong class="device-score-good">${escapeHtml(online)}</strong>
        </div>
        <div class="device-health-card">
            <span>Local Only</span>
            <strong class="device-score-watch">${escapeHtml(localOnly)}</strong>
        </div>
        <div class="device-health-card">
            <span>Blocked</span>
            <strong class="device-score-bad">${escapeHtml(blocked)}</strong>
        </div>
        <div class="device-health-card">
            <span>PC / Laptop</span>
            <strong>${escapeHtml(pcs + laptops)}</strong>
        </div>
        <div class="device-health-card">
            <span>Phones / Tablets</span>
            <strong>${escapeHtml(phones + tablets)}</strong>
        </div>
    `;
}

function formatBattery(worker) {
    const value = worker.battery_percent;

    if (value === null || value === undefined || value === '') {
        return '<span class="mobile-field-muted">N/A</span>';
    }

    const n = parseInt(value);
    if (Number.isNaN(n)) {
        return '<span class="mobile-field-muted">N/A</span>';
    }

    let cls = 'battery-good';
    if (n <= 20) cls = 'battery-bad';
    else if (n <= 50) cls = 'battery-watch';

    return `<span class="battery-pill ${cls}">${escapeHtml(n)}%</span>`;
}

function formatCharging(worker) {
    const charging = (
        worker.charging === true ||
        worker.charging === 1 ||
        String(worker.charging).toLowerCase() === 'true'
    );

    return charging
        ? '<span class="charging-pill charging-yes">YES</span>'
        : '<span class="charging-pill charging-no">NO</span>';
}

function formatNetworkType(worker) {
    const value = String(worker.network_type || '').trim();

    if (!value) {
        return '<span class="mobile-field-muted">Unknown</span>';
    }

    return `<span class="network-pill">${escapeHtml(value)}</span>`;
}

function renderWorkerTable(response) {
    const tbody = document.getElementById('worker-table-body');
    if (!tbody) return;

    const workers = response && Array.isArray(response.workers) ? response.workers : [];

    renderDeviceHealthSummary(workers);

    if (workers.length === 0) {
        tbody.innerHTML = `<tr><td colspan="18">No connected devices found.</td></tr>`;
        return;
    }

    tbody.innerHTML = '';

    workers.forEach(worker => {
        const pcId = worker.pc_id || '';
        const hostname = worker.hostname || '';
        const deviceType = getDeviceType(worker);
        const deviceTypeClass = getDeviceTypeClass(deviceType);
        const capabilities = getDeviceCapabilities(worker);
        const roleClass = getDeviceRoleClass(capabilities.role);
        const status = worker.display_status || worker.status || 'UNKNOWN';
        const blocked = worker.blocked === true || worker.blocked === 1 || String(worker.blocked).toLowerCase() === 'true';
        const activeProfiles = worker.active_profiles || 0;
        const ipAddress = worker.ip_address || '';
        const lastSeen = formatWorkerLastSeen(worker.seconds_since_seen);
        const statusStyle = getWorkerStatusStyle(status, blocked);
        const health = calculateDeviceHealth(worker);

        const actionButton = blocked
            ? `<button class="btn btn-primary device-action-btn" onclick="unblockWorker('${escapeHtml(pcId)}')">UNBLOCK</button>`
            : `<button class="btn btn-danger device-action-btn" onclick="blockWorker('${escapeHtml(pcId)}')">BLOCK</button>`;

        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${escapeHtml(pcId)}</td>
            <td><span class="device-type-pill ${deviceTypeClass}">${escapeHtml(deviceType)}</span></td>
            <td><span class="device-role-pill ${roleClass}">${escapeHtml(capabilities.role)}</span></td>
            <td>${escapeHtml(hostname)}</td>
            <td><span style="${statusStyle}">${escapeHtml(status)}</span></td>
            <td>${escapeHtml(ipAddress)}</td>
            <td>${formatBattery(worker)}</td>
            <td>${formatCharging(worker)}</td>
            <td>${formatNetworkType(worker)}</td>
            <td>${escapeHtml(lastSeen)}</td>
            <td>${escapeHtml(activeProfiles)}</td>
            <td>${capabilityBadge(capabilities.canLaunchProfiles)}</td>
            <td>${capabilityBadge(capabilities.canRunMobileTasks)}</td>
            <td>${capabilityBadge(capabilities.canControlFleet)}</td>
            <td>
                <div class="device-score-cell">
                    <strong class="${health.gradeClass}">${escapeHtml(health.score)}/100</strong>
                    <div class="device-score-bar">
                        <div class="device-score-fill ${health.gradeClass}" style="width:${escapeHtml(health.score)}%;"></div>
                    </div>
                </div>
            </td>
            <td>${escapeHtml(health.issue)}</td>
            <td>${blocked ? '<span style="color:#d85a5a;font-weight:900;">YES</span>' : '<span style="color:#38d98a;font-weight:900;">NO</span>'}</td>
            <td>${actionButton}</td>
        `;
        tbody.appendChild(tr);
    });
}

function refreshWorkerTable() {
    if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_worker_data !== 'function') {
        console.log('[Ghost UI] get_worker_data API is not available yet.');
        return;
    }

    window.pywebview.api.get_worker_data().then(response => {
        renderWorkerTable(response);
    }).catch(err => {
        console.log('[Ghost UI] Device refresh failed:', err);
    });
}

window.__pcControlSubtab = window.__pcControlSubtab || 'devices';
window.__profileIdentityLoaded = false;

function applyPcControlSubtabVisibility(tabName) {
    const selected = ['run-control', 'autoscale', 'identity', 'proton', 'route-plan'].includes(tabName) ? tabName : 'devices';
    const pcSection = document.getElementById('pc-control-section');
    const runControlPanel = document.getElementById('run-control-panel');
    const autoscalePanel = document.getElementById('autoscale-learning-panel');
    const identityPanel = document.getElementById('profile-identity-report-panel');
    const protonPanel = document.getElementById('proton-account-panel');
    const routePlanPanel = document.getElementById('safe-route-plan-panel');
    if (!pcSection) return;

    const managedPanels = new Set([runControlPanel, autoscalePanel, identityPanel, protonPanel, routePlanPanel].filter(Boolean));

    Array.from(pcSection.children).forEach(child => {
        if (child.classList.contains('device-health-header')) {
            child.style.display = '';
            return;
        }

        if (managedPanels.has(child)) {
            const shouldShow = (
                (child === runControlPanel && selected === 'run-control') ||
                (child === autoscalePanel && selected === 'autoscale') ||
                (child === identityPanel && selected === 'identity') ||
                (child === protonPanel && selected === 'proton') ||
                (child === routePlanPanel && selected === 'route-plan')
            );
            child.style.display = shouldShow ? 'block' : 'none';
            return;
        }

        if (selected !== 'devices') {
            child.dataset.hiddenByIdentityTab = '1';
            child.style.display = 'none';
        } else if (child.dataset.hiddenByIdentityTab === '1') {
            child.style.display = '';
            delete child.dataset.hiddenByIdentityTab;
        }
    });

    const summary = document.getElementById('device-health-summary');
    const deviceTable = document.querySelector('#pc-control-section .device-health-table');
    if (selected === 'devices') {
        if (summary) summary.style.display = 'grid';
        if (deviceTable) deviceTable.style.display = 'table';
        if (runControlPanel) runControlPanel.style.display = 'none';
        if (autoscalePanel) autoscalePanel.style.display = 'none';
        if (identityPanel) identityPanel.style.display = 'none';
        if (protonPanel) protonPanel.style.display = 'none';
        if (routePlanPanel) routePlanPanel.style.display = 'none';
    }
}

function showPcControlSubtab(tabName) {
    const selected = ['run-control', 'autoscale', 'identity', 'proton', 'route-plan'].includes(tabName) ? tabName : 'devices';
    window.__pcControlSubtab = selected;

    const devicesBtn = document.getElementById('pc-control-tab-devices');
    const runControlBtn = document.getElementById('pc-control-tab-run-control');
    const autoscaleBtn = document.getElementById('pc-control-tab-autoscale');
    const identityBtn = document.getElementById('pc-control-tab-identity');
    const protonBtn = document.getElementById('pc-control-tab-proton');
    const routePlanBtn = document.getElementById('pc-control-tab-route-plan');

    if (devicesBtn) devicesBtn.classList.toggle('active', selected === 'devices');
    if (runControlBtn) runControlBtn.classList.toggle('active', selected === 'run-control');
    if (autoscaleBtn) autoscaleBtn.classList.toggle('active', selected === 'autoscale');
    if (identityBtn) identityBtn.classList.toggle('active', selected === 'identity');
    if (protonBtn) protonBtn.classList.toggle('active', selected === 'proton');
    if (routePlanBtn) routePlanBtn.classList.toggle('active', selected === 'route-plan');

    applyPcControlSubtabVisibility(selected);

    if (selected === 'run-control') {
        refreshRunControlCenter();
    } else if (selected === 'autoscale') {
        refreshAutoscaleLearningPanel();
    } else if (selected === 'identity') {
        refreshProfileIdentityReport();
    } else if (selected === 'proton') {
        refreshProtonAccountPanel();
    } else if (selected === 'route-plan') {
        refreshSafeRoutePlan();
    } else {
        refreshWorkerTable();
    }
}

function profileIdentityStatus(message, isBad = false) {
    const status = document.getElementById('profile-identity-status');
    if (!status) return;
    status.textContent = message || '';
    status.classList.toggle('bad', Boolean(isBad));
}

function renderProfileIdentitySummary(summary) {
    const target = document.getElementById('profile-identity-summary');
    if (!target) return;

    const data = summary || {};
    const okClass = data.ok ? 'identity-status-ok' : 'identity-status-warn';

    target.innerHTML = `
        <div class="profile-identity-card">
            <span>Total Profiles</span>
            <strong>${escapeHtml(data.total || 0)}</strong>
        </div>
        <div class="profile-identity-card">
            <span>Desktop / PC</span>
            <strong>${escapeHtml(data.desktop_count || 0)} <small>${escapeHtml(data.desktop_percent || 0)}%</small></strong>
        </div>
        <div class="profile-identity-card">
            <span>Mobile / Tablet</span>
            <strong>${escapeHtml(data.mobile_count || 0)}</strong>
        </div>
        <div class="profile-identity-card">
            <span>Unique</span>
            <strong class="${okClass}">${escapeHtml(data.unique_count || 0)}</strong>
        </div>
        <div class="profile-identity-card">
            <span>Duplicate Identities</span>
            <strong class="${data.duplicate_identity_count ? 'identity-status-warn' : 'identity-status-ok'}">${escapeHtml(data.duplicate_identity_count || 0)}</strong>
        </div>
        <div class="profile-identity-card">
            <span>Duplicate Models</span>
            <strong class="${data.duplicate_model_count ? 'identity-status-warn' : 'identity-status-ok'}">${escapeHtml(data.duplicate_model_count || 0)}</strong>
        </div>
    `;
}

function renderProfileIdentityReport(response) {
    const meta = document.getElementById('profile-identity-meta');
    const tbody = document.getElementById('profile-identity-table-body');
    if (!tbody) return;

    const rows = response && Array.isArray(response.rows) ? response.rows : [];
    const summary = response && response.summary ? response.summary : {};

    if (meta) {
        const source = response && response.source ? String(response.source).toUpperCase() : 'UNKNOWN';
        const generatedAt = response && response.generated_at ? response.generated_at : '';
        meta.textContent = `Source: ${source}${generatedAt ? ' | Updated: ' + generatedAt : ''}`;
    }

    renderProfileIdentitySummary(summary);

    if (!rows.length) {
        tbody.innerHTML = `<tr><td colspan="16">No profile identities found.</td></tr>`;
        profileIdentityStatus('No profile identity records found.', true);
        return;
    }

    tbody.innerHTML = '';

    rows.forEach(row => {
        const resultText = row.identity_status || 'Unique';
        const isWarn = resultText !== 'Unique';
        const typeClass = String(row.type || '').toLowerCase() === 'desktop'
            ? 'identity-type-desktop'
            : 'identity-type-mobile';

        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${escapeHtml(row.id)}</td>
            <td>${escapeHtml(row.name)}</td>
            <td>${escapeHtml(row.status)}</td>
            <td><span class="profile-identity-type ${typeClass}">${escapeHtml(row.type || 'Unknown')}</span></td>
            <td>${escapeHtml(row.device_name || 'Missing')}</td>
            <td>${escapeHtml(`${row.os || ''} ${row.os_version || ''}`.trim())}</td>
            <td>${escapeHtml(row.viewport)}</td>
            <td>${escapeHtml(row.language)}</td>
            <td>${escapeHtml(row.platform)}</td>
            <td>${escapeHtml(row.hardware_concurrency)}</td>
            <td>${escapeHtml(row.device_memory)}</td>
            <td>${escapeHtml(row.touch_points)}</td>
            <td><code>${escapeHtml(row.user_agent_hash)}</code></td>
            <td><code>${escapeHtml(row.identity_hash)}</code></td>
            <td><code>${escapeHtml(row.signature_hash)}</code></td>
            <td><span class="${isWarn ? 'identity-status-warn' : 'identity-status-ok'}">${escapeHtml(resultText)}</span></td>
        `;
        tbody.appendChild(tr);
    });

    profileIdentityStatus(summary.ok ? 'Profile identity report loaded.' : 'Profile identity report loaded with warnings.', !summary.ok);
}

function refreshProfileIdentityReport() {
    applyPcControlSubtabVisibility('identity');

    if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_profile_identity_report !== 'function') {
        profileIdentityStatus('Backend bridge missing: get_profile_identity_report', true);
        return;
    }

    profileIdentityStatus('Loading profile identity report...');

    window.pywebview.api.get_profile_identity_report().then(response => {
        if (!response || response.ok === false) {
            profileIdentityStatus(response && response.error ? response.error : 'Could not load profile identity report.', true);
            renderProfileIdentitySummary({});
            const tbody = document.getElementById('profile-identity-table-body');
            if (tbody) tbody.innerHTML = `<tr><td colspan="16">Profile identity report failed.</td></tr>`;
            return;
        }
        window.__profileIdentityLoaded = true;
        renderProfileIdentityReport(response);
    }).catch(err => {
        profileIdentityStatus(String(err), true);
    });
}

function protonAccountStatus(message, isBad = false) {
    const status = document.getElementById('proton-account-status');
    if (!status) return;
    status.textContent = message || '';
    status.classList.toggle('bad', Boolean(isBad));
}

function protonReadinessClass(status, ready) {
    const normalized = String(status || '').toUpperCase();
    if (ready || normalized === 'READY') return 'proton-ready-ok';
    if (normalized === 'BLOCKED') return 'proton-ready-bad';
    if (normalized === 'SETUP_OPENED') return 'proton-ready-warn';
    return 'proton-ready-warn';
}

function protonReadinessLabel(status, ready) {
    const normalized = String(status || '').toUpperCase();
    if (ready || normalized === 'READY') return 'READY';
    if (normalized === 'SETUP_OPENED') return 'SETUP OPENED';
    if (normalized === 'BLOCKED') return 'BLOCKED';
    return 'NEEDS LOGIN';
}

function ensureProtonReadinessPanel() {
    let panel = document.getElementById('proton-readiness-panel');
    if (panel) return panel;

    const accountPanel = document.getElementById('proton-account-panel');
    if (!accountPanel) return null;

    panel = document.createElement('div');
    panel.id = 'proton-readiness-panel';
    panel.className = 'proton-readiness-panel';
    panel.innerHTML = `
        <div class="proton-readiness-header">
            <div>
                <h3>Proton Profile Readiness</h3>
                <div class="proton-account-meta">Launch Guard only allows profiles marked READY.</div>
            </div>
            <button class="btn btn-secondary" onclick="refreshProtonAccountPanel()">REFRESH READINESS</button>
        </div>
        <div id="proton-readiness-summary" class="proton-readiness-summary"></div>
        <div class="proton-readiness-table-wrap">
            <table class="ghost-table proton-readiness-table">
                <thead>
                    <tr>
                        <th>Profile</th>
                        <th>Account</th>
                        <th>Status</th>
                        <th>Launch Guard</th>
                        <th>Reason</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody id="proton-readiness-table-body">
                    <tr><td colspan="6">No readiness data loaded.</td></tr>
                </tbody>
            </table>
        </div>
    `;

    accountPanel.appendChild(panel);
    return panel;
}

function renderProtonReadinessPanel(response) {
    const panel = ensureProtonReadinessPanel();
    if (!panel) return;

    const summaryTarget = document.getElementById('proton-readiness-summary');
    const tbody = document.getElementById('proton-readiness-table-body');
    if (!tbody) return;

    const profiles = response && Array.isArray(response.profile_readiness) ? response.profile_readiness : [];
    const summary = response && response.summary ? response.summary : {};

    if (summaryTarget) {
        summaryTarget.innerHTML = `
            <div class="proton-account-card"><span>Ready</span><strong class="identity-status-ok">${escapeHtml(summary.ready_profiles || 0)}</strong></div>
            <div class="proton-account-card"><span>Needs Login</span><strong class="identity-status-warn">${escapeHtml(summary.needs_login_profiles || 0)}</strong></div>
            <div class="proton-account-card"><span>Setup Opened</span><strong class="identity-status-warn">${escapeHtml(summary.setup_opened_profiles || 0)}</strong></div>
            <div class="proton-account-card"><span>Blocked</span><strong class="identity-status-warn">${escapeHtml(summary.blocked_profiles || 0)}</strong></div>
        `;
    }

    if (!profiles.length) {
        tbody.innerHTML = `<tr><td colspan="6">No profiles found for Proton readiness.</td></tr>`;
        return;
    }

    tbody.innerHTML = '';
    profiles.forEach(row => {
        const profileId = parseInt(row.profile_id);
        const ready = Boolean(row.ready || row.launch_ready);
        const status = row.setup_status || 'NEEDS_LOGIN';
        const statusClass = protonReadinessClass(status, ready);
        const guardText = ready ? 'ALLOWED' : 'BLOCKED';
        const guardClass = ready ? 'proton-ready-ok' : 'proton-ready-bad';
        const accountText = row.account_label ? `${row.account_label}${row.username ? ' / ' + row.username : ''}` : 'No account assigned';

        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${escapeHtml(row.profile_name || ('Profile ' + profileId))}</td>
            <td>${escapeHtml(accountText)}</td>
            <td><span class="proton-ready-pill ${statusClass}">${escapeHtml(protonReadinessLabel(status, ready))}</span></td>
            <td><span class="proton-ready-pill ${guardClass}">${escapeHtml(guardText)}</span></td>
            <td>${escapeHtml(row.block_reason || '')}</td>
            <td>
                <div class="proton-ready-actions">
                    <button class="btn btn-secondary proton-ready-btn" onclick="openProtonSetupProfile(${profileId})">OPEN SETUP</button>
                    <button class="btn btn-primary proton-ready-btn" onclick="setProfileProtonStatus(${profileId}, 'READY')">READY</button>
                    <button class="btn btn-secondary proton-ready-btn" onclick="setProfileProtonStatus(${profileId}, 'NEEDS_LOGIN')">NEEDS LOGIN</button>
                    <button class="btn btn-danger proton-ready-btn" onclick="setProfileProtonStatus(${profileId}, 'BLOCKED')">BLOCK</button>
                </div>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function renderProtonAccountPanel(response) {
    const summaryTarget = document.getElementById('proton-account-summary');
    const tbody = document.getElementById('proton-account-table-body');
    if (!tbody) return;

    const accounts = response && Array.isArray(response.accounts) ? response.accounts : [];
    const summary = response && response.summary ? response.summary : {};

    if (summaryTarget) {
        summaryTarget.innerHTML = `
            <div class="proton-account-card">
                <span>Accounts</span>
                <strong>${escapeHtml(summary.account_count || 0)}</strong>
            </div>
            <div class="proton-account-card">
                <span>Total Profiles</span>
                <strong>${escapeHtml(summary.total_profiles || 0)}</strong>
            </div>
            <div class="proton-account-card">
                <span>Assigned</span>
                <strong>${escapeHtml(summary.assigned_profiles || 0)}</strong>
            </div>
            <div class="proton-account-card">
                <span>Ready</span>
                <strong class="identity-status-ok">${escapeHtml(summary.ready_profiles || 0)}</strong>
            </div>
            <div class="proton-account-card">
                <span>Unassigned</span>
                <strong class="${summary.unassigned_profiles ? 'identity-status-warn' : 'identity-status-ok'}">${escapeHtml(summary.unassigned_profiles || 0)}</strong>
            </div>
        `;
    }

    const headerRow = tbody.closest('table')?.querySelector('thead tr');
    if (headerRow && !headerRow.dataset.patch006Ready) {
        headerRow.dataset.patch006Ready = '1';
        headerRow.innerHTML = `
            <th>ID</th>
            <th>Label</th>
            <th>Username</th>
            <th>Profile Limit</th>
            <th>Assigned</th>
            <th>Ready</th>
            <th>Profiles</th>
            <th>Status</th>
        `;
    }

    if (!accounts.length) {
        tbody.innerHTML = `<tr><td colspan="8">No Proton accounts imported.</td></tr>`;
        renderProtonReadinessPanel(response || {});
        protonAccountStatus('No Proton accounts imported yet. Import accounts, then profiles can be assigned.');
        return;
    }

    tbody.innerHTML = '';
    accounts.forEach(account => {
        const active = account.active ? 'ACTIVE' : 'OFF';
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${escapeHtml(account.id)}</td>
            <td>${escapeHtml(account.label)}</td>
            <td>${escapeHtml(account.username)}</td>
            <td>${escapeHtml(account.max_profiles)}</td>
            <td>${escapeHtml(account.assigned_count)}</td>
            <td>${escapeHtml(account.ready_count || 0)}</td>
            <td>${escapeHtml(account.profile_ids || '')}</td>
            <td><span class="${account.active ? 'identity-status-ok' : 'identity-status-warn'}">${escapeHtml(active)}</span></td>
        `;
        tbody.appendChild(tr);
    });

    renderProtonReadinessPanel(response);
    protonAccountStatus('Proton account vault loaded. Launch Guard is enforcing Proton Ready status.');
}

function refreshProtonAccountPanel() {
    applyPcControlSubtabVisibility('proton');

    if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_proton_account_status !== 'function') {
        protonAccountStatus('Backend bridge missing: get_proton_account_status', true);
        return;
    }

    protonAccountStatus('Loading Proton account vault...');
    window.pywebview.api.get_proton_account_status().then(response => {
        if (!response || response.ok === false) {
            protonAccountStatus(response && response.error ? response.error : 'Could not load Proton account vault.', true);
            return;
        }
        renderProtonAccountPanel(response);
    }).catch(err => {
        protonAccountStatus(String(err), true);
    });
}

function setProfileProtonStatus(profileId, status) {
    if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.set_profile_proton_setup_status !== 'function') {
        protonAccountStatus('Backend bridge missing: set_profile_proton_setup_status', true);
        return;
    }

    protonAccountStatus(`Setting Profile ${profileId} Proton status to ${status}...`);
    window.pywebview.api.set_profile_proton_setup_status(profileId, status, '').then(response => {
        if (!response || response.ok === false) {
            const err = response && (response.error || (response.result && response.result.error));
            protonAccountStatus(err || 'Could not update Proton readiness.', true);
            return;
        }
        protonAccountStatus(`Profile ${profileId} Proton status updated.`);
        renderProtonAccountPanel(response.status || response);
        refreshProfilesAfterCreate();
    }).catch(err => {
        protonAccountStatus(String(err), true);
    });
}

function openProtonSetupProfile(profileId) {
    if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.open_proton_setup_profile !== 'function') {
        protonAccountStatus('Backend bridge missing: open_proton_setup_profile', true);
        return;
    }

    protonAccountStatus(`Opening Profile ${profileId} for manual Proton setup...`);
    window.pywebview.api.open_proton_setup_profile(profileId).then(response => {
        if (!response || response.ok === false) {
            protonAccountStatus(response && response.error ? response.error : 'Could not open Proton setup profile.', true);
            refreshProtonAccountPanel();
            return;
        }
        protonAccountStatus(`Profile ${profileId} opened. Complete Proton login manually, then click READY.`);
        refreshProtonAccountPanel();
    }).catch(err => {
        protonAccountStatus(String(err), true);
    });
}

function readProtonAccountFile() {
    return new Promise(resolve => {
        const input = document.getElementById('proton-account-file');
        if (!input || !input.files || !input.files.length) {
            resolve('');
            return;
        }

        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ''));
        reader.onerror = () => resolve('');
        reader.readAsText(input.files[0]);
    });
}

async function importProtonAccountsFromInput() {
    if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.import_proton_accounts !== 'function') {
        protonAccountStatus('Backend bridge missing: import_proton_accounts', true);
        return;
    }

    const textArea = document.getElementById('proton-account-text');
    const maxInput = document.getElementById('proton-max-profiles');
    const pastedText = textArea ? String(textArea.value || '') : '';
    const fileText = await readProtonAccountFile();
    const accountText = fileText || pastedText;
    const maxProfiles = Math.max(1, parseInt(maxInput && maxInput.value ? maxInput.value : '4', 10) || 4);

    if (!accountText.trim()) {
        protonAccountStatus('Choose a file or paste account lines first.', true);
        return;
    }

    protonAccountStatus('Importing Proton accounts...');

    window.pywebview.api.import_proton_accounts(accountText, maxProfiles).then(response => {
        if (!response || response.ok === false) {
            protonAccountStatus(response && response.error ? response.error : 'Import failed.', true);
            return;
        }
        if (textArea) textArea.value = '';
        protonAccountStatus(`Imported ${response.imported || 0}, updated ${response.updated || 0}, skipped ${response.skipped || 0}.`);
        refreshProtonAccountPanel();
    }).catch(err => {
        protonAccountStatus(String(err), true);
    });
}

function rebalanceProtonAccounts() {
    if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.rebalance_proton_accounts !== 'function') {
        protonAccountStatus('Backend bridge missing: rebalance_proton_accounts', true);
        return;
    }

    const maxInput = document.getElementById('proton-max-profiles');
    const maxProfiles = Math.max(1, parseInt(maxInput && maxInput.value ? maxInput.value : '4', 10) || 4);
    protonAccountStatus('Rebalancing profile assignments...');

    window.pywebview.api.rebalance_proton_accounts(maxProfiles).then(response => {
        if (!response || response.ok === false) {
            protonAccountStatus(response && response.error ? response.error : 'Rebalance failed.', true);
            return;
        }
        const status = response.status || {};
        renderProtonAccountPanel(status);
        protonAccountStatus('Proton account assignments rebalanced.');
    }).catch(err => {
        protonAccountStatus(String(err), true);
    });
}

function safeRoutePlanStatus(message, isBad = false) {
    const status = document.getElementById('safe-route-plan-status');
    if (!status) return;
    status.textContent = message || '';
    status.classList.toggle('bad', Boolean(isBad));
}

function runControlStatus(message, isBad = false) {
    const status = document.getElementById('run-control-status');
    if (!status) return;
    status.textContent = message || '';
    status.classList.toggle('bad', Boolean(isBad));
}

function formatRunControlAge(seconds) {
    const value = Math.max(0, parseInt(seconds || 0, 10) || 0);
    if (value < 60) return `${value}s`;
    const minutes = Math.floor(value / 60);
    const remainder = value % 60;
    if (minutes < 60) return `${minutes}m ${remainder}s`;
    const hours = Math.floor(minutes / 60);
    const minutePart = minutes % 60;
    return `${hours}h ${minutePart}m`;
}

function runControlSeverityClass(severity, warning) {
    const value = String(severity || '').toLowerCase();
    if (warning || value === 'warning') return 'run-control-pill-warn';
    if (value === 'error') return 'run-control-pill-bad';
    return 'run-control-pill-ok';
}

function renderRunControlCenter(response) {
    const summaryTarget = document.getElementById('run-control-summary');
    const tbody = document.getElementById('run-control-table-body');
    const timelineBody = document.getElementById('run-control-timeline-body');
    const watchdogSummary = document.getElementById('run-control-watchdog-summary');
    if (!tbody) return;

    const summary = response && response.summary ? response.summary : {};
    const rows = response && Array.isArray(response.rows) ? response.rows : [];
    const lifecycle = response && response.lifecycle ? response.lifecycle : {};
    const lifecycleEvents = Array.isArray(lifecycle.events) ? lifecycle.events : [];
    const watchdog = response && response.watchdog ? response.watchdog : {};
    const watchdogWarnings = Array.isArray(watchdog.warnings) ? watchdog.warnings : [];

    if (summaryTarget) {
        const cards = [
            ['Total', summary.total || 0],
            ['Active', summary.active || 0],
            ['Launching', summary.launching || 0],
            ['Verified Waiting', summary.verified_waiting || 0],
            ['Stopping', summary.stopping || 0],
            ['Offline', summary.offline || 0],
            ['Quarantined', summary.quarantined || 0],
            ['Watchdog', summary.watchdog_warnings || 0],
            ['Lifecycle Warnings', summary.lifecycle_warnings || 0]
        ];
        summaryTarget.innerHTML = cards.map(([label, value]) => `
            <div class="run-control-card">
                <span>${escapeHtml(label)}</span>
                <strong>${escapeHtml(value)}</strong>
            </div>
        `).join('');
    }

    if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="13">No profile runtime data is available.</td></tr>';
        runControlStatus('No run-control rows available.', true);
        return;
    }

    tbody.innerHTML = '';
    rows.forEach(row => {
        const active = Boolean(row.active_session);
        const quarantined = Boolean(row.quarantined);
        const warning = Boolean(row.watchdog_warning);
        const severityClass = runControlSeverityClass(row.lifecycle_severity, warning);
        const watchdogText = row.watchdog_status || 'OK';
        const tr = document.createElement('tr');
        if (warning) tr.classList.add('run-control-row-warning');
        tr.innerHTML = `
            <td>${escapeHtml(row.profile_id || '')}</td>
            <td>${escapeHtml(row.profile_name || '')}</td>
            <td><span class="${active ? 'identity-status-ok' : 'identity-status-warn'}">${escapeHtml(row.status || '')}</span></td>
            <td>${escapeHtml(row.stage || '')}</td>
            <td><span class="run-control-pill ${severityClass}" title="${escapeHtml(row.lifecycle_stage || '')}">${escapeHtml(row.lifecycle_state || '-')}</span></td>
            <td>${escapeHtml(active ? formatRunControlAge(row.age_seconds || 0) : '-')}</td>
            <td><span class="run-control-watchdog ${warning ? 'bad' : ''}">${escapeHtml(watchdogText)}</span></td>
            <td>${escapeHtml(row.current_target || '')}</td>
            <td>${escapeHtml(row.ip_address || '')}</td>
            <td>${escapeHtml(row.session_id || (active ? 'active' : '-'))}</td>
            <td>${escapeHtml(row.debug_port || '-')}</td>
            <td>${escapeHtml(row.process_state || '-')}</td>
            <td>${quarantined ? `<span class="identity-status-warn">${escapeHtml(row.quarantine_reason || 'Quarantined')}</span>` : 'No'}</td>
        `;
        tbody.appendChild(tr);
    });

    if (watchdogSummary) {
        watchdogSummary.textContent = watchdogWarnings.length
            ? `${watchdogWarnings.length} watchdog warning(s): ${watchdogWarnings.map(w => `Profile ${w.profile_id}`).join(', ')}`
            : 'Watchdog OK. No stuck transitional states detected.';
        watchdogSummary.classList.toggle('bad', watchdogWarnings.length > 0);
    }

    if (timelineBody) {
        if (!lifecycleEvents.length) {
            timelineBody.innerHTML = '<tr><td colspan="8">No lifecycle events recorded yet.</td></tr>';
        } else {
            timelineBody.innerHTML = '';
            lifecycleEvents.slice(0, 40).forEach(event => {
                const eventWarning = ['warning', 'error'].includes(String(event.severity || '').toLowerCase()) || event.state === 'STUCK_WARNING';
                const tr = document.createElement('tr');
                if (eventWarning) tr.classList.add('run-control-row-warning');
                tr.innerHTML = `
                    <td>${escapeHtml(event.created_at || '')}</td>
                    <td>${escapeHtml(event.profile_id || '-')}</td>
                    <td><span class="run-control-pill ${runControlSeverityClass(event.severity, eventWarning)}">${escapeHtml(event.state || '')}</span></td>
                    <td>${escapeHtml(event.status || '')}</td>
                    <td>${escapeHtml(event.stage || '')}</td>
                    <td>${escapeHtml(event.target_platform || '')}</td>
                    <td>${escapeHtml(event.source || '')}</td>
                    <td>${escapeHtml(event.severity || '')}</td>
                `;
                timelineBody.appendChild(tr);
            });
        }
    }

    runControlStatus(`Run-control loaded for ${rows.length} profile(s). Watchdog warnings: ${watchdogWarnings.length}.`, watchdogWarnings.length > 0);
}

function refreshRunControlCenter() {
    applyPcControlSubtabVisibility('run-control');

    if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_run_control_center !== 'function') {
        runControlStatus('Backend bridge missing: get_run_control_center. Restart the dashboard.', true);
        return;
    }

    runControlStatus('Loading run-control status...');
    window.pywebview.api.get_run_control_center().then(response => {
        if (!response || response.ok === false) {
            runControlStatus(response && response.error ? response.error : 'Could not load run-control data.', true);
            renderRunControlCenter({ rows: [], summary: {} });
            return;
        }
        renderRunControlCenter(response);
    }).catch(err => {
        runControlStatus(String(err), true);
    });
}

function runProfileWatchdogScan() {
    applyPcControlSubtabVisibility('run-control');

    if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.run_profile_watchdog_scan !== 'function') {
        runControlStatus('Backend bridge missing: run_profile_watchdog_scan. Restart the dashboard.', true);
        return;
    }

    runControlStatus('Running watchdog scan...');
    window.pywebview.api.run_profile_watchdog_scan().then(response => {
        if (!response || response.ok === false) {
            runControlStatus(response && response.error ? response.error : 'Watchdog scan failed.', true);
            return;
        }
        const count = response.warning_count || 0;
        runControlStatus(count ? `Watchdog found ${count} stuck profile warning(s).` : 'Watchdog scan OK. No stuck transitional states found.', count > 0);
        refreshRunControlCenter();
    }).catch(err => {
        runControlStatus(String(err), true);
    });
}

function autoscaleLearningStatus(message, isBad = false) {
    const status = document.getElementById('autoscale-learning-status');
    if (!status) return;
    status.textContent = message || '';
    status.classList.toggle('bad', Boolean(isBad));
}

function autoscaleNumber(id, fallback) {
    const el = document.getElementById(id);
    const value = parseFloat(el && el.value !== undefined ? el.value : fallback);
    return Number.isFinite(value) ? value : fallback;
}

function collectAutoscaleConfig(enabledOverride = null) {
    return {
        enabled: enabledOverride === null ? undefined : Boolean(enabledOverride),
        target_profiles: autoscaleNumber('autoscale-target-profiles', 3),
        min_profiles: autoscaleNumber('autoscale-min-profiles', 0),
        max_profiles: autoscaleNumber('autoscale-max-profiles', 10),
        cooldown_seconds: autoscaleNumber('autoscale-cooldown', 90),
        loop_interval_seconds: autoscaleNumber('autoscale-loop-interval', 30),
        cpu_high: autoscaleNumber('autoscale-cpu-high', 82),
        ram_high: autoscaleNumber('autoscale-ram-high', 88),
        gpu_high: autoscaleNumber('autoscale-gpu-high', 92),
        manual_mode_only: true,
        close_autoscale_only: true
    };
}

function applyAutoscaleConfigToInputs(config) {
    config = config || {};
    const pairs = [
        ['autoscale-target-profiles', config.target_profiles],
        ['autoscale-min-profiles', config.min_profiles],
        ['autoscale-max-profiles', config.max_profiles],
        ['autoscale-cooldown', config.cooldown_seconds],
        ['autoscale-loop-interval', config.loop_interval_seconds],
        ['autoscale-cpu-high', config.cpu_high],
        ['autoscale-ram-high', config.ram_high],
        ['autoscale-gpu-high', config.gpu_high]
    ];
    pairs.forEach(([id, value]) => {
        const el = document.getElementById(id);
        if (el && value !== undefined && value !== null) el.value = String(value);
    });
}

function renderAutoscaleLearningPanel(response) {
    const summaryTarget = document.getElementById('autoscale-learning-summary');
    const eventBody = document.getElementById('autoscale-events-body');
    const obsBody = document.getElementById('autoscale-observations-body');
    if (!summaryTarget) return;

    const config = response && response.config ? response.config : {};
    const metrics = response && response.metrics ? response.metrics : {};
    const decision = response && response.decision ? response.decision : {};
    const learning = response && response.learning ? response.learning : {};
    const learningSummary = learning.summary || {};
    const events = Array.isArray(learning.autoscale_events) ? learning.autoscale_events : [];
    const observations = Array.isArray(learning.observations) ? learning.observations : [];
    const managed = Array.isArray(response.managed_profile_ids) ? response.managed_profile_ids : [];

    applyAutoscaleConfigToInputs(config);

    summaryTarget.innerHTML = `
        <div class="autoscale-card"><span>Enabled</span><strong>${escapeHtml(config.enabled ? 'YES' : 'NO')}</strong></div>
        <div class="autoscale-card"><span>Action</span><strong>${escapeHtml((decision.action || 'hold').toUpperCase())}</strong></div>
        <div class="autoscale-card"><span>Active / Desired</span><strong>${escapeHtml(metrics.active_profiles || 0)} / ${escapeHtml(decision.desired_profiles || 0)}</strong></div>
        <div class="autoscale-card"><span>Safe Limit</span><strong>${escapeHtml(metrics.safe_limit || 0)}</strong></div>
        <div class="autoscale-card"><span>CPU / RAM / GPU</span><strong>${escapeHtml(metrics.cpu || 0)} / ${escapeHtml(metrics.ram_percent || 0)} / ${escapeHtml(metrics.gpu || 0)}</strong></div>
        <div class="autoscale-card"><span>Managed</span><strong>${escapeHtml(managed.length)}</strong></div>
        <div class="autoscale-card"><span>Observations</span><strong>${escapeHtml(learningSummary.observation_count || 0)}</strong></div>
        <div class="autoscale-card"><span>Avg Reward</span><strong>${escapeHtml(learningSummary.average_reward || 0)}</strong></div>
    `;

    if (eventBody) {
        if (!events.length) {
            eventBody.innerHTML = '<tr><td colspan="6">No autoscale events yet.</td></tr>';
        } else {
            eventBody.innerHTML = '';
            events.slice(0, 12).forEach(row => {
                const details = row.details || {};
                const reward = details.reward !== undefined ? details.reward : '';
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${escapeHtml(row.created_at || '')}</td>
                    <td>${escapeHtml(row.action || '')}</td>
                    <td>${escapeHtml(row.reason || '')}</td>
                    <td>${escapeHtml(row.active_profiles || 0)}</td>
                    <td>${escapeHtml(row.desired_profiles || 0)}</td>
                    <td>${escapeHtml(reward)}</td>
                `;
                eventBody.appendChild(tr);
            });
        }
    }

    if (obsBody) {
        if (!observations.length) {
            obsBody.innerHTML = '<tr><td colspan="6">No learning observations yet.</td></tr>';
        } else {
            obsBody.innerHTML = '';
            observations.slice(0, 12).forEach(row => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${escapeHtml(row.created_at || '')}</td>
                    <td>${escapeHtml(row.event_type || '')}</td>
                    <td>${escapeHtml(row.profile_id || '-')}</td>
                    <td>${escapeHtml(row.action || '')}</td>
                    <td>${escapeHtml(row.action_result || '')}</td>
                    <td>${escapeHtml(row.reward || 0)}</td>
                `;
                obsBody.appendChild(tr);
            });
        }
    }

    autoscaleLearningStatus(`Autoscale loaded. Decision: ${(decision.action || 'hold').toUpperCase()} - ${decision.reason || ''}`);
}

function refreshAutoscaleLearningPanel() {
    applyPcControlSubtabVisibility('autoscale');

    if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_autoscale_learning_status !== 'function') {
        autoscaleLearningStatus('Backend bridge missing: get_autoscale_learning_status. Restart the dashboard.', true);
        return;
    }

    autoscaleLearningStatus('Loading autoscale and learning status...');
    window.pywebview.api.get_autoscale_learning_status().then(response => {
        if (!response || response.ok === false) {
            autoscaleLearningStatus(response && response.error ? response.error : 'Could not load autoscale status.', true);
            return;
        }
        renderAutoscaleLearningPanel(response);
    }).catch(err => {
        autoscaleLearningStatus(String(err), true);
    });
}

function saveAutoscaleConfig(enabled) {
    if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.set_autoscale_config !== 'function') {
        autoscaleLearningStatus('Backend bridge missing: set_autoscale_config. Restart the dashboard.', true);
        return;
    }

    const payload = collectAutoscaleConfig(Boolean(enabled));
    autoscaleLearningStatus(enabled ? 'Saving and enabling autoscale...' : 'Saving autoscale config disabled...');

    window.pywebview.api.set_autoscale_config(payload).then(response => {
        if (!response || response.ok === false) {
            autoscaleLearningStatus(response && response.error ? response.error : 'Autoscale config save failed.', true);
            return;
        }
        autoscaleLearningStatus(enabled ? 'Autoscale enabled.' : 'Autoscale config saved disabled.');
        refreshAutoscaleLearningPanel();
    }).catch(err => {
        autoscaleLearningStatus(String(err), true);
    });
}

function disableAutoscale() {
    saveAutoscaleConfig(false);
}

function runAutoscaleDryRun() {
    if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.run_autoscale_once !== 'function') {
        autoscaleLearningStatus('Backend bridge missing: run_autoscale_once. Restart the dashboard.', true);
        return;
    }

    autoscaleLearningStatus('Running autoscale dry run...');
    window.pywebview.api.run_autoscale_once(true, 'dashboard_dry_run').then(response => {
        if (!response || response.ok === false) {
            autoscaleLearningStatus(response && response.error ? response.error : 'Autoscale dry run failed.', true);
            return;
        }
        renderAutoscaleLearningPanel(response);
        autoscaleLearningStatus(`Dry run complete: ${(response.decision || {}).action || 'hold'}.`);
    }).catch(err => {
        autoscaleLearningStatus(String(err), true);
    });
}

function runAutoscaleNow() {
    if (!confirm('Run one autoscale cycle now? Scale-up opens manual-mode profile browsers only.')) {
        return;
    }

    if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.run_autoscale_once !== 'function') {
        autoscaleLearningStatus('Backend bridge missing: run_autoscale_once. Restart the dashboard.', true);
        return;
    }

    autoscaleLearningStatus('Running autoscale once...');
    window.pywebview.api.run_autoscale_once(false, 'dashboard_run_once').then(response => {
        if (!response || response.ok === false) {
            autoscaleLearningStatus(response && response.error ? response.error : 'Autoscale run failed.', true);
            return;
        }
        renderAutoscaleLearningPanel(response);
        autoscaleLearningStatus(`Autoscale run complete. Launched ${(response.launched_ids || []).length}, closed ${(response.closed_ids || []).length}.`);
        refreshRunControlCenter();
    }).catch(err => {
        autoscaleLearningStatus(String(err), true);
    });
}

function renderSafeRoutePlan(response) {
    const summaryTarget = document.getElementById('safe-route-plan-summary');
    const tbody = document.getElementById('safe-route-plan-table-body');
    if (!tbody) return;

    const summary = response && response.summary ? response.summary : {};
    const rows = response && Array.isArray(response.plan) ? response.plan : [];

    if (summaryTarget) {
        const active = Array.isArray(summary.active_platforms) ? summary.active_platforms.join(', ') : '';
        const routePlanId = summary.route_plan_id || response.route_plan_id || '';
        summaryTarget.innerHTML = `
            <div class="safe-route-plan-card">
                <span>Profiles Planned</span>
                <strong>${escapeHtml(summary.profile_count || 0)}</strong>
            </div>
            <div class="safe-route-plan-card">
                <span>Active Platforms</span>
                <strong>${escapeHtml(active || 'None')}</strong>
            </div>
            <div class="safe-route-plan-card">
                <span>Per Profile</span>
                <strong>${escapeHtml(summary.platforms_per_profile || 0)}</strong>
            </div>
            <div class="safe-route-plan-card">
                <span>Mode</span>
                <strong>${escapeHtml(summary.safe_mode ? 'SAFE PLAN' : 'UNKNOWN')}</strong>
            </div>
            <div class="safe-route-plan-card">
                <span>Saved Plan</span>
                <strong>${escapeHtml(routePlanId ? ('#' + routePlanId) : (summary.persisted ? 'YES' : 'NO'))}</strong>
            </div>
        `;
    }

    if (!rows.length) {
        tbody.innerHTML = '<tr><td colspan="8">No route plan available. Turn on at least one platform and refresh.</td></tr>';
        safeRoutePlanStatus('No route plan available.', true);
        return;
    }

    tbody.innerHTML = '';
    rows.forEach(row => {
        const tr = document.createElement('tr');
        const platforms = Array.isArray(row.planned_platforms) ? row.planned_platforms.join(' -> ') : '';
        tr.innerHTML = `
            <td>${escapeHtml(row.order || '')}</td>
            <td>${escapeHtml(row.profile_name || ('Profile ' + row.profile_id))}</td>
            <td>${escapeHtml(row.last_platform || 'None')}</td>
            <td><strong>${escapeHtml(platforms)}</strong></td>
            <td>${escapeHtml(row.random_warmup_seconds || 30)}s</td>
            <td>${escapeHtml(row.session_minutes || 180)}m</td>
            <td>${escapeHtml(row.target_policy || 'Planning only')}</td>
            <td>${escapeHtml(row.notes || '')}</td>
        `;
        tbody.appendChild(tr);
    });

    const savedLabel = summary.route_plan_id || response.route_plan_id
        ? ` Saved as plan #${summary.route_plan_id || response.route_plan_id}.`
        : '';
    safeRoutePlanStatus(`Safe route plan loaded for ${rows.length} profile(s).${savedLabel}`);
}

function refreshSafeRoutePlan() {
    applyPcControlSubtabVisibility('route-plan');

    if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_safe_automation_route_plan !== 'function') {
        safeRoutePlanStatus('Backend bridge missing: get_safe_automation_route_plan. Restart the dashboard.', true);
        return;
    }

    const activePlatforms = typeof getActivePlatforms === 'function' ? getActivePlatforms() : [];
    safeRoutePlanStatus('Building safe randomized route plan...');

    window.pywebview.api.get_safe_automation_route_plan(activePlatforms).then(response => {
        if (!response || response.ok === false) {
            safeRoutePlanStatus(response && response.error ? response.error : 'Could not build route plan.', true);
            renderSafeRoutePlan({ plan: [], summary: {} });
            return;
        }
        renderSafeRoutePlan(response);
    }).catch(err => {
        safeRoutePlanStatus(String(err), true);
    });
}

setInterval(function () {
    const pcControlSection = document.getElementById('pc-control-section');
    if (pcControlSection && pcControlSection.style.display !== 'none' && window.__pcControlSubtab === 'identity') {
        applyPcControlSubtabVisibility('identity');
    }
}, 1000);

setInterval(function () {
    const pcControlSection = document.getElementById('pc-control-section');
    if (pcControlSection && pcControlSection.style.display !== 'none' && window.__pcControlSubtab === 'run-control') {
        refreshRunControlCenter();
    }
}, 7000);

setInterval(function () {
    const pcControlSection = document.getElementById('pc-control-section');
    if (pcControlSection && pcControlSection.style.display !== 'none' && window.__pcControlSubtab === 'autoscale') {
        refreshAutoscaleLearningPanel();
    }
}, 10000);

function blockWorker(pcId) {
    if (!pcId) return;

    if (!confirm(`Block device ${pcId} from running profiles?`)) {
        return;
    }

    if (window.pywebview && window.pywebview.api && typeof window.pywebview.api.block_worker === 'function') {
        window.pywebview.api.block_worker(pcId).then(response => {
            console.log('[Ghost UI] Block device result:', response);
            refreshWorkerTable();
        });
    }
}

function unblockWorker(pcId) {
    if (!pcId) return;

    if (!confirm(`Unblock device ${pcId}?`)) {
        return;
    }

    if (window.pywebview && window.pywebview.api && typeof window.pywebview.api.unblock_worker === 'function') {
        window.pywebview.api.unblock_worker(pcId).then(response => {
            console.log('[Ghost UI] Unblock device result:', response);
            refreshWorkerTable();
        });
    }
}

setInterval(function () {
    const pcControlSection = document.getElementById('pc-control-section');
    if (pcControlSection && pcControlSection.style.display !== 'none') {
        refreshWorkerTable();
    }
}, 5000);


// ==============================
// ANALYTICS TAB
// ==============================

function formatMoney(value) {
    const n = Number(value || 0);
    return "$" + n.toFixed(6);
}

function formatMoneyCompact(value) {
    const n = Number(value || 0);
    if (Math.abs(n) >= 1) return "$" + n.toFixed(2);
    return "$" + n.toFixed(6);
}

function formatMetricCount(value) {
    const n = Number(value || 0);
    if (!Number.isFinite(n)) return "0";
    if (Math.abs(n - Math.round(n)) < 0.000001) return String(Math.round(n));
    return n.toFixed(2);
}

function safeText(value) {
    return escapeHtml(value === undefined || value === null ? "" : String(value));
}

// ==============================
// PROFILE RELIABILITY SCORE
// ==============================

function reliabilityClampScore(value) {
    const n = Number(value || 0);
    if (!Number.isFinite(n)) return 0;
    return Math.max(0, Math.min(100, Math.round(n)));
}

function reliabilityTimeValue(row) {
    const candidates = [
        row && row.event_ts,
        row && row.last_event,
        row && row.ended_at,
        row && row.started_at
    ];

    for (const raw of candidates) {
        const parsed = Date.parse(raw || "");
        if (!Number.isNaN(parsed)) return parsed;
    }

    const idVal = Number(row && row.id ? row.id : 0);
    return Number.isFinite(idVal) ? idVal : 0;
}

function reliabilityText(row) {
    return [
        row && row.event_type,
        row && row.ip_status,
        row && row.status,
        row && row.close_reason,
        row && row.details,
        row && row.platform
    ].map(v => String(v || "").toUpperCase()).join(" ");
}

function reliabilityHas(row, terms) {
    const text = reliabilityText(row);
    return terms.some(term => text.includes(String(term).toUpperCase()));
}

function reliabilityGrade(score) {
    const s = Number(score || 0);

    if (s >= 85) {
        return {
            key: "reliable",
            label: "Reliable",
            className: "reliability-good"
        };
    }

    if (s >= 60) {
        return {
            key: "watch",
            label: "Watch",
            className: "reliability-watch"
        };
    }

    if (s >= 30) {
        return {
            key: "weak",
            label: "Weak",
            className: "reliability-weak"
        };
    }

    return {
        key: "bad",
        label: "Bad",
        className: "reliability-bad"
    };
}

function reliabilityIssueLabel(issueKey) {
    const labels = {
        blacklisted_ip: "Blacklisted IP",
        home_ip: "Home IP detected",
        selenium_failed: "Selenium failed",
        ip_failed: "IP check failed",
        platform_failed: "Platform/page failed",
        browser_closed: "Browser closed",
        short_session: "Short session",
        errors: "Errors detected",
        no_events: "No events yet",
        healthy: "No major issue"
    };

    return labels[issueKey] || issueKey || "Unknown";
}

function calculateProfileReliability(profile, events, sessions) {
    const profileId = String(profile.profile_id || profile.id || "").trim();

    const profileEvents = events.filter(row => String(row.profile_id || "").trim() === profileId);
    const profileSessions = sessions.filter(row => String(row.profile_id || "").trim() === profileId);

    let score = 100;
    const issues = [];
    const positives = [];

    const hasBlacklisted = profileEvents.some(row => reliabilityHas(row, ["BLACKLISTED", "IP_BLACKLISTED_BLOCKED"]));
    const hasHomeIp = profileEvents.some(row => reliabilityHas(row, ["HOME_IP", "HOME IP DETECTED", "HOME_IP_BLOCKED"]));
    const hasSeleniumFailed = profileEvents.some(row => reliabilityHas(row, ["SELENIUM_ATTACH_FAILED", "COULD NOT ATTACH SELENIUM"]));
    const hasIpFailed = profileEvents.some(row => reliabilityHas(row, ["IP_CHECK_FAILED", "IP_GUARD_ERROR", "IP verification failed", "Could not detect"]));
    const hasPlatformFailed = profileEvents.some(row => reliabilityHas(row, ["PLATFORM_PAGE_OPEN_FAILED", "NO_RUNNER_FOUND", "PAGE_FAILED", "TARGET_FAILED"]));
    const hasBrowserClosed = profileEvents.some(row => reliabilityHas(row, ["BROWSER_CLOSED", "browser_closed", "unexpectedly"]));

    const errorEvents = profileEvents.filter(row => {
        return reliabilityHas(row, [
            "ERROR",
            "FAILED",
            "BLOCKED",
            "BLACKLISTED",
            "HOME_IP",
            "CRITICAL"
        ]);
    });

    const shortSessions = profileSessions.filter(row => {
        const seconds = Number(row.duration_seconds || 0);
        const status = String(row.status || "").toUpperCase();
        return seconds > 0 && seconds < 60 && !status.includes("RUNNING");
    });

    const ipVerifiedCount = profileEvents.filter(row => reliabilityHas(row, ["IP_VERIFIED"])).length;
    const seleniumAttachedCount = profileEvents.filter(row => reliabilityHas(row, ["SELENIUM_ATTACHED"])).length;
    const browserLaunchedCount = profileEvents.filter(row => reliabilityHas(row, ["BROWSER_LAUNCHED"])).length;
    const platformOpenedCount = profileEvents.filter(row => reliabilityHas(row, ["PLATFORM_SELECTED", "PLATFORM_OPENED", "PAGE_OPENED", "PAGE_LOADED"])).length;
    const normalEndedCount = profileEvents.filter(row => reliabilityHas(row, ["SESSION_ENDED", "SESSION_ENDING"])).length;

    if (hasBlacklisted) {
        score -= 35;
        issues.push("blacklisted_ip");
    }

    if (hasHomeIp) {
        score -= 35;
        issues.push("home_ip");
    }

    if (hasSeleniumFailed) {
        score -= 20;
        issues.push("selenium_failed");
    }

    if (hasIpFailed) {
        score -= 18;
        issues.push("ip_failed");
    }

    if (hasPlatformFailed) {
        score -= 15;
        issues.push("platform_failed");
    }

    if (hasBrowserClosed) {
        score -= 10;
        issues.push("browser_closed");
    }

    if (shortSessions.length > 0) {
        score -= Math.min(20, shortSessions.length * 10);
        issues.push("short_session");
    }

    if (errorEvents.length > 0) {
        score -= Math.min(25, errorEvents.length * 3);
        issues.push("errors");
    }

    if (ipVerifiedCount > 0) {
        score += Math.min(10, ipVerifiedCount * 3);
        positives.push("IP verified");
    }

    if (seleniumAttachedCount > 0) {
        score += Math.min(8, seleniumAttachedCount * 2);
        positives.push("Selenium attached");
    }

    if (browserLaunchedCount > 0) {
        score += Math.min(6, browserLaunchedCount * 2);
        positives.push("Browser launched");
    }

    if (platformOpenedCount > 0) {
        score += Math.min(10, platformOpenedCount * 3);
        positives.push("Platform opened");
    }

    if (normalEndedCount > 0) {
        score += Math.min(6, normalEndedCount * 2);
        positives.push("Normal ending");
    }

    if (!profileEvents.length && !profileSessions.length) {
        score = 50;
        issues.push("no_events");
    }

    score = reliabilityClampScore(score);

    const lastEvent = profileEvents
        .slice()
        .sort((a, b) => reliabilityTimeValue(b) - reliabilityTimeValue(a))[0] || null;

    const lastSession = profileSessions
        .slice()
        .sort((a, b) => reliabilityTimeValue(b) - reliabilityTimeValue(a))[0] || null;

    const grade = reliabilityGrade(score);

    const distinctSessionIds = new Set();

    profileEvents.forEach(row => {
        const sid = String(row.session_id || "").trim();
        if (sid) distinctSessionIds.add(sid);
    });

    profileSessions.forEach(row => {
        const sid = String(row.session_id || "").trim();
        if (sid) distinctSessionIds.add(sid);
    });

    const lastPlatform =
        (lastEvent && lastEvent.platform) ||
        (lastSession && lastSession.platform) ||
        profile.target_platform ||
        "None";

    const lastIp =
        (lastEvent && (lastEvent.ip_label || lastEvent.ip_address)) ||
        (lastSession && (lastSession.final_ip || lastSession.starting_ip)) ||
        profile.last_ip ||
        "Unknown";

    return {
        profile_id: profileId,
        profile_name: profile.profile_name || profile.name || ("Profile " + profileId),
        score,
        grade_key: grade.key,
        grade_label: grade.label,
        grade_class: grade.className,
        status: profile.status || "UNKNOWN",
        last_platform: lastPlatform,
        last_ip: lastIp,
        session_count: distinctSessionIds.size || profileSessions.length || 0,
        event_count: profileEvents.length,
        error_count: errorEvents.length,
        main_issue: issues.length ? issues[0] : "healthy",
        issue_count: issues.length,
        positives,
        last_event: (lastEvent && lastEvent.event_ts) || (lastSession && (lastSession.ended_at || lastSession.started_at)) || "",
        last_session_id: (lastEvent && lastEvent.session_id) || (lastSession && lastSession.session_id) || "",
        quarantined: Number(profile.quarantined || 0) === 1,
        quarantine_score: Number(profile.quarantine_score || score || 0),
        quarantine_reason: profile.quarantine_reason || "",
        quarantine_source: profile.quarantine_source || "",
        quarantined_at: profile.quarantined_at || "",
        raw_events: profileEvents
    };
}

function getProfileReliabilityRows(data) {
    const profiles = Array.isArray(data && data.profiles) ? data.profiles : [];
    const events = Array.isArray(data && data.events) ? data.events : [];
    const sessions = Array.isArray(data && data.sessions) ? data.sessions : [];

    const profileMap = new Map();

    profiles.forEach(profile => {
        const id = String(profile.profile_id || profile.id || "").trim();
        if (id) profileMap.set(id, profile);
    });

    events.forEach(event => {
        const id = String(event.profile_id || "").trim();
        if (id && !profileMap.has(id)) {
            profileMap.set(id, {
                profile_id: id,
                profile_name: "Profile " + id,
                status: "UNKNOWN",
                target_platform: event.platform || "Unknown",
                last_ip: event.ip_label || event.ip_address || "Unknown"
            });
        }
    });

    sessions.forEach(session => {
        const id = String(session.profile_id || "").trim();
        if (id && !profileMap.has(id)) {
            profileMap.set(id, {
                profile_id: id,
                profile_name: "Profile " + id,
                status: session.status || "UNKNOWN",
                target_platform: session.platform || "Unknown",
                last_ip: session.final_ip || session.starting_ip || "Unknown"
            });
        }
    });

    const rows = Array.from(profileMap.values()).map(profile => {
        return calculateProfileReliability(profile, events, sessions);
    });

    return rows;
}

function filterProfileReliabilityRows(rows) {
    const filter = String(window.__ghostReliabilityFilter || "all").toLowerCase();

    if (filter === "all") return rows;

    if (filter === "errors") {
        return rows.filter(row => Number(row.error_count || 0) > 0 || row.main_issue !== "healthy");
    }

    return rows.filter(row => String(row.grade_key || "").toLowerCase() === filter);
}

function sortProfileReliabilityRows(rows) {
    const sort = String(window.__ghostReliabilitySort || "score").toLowerCase();

    const copy = rows.slice();

    if (sort === "errors") {
        copy.sort((a, b) => {
            const diff = Number(b.error_count || 0) - Number(a.error_count || 0);
            if (diff !== 0) return diff;
            return Number(a.score || 0) - Number(b.score || 0);
        });
        return copy;
    }

    if (sort === "recent") {
        copy.sort((a, b) => {
            const diff = Date.parse(b.last_event || "") - Date.parse(a.last_event || "");
            if (!Number.isNaN(diff) && diff !== 0) return diff;
            return Number(a.profile_id || 0) - Number(b.profile_id || 0);
        });
        return copy;
    }

    copy.sort((a, b) => {
        const diff = Number(a.score || 0) - Number(b.score || 0);
        if (diff !== 0) return diff;
        return Number(b.error_count || 0) - Number(a.error_count || 0);
    });

    return copy;
}

function setProfileReliabilityFilter(value) {
    window.__ghostReliabilityFilter = String(value || "all").toLowerCase();
    renderProfileReliabilityFromCache();
}

function setProfileReliabilitySort(value) {
    window.__ghostReliabilitySort = String(value || "score").toLowerCase();
    renderProfileReliabilityFromCache();
}

function renderProfileReliabilityFromCache() {
    if (window.__ghostLatestAnalyticsData) {
        renderProfileReliability(window.__ghostLatestAnalyticsData);
    }
}

// ==============================
// AUTOMATIC PROFILE QUARANTINE
// ==============================

function applyAutoQuarantineNow() {
    if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.apply_auto_quarantine !== "function") {
        alert("Quarantine API is not ready. Restart the dashboard after installing the backend patch.");
        return;
    }

    window.pywebview.api.apply_auto_quarantine().then(res => {
        if (res && res.ok) {
            alert(`Auto-quarantine scan complete. Newly quarantined: ${res.count || 0}`);
        } else {
            alert((res && res.error) || "Auto-quarantine scan failed.");
        }

        refreshAnalytics();
    }).catch(err => {
        alert("Auto-quarantine scan failed: " + err);
    });
}

function quarantineProfileFromReliability(profileId, score, reason) {
    profileId = parseInt(profileId);

    if (!profileId || Number.isNaN(profileId)) {
        alert("Invalid profile ID.");
        return;
    }

    reason = String(reason || "Manual quarantine from Profile Reliability panel").trim();
    score = parseInt(score || 0);

    if (!confirm(`Quarantine Profile ${profileId}?\n\nReason: ${reason}`)) {
        return;
    }

    if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.quarantine_profile !== "function") {
        alert("Quarantine API is not ready. Restart the dashboard after installing the backend patch.");
        return;
    }

    window.pywebview.api.quarantine_profile(profileId, reason, score).then(res => {
        if (!res || !res.ok) {
            alert((res && res.error) || "Could not quarantine profile.");
        }

        refreshAnalytics();
        if (typeof refreshProfiles === "function") {
            refreshProfiles();
        }
    }).catch(err => {
        alert("Could not quarantine profile: " + err);
    });
}

function unquarantineProfileFromReliability(profileId) {
    profileId = parseInt(profileId);

    if (!profileId || Number.isNaN(profileId)) {
        alert("Invalid profile ID.");
        return;
    }

    if (!confirm(`Remove Profile ${profileId} from quarantine?`)) {
        return;
    }

    if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.unquarantine_profile !== "function") {
        alert("Unquarantine API is not ready. Restart the dashboard after installing the backend patch.");
        return;
    }

    window.pywebview.api.unquarantine_profile(profileId, "Manual review passed").then(res => {
        if (!res || !res.ok) {
            alert((res && res.error) || "Could not unquarantine profile.");
        }

        refreshAnalytics();
        if (typeof refreshProfiles === "function") {
            refreshProfiles();
        }
    }).catch(err => {
        alert("Could not unquarantine profile: " + err);
    });
}

function renderProfileReliability(data) {
    const body = document.getElementById("profile-reliability-body");
    const summary = document.getElementById("profile-reliability-summary");
    const filterSelect = document.getElementById("profile-reliability-filter");

    if (!body) return;

    if (filterSelect) {
        filterSelect.value = window.__ghostReliabilityFilter || "all";
    }

    let allRows = [];

    try {
        allRows = getProfileReliabilityRows(data);
    } catch (e) {
        console.error("[Profile Reliability] Could not calculate rows:", e);
        body.innerHTML = `<tr><td colspan="12">Profile reliability failed: ${safeText(e.message || e)}</td></tr>`;
        if (summary) summary.innerText = "Reliability calculation failed.";
        return;
    }

    if (!allRows.length) {
        body.innerHTML = `<tr><td colspan="12">No profile reliability data yet.</td></tr>`;
        if (summary) summary.innerText = "No profiles or events found.";
        return;
    }

    const reliableCount = allRows.filter(r => r.grade_key === "reliable").length;
    const watchCount = allRows.filter(r => r.grade_key === "watch").length;
    const weakCount = allRows.filter(r => r.grade_key === "weak").length;
    const badCount = allRows.filter(r => r.grade_key === "bad").length;
    const quarantinedCount = allRows.filter(r => r.quarantined).length;
    const avgScore = Math.round(
        allRows.reduce((sum, row) => sum + Number(row.score || 0), 0) / Math.max(1, allRows.length)
    );

    if (summary) {
        summary.innerText =
            `Profiles: ${allRows.length} | Avg Score: ${avgScore}/100 | ` +
            `Reliable: ${reliableCount} | Watch: ${watchCount} | Weak: ${weakCount} | Bad: ${badCount} | ` +
            `Quarantined: ${quarantinedCount}`;
    }

    const filtered = sortProfileReliabilityRows(filterProfileReliabilityRows(allRows));

    if (!filtered.length) {
        body.innerHTML = `<tr><td colspan="12">No profiles match this reliability filter.</td></tr>`;
        return;
    }

    body.innerHTML = "";

    filtered.forEach(row => {
        const tr = document.createElement("tr");
        tr.className = "profile-reliability-row";
        tr.style.cursor = row.last_session_id && typeof openSessionDetailsDrawer === "function" ? "pointer" : "default";
        tr.title = row.last_session_id && typeof openSessionDetailsDrawer === "function"
            ? "Click to open latest Session Details"
            : "No session details available";

        if (row.last_session_id && typeof openSessionDetailsDrawer === "function") {
            tr.addEventListener("click", function () {
                openSessionDetailsDrawer(row.last_session_id || "", row.profile_id || "");
            });
        }

        const profileIdNumber = Number(row.profile_id || 0);
        const scoreNumber = Number(row.score || 0);
        const reasonForJs = JSON.stringify(String(reliabilityIssueLabel(row.main_issue) || "Manual quarantine"));

        const actionHtml = row.quarantined
            ? `<button class="btn btn-secondary quarantine-action-btn quarantine-unlock-btn"
                       onclick="event.stopPropagation(); unquarantineProfileFromReliability(${profileIdNumber});">
                   UNQUARANTINE
               </button>`
            : `<button class="btn btn-secondary quarantine-action-btn quarantine-lock-btn"
                       onclick='event.stopPropagation(); quarantineProfileFromReliability(${profileIdNumber}, ${scoreNumber}, ${reasonForJs});'>
                   QUARANTINE
               </button>`;

        tr.innerHTML = `
            <td>${safeText(row.profile_name)}</td>
            <td>
                <div class="reliability-score-cell">
                    <strong class="${row.grade_class}">${safeText(row.score)}/100</strong>
                    <div class="reliability-score-bar">
                        <div class="reliability-score-fill ${row.grade_class}" style="width: ${safeText(row.score)}%;"></div>
                    </div>
                </div>
            </td>
            <td><span class="reliability-grade ${row.grade_class}">${safeText(row.grade_label)}</span></td>
            <td><span style="${statusSoftStyle(row.status)}">${safeText(row.status)}</span></td>
            <td>${safeText(row.last_platform || "None")}</td>
            <td>${safeText(row.last_ip || "Unknown")}</td>
            <td>${safeText(row.session_count || 0)}</td>
            <td>${safeText(row.event_count || 0)}</td>
            <td><span class="${row.error_count > 0 ? "reliability-bad" : "reliability-good"}">${safeText(row.error_count || 0)}</span></td>
            <td>${safeText(reliabilityIssueLabel(row.main_issue))}</td>
            <td>${safeText(row.last_event || "-")}</td>
            <td>${actionHtml}</td>
        `;

        body.appendChild(tr);
    });
}

// ==============================
// SESSION DETAILS DRAWER
// ==============================

function normalizeSessionId(value) {
    const raw = String(value || "").trim();
    return raw || "__NO_SESSION__";
}

function displaySessionId(value) {
    const raw = String(value || "").trim();
    if (!raw || raw === "__NO_SESSION__") return "No Session ID";
    return raw;
}

function sessionEventTimeValue(row) {
    const raw = row && row.event_ts ? Date.parse(row.event_ts) : NaN;
    if (!Number.isNaN(raw)) return raw;

    const idVal = Number(row && row.id ? row.id : 0);
    return Number.isFinite(idVal) ? idVal : 0;
}

function formatDuration(seconds) {
    const total = Number(seconds || 0);

    if (!Number.isFinite(total) || total <= 0) {
        return "0s";
    }

    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = Math.floor(total % 60);

    if (h > 0) return `${h}h ${m}m ${s}s`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
}

function rawDetailsText(value) {
    const raw = String(value || "").trim();

    if (!raw) return "";

    try {
        const parsed = JSON.parse(raw);

        if (parsed && typeof parsed === "object") {
            const parts = [];

            if (parsed.message) parts.push(parsed.message);
            if (parsed.details && typeof parsed.details === "string") parts.push(parsed.details);
            if (parsed.reason) parts.push("reason=" + parsed.reason);
            if (parsed.error) parts.push("error=" + parsed.error);
            if (parsed.selected_platform) parts.push("selected=" + parsed.selected_platform);
            if (parsed.active_platforms) parts.push("active=" + parsed.active_platforms);

            if (parsed.browser && parsed.browser.url) {
                parts.push("url=" + parsed.browser.url);
            }

            if (parts.length) {
                return parts.join(" | ");
            }

            return JSON.stringify(parsed);
        }
    } catch (e) {
        // Keep raw value.
    }

    return raw;
}

function isErrorEvent(row) {
    const e = String(row.event_type || "").toUpperCase();
    const s = String(row.ip_status || "").toUpperCase();

    return (
        e.includes("ERROR") ||
        e.includes("FAILED") ||
        e.includes("BLOCKED") ||
        e.includes("BLACKLISTED") ||
        s.includes("FAILED") ||
        s.includes("BLOCKED") ||
        s.includes("BLACKLISTED") ||
        s.includes("HOME")
    );
}

function isIpEvent(row) {
    const e = String(row.event_type || "").toUpperCase();
    const s = String(row.ip_status || "").toUpperCase();

    return (
        e.includes("IP") ||
        s === "OK" ||
        s === "FAILED" ||
        s === "HOME_IP" ||
        s === "BLACKLISTED"
    );
}

function isPlatformEvent(row) {
    const e = String(row.event_type || "").toUpperCase();

    return (
        e.includes("PLATFORM") ||
        e.includes("TARGET") ||
        e.includes("PAGE") ||
        e.includes("YOUTUBE") ||
        e.includes("TWITCH") ||
        e.includes("SPOTIFY") ||
        e.includes("DEEZER")
    );
}

function drawerEventClass(row) {
    if (isErrorEvent(row)) return "drawer-event-bad";
    if (String(row.event_type || "").toUpperCase().includes("VERIFIED")) return "drawer-event-good";
    if (String(row.event_type || "").toUpperCase().includes("START")) return "drawer-event-warn";
    return "drawer-event-neutral";
}

function getSessionEvents(data, sessionId, profileId) {
    const rows = Array.isArray(data && data.events) ? data.events : [];
    const wantedSession = normalizeSessionId(sessionId);
    const wantedProfile = String(profileId || "").trim();

    return rows
        .filter(row => {
            const rowSession = normalizeSessionId(row.session_id);
            const rowProfile = String(row.profile_id || "").trim();

            if (wantedSession !== "__NO_SESSION__") {
                return rowSession === wantedSession;
            }

            if (wantedProfile) {
                return rowProfile === wantedProfile;
            }

            return false;
        })
        .sort((a, b) => {
            const diff = sessionEventTimeValue(a) - sessionEventTimeValue(b);
            if (diff !== 0) return diff;
            return Number(a.id || 0) - Number(b.id || 0);
        });
}

function findSessionSummary(data, sessionId, profileId) {
    const sessions = Array.isArray(data && data.sessions) ? data.sessions : [];
    const wantedSession = String(sessionId || "").trim();
    const wantedProfile = String(profileId || "").trim();

    if (wantedSession) {
        const exact = sessions.find(s => String(s.session_id || "").trim() === wantedSession);
        if (exact) return exact;
    }

    if (wantedProfile) {
        return sessions.find(s => String(s.profile_id || "").trim() === wantedProfile) || null;
    }

    return null;
}

function inferSessionSummaryFromEvents(events, sessionId, profileId) {
    const first = events[0] || {};
    const last = events[events.length - 1] || first || {};

    return {
        session_id: sessionId || first.session_id || "",
        pc_id: first.pc_id || last.pc_id || "",
        profile_id: profileId || first.profile_id || last.profile_id || "",
        platform: last.platform || first.platform || "Unknown",
        started_at: first.event_ts || "",
        ended_at: last.event_ts || "",
        duration_seconds: 0,
        starting_ip: first.ip_label || first.ip_address || "",
        final_ip: last.ip_label || last.ip_address || "",
        ip_status: last.ip_status || first.ip_status || "UNKNOWN",
        status: last.ip_status || "UNKNOWN",
        close_reason: rawDetailsText(last.details || ""),
        event_count: events.length,
        error_count: events.filter(isErrorEvent).length,
        last_event: last.event_ts || ""
    };
}

function sessionStatusClass(status) {
    const s = String(status || "").toUpperCase();

    if (s.includes("BLACKLISTED") || s.includes("BLOCKED") || s.includes("FAILED") || s.includes("ERROR")) {
        return "session-status-bad";
    }

    if (s.includes("RUNNING") || s.includes("OK")) {
        return "session-status-good";
    }

    if (s.includes("STOP") || s.includes("ENDING")) {
        return "session-status-warn";
    }

    return "session-status-neutral";
}

function filterDrawerEventRows(rows) {
    const filter = String(window.__ghostSessionDrawerFilter || "all").toLowerCase();

    if (filter === "errors") {
        return rows.filter(isErrorEvent);
    }

    if (filter === "ip") {
        return rows.filter(isIpEvent);
    }

    if (filter === "platform") {
        return rows.filter(isPlatformEvent);
    }

    return rows;
}

function filterDrawerEvents(filterName) {
    window.__ghostSessionDrawerFilter = String(filterName || "all").toLowerCase();

    if (window.__ghostSelectedSessionId || window.__ghostSelectedSessionProfileId) {
        openSessionDetailsDrawer(
            window.__ghostSelectedSessionId,
            window.__ghostSelectedSessionProfileId,
            false
        );
    }
}

function openSessionDetailsDrawer(sessionId, profileId, forceAllFilter = true) {
    const data = window.__ghostLatestAnalyticsData || {};

    if (forceAllFilter) {
        window.__ghostSessionDrawerFilter = "all";
    }

    window.__ghostSelectedSessionId = String(sessionId || "").trim();
    window.__ghostSelectedSessionProfileId = String(profileId || "").trim();

    const events = getSessionEvents(
        data,
        window.__ghostSelectedSessionId,
        window.__ghostSelectedSessionProfileId
    );

    const summaryFromDb = findSessionSummary(
        data,
        window.__ghostSelectedSessionId,
        window.__ghostSelectedSessionProfileId
    );

    const summary = summaryFromDb || inferSessionSummaryFromEvents(
        events,
        window.__ghostSelectedSessionId,
        window.__ghostSelectedSessionProfileId
    );

    renderSessionDetailsDrawer(summary, events);

    const drawer = document.getElementById("session-details-drawer");
    const backdrop = document.getElementById("session-details-backdrop");

    if (drawer) drawer.classList.add("open");
    if (backdrop) backdrop.classList.add("open");
}

function closeSessionDetailsDrawer() {
    const drawer = document.getElementById("session-details-drawer");
    const backdrop = document.getElementById("session-details-backdrop");

    if (drawer) drawer.classList.remove("open");
    if (backdrop) backdrop.classList.remove("open");
}

function renderSessionDetailsDrawer(summary, events) {
    const title = document.getElementById("session-details-title");
    const summaryBox = document.getElementById("session-details-summary");
    const countBox = document.getElementById("session-details-event-count");
    const eventBox = document.getElementById("session-details-events");

    if (!summaryBox || !eventBox) return;

    const sessionId = summary && summary.session_id ? summary.session_id : window.__ghostSelectedSessionId;
    const profileId = summary && summary.profile_id ? summary.profile_id : window.__ghostSelectedSessionProfileId;
    const status = summary && summary.status ? summary.status : "UNKNOWN";
    const statusClass = sessionStatusClass(status);

    if (title) {
        title.innerHTML = `Profile ${safeText(profileId || "-")} <span>${safeText(displaySessionId(sessionId))}</span>`;
    }

    const eventCount = events.length;
    const errorCount = events.filter(isErrorEvent).length;

    summaryBox.innerHTML = `
        <div class="session-details-grid">
            <div class="session-detail-card">
                <span>Profile</span>
                <strong>${safeText(profileId || "-")}</strong>
            </div>
            <div class="session-detail-card">
                <span>Status</span>
                <strong class="${statusClass}">${safeText(status || "UNKNOWN")}</strong>
            </div>
            <div class="session-detail-card">
                <span>PC</span>
                <strong>${safeText(summary.pc_id || "-")}</strong>
            </div>
            <div class="session-detail-card">
                <span>Platform</span>
                <strong>${safeText(summary.platform || "Unknown")}</strong>
            </div>
            <div class="session-detail-card wide">
                <span>Session ID</span>
                <strong>${safeText(displaySessionId(sessionId))}</strong>
            </div>
            <div class="session-detail-card">
                <span>Started</span>
                <strong>${safeText(summary.started_at || "-")}</strong>
            </div>
            <div class="session-detail-card">
                <span>Ended</span>
                <strong>${safeText(summary.ended_at || "-")}</strong>
            </div>
            <div class="session-detail-card">
                <span>Duration</span>
                <strong>${safeText(formatDuration(summary.duration_seconds || 0))}</strong>
            </div>
            <div class="session-detail-card">
                <span>Events</span>
                <strong>${safeText(summary.event_count || eventCount || 0)}</strong>
            </div>
            <div class="session-detail-card">
                <span>Errors</span>
                <strong class="${errorCount > 0 ? "session-status-bad" : "session-status-good"}">${safeText(summary.error_count || errorCount || 0)}</strong>
            </div>
            <div class="session-detail-card wide">
                <span>Starting IP</span>
                <strong>${safeText(summary.starting_ip || "-")}</strong>
            </div>
            <div class="session-detail-card wide">
                <span>Final IP</span>
                <strong>${safeText(summary.final_ip || "-")}</strong>
            </div>
            <div class="session-detail-card wide">
                <span>Close Reason</span>
                <strong>${safeText(summary.close_reason || "-")}</strong>
            </div>
        </div>
    `;

    const filteredEvents = filterDrawerEventRows(events);

    if (countBox) {
        countBox.innerText = `${filteredEvents.length} shown / ${eventCount} total | filter: ${String(window.__ghostSessionDrawerFilter || "all").toUpperCase()}`;
    }

    eventBox.innerHTML = "";

    if (!filteredEvents.length) {
        eventBox.innerHTML = `<div class="session-details-empty">No events match this filter.</div>`;
        return;
    }

    filteredEvents.forEach((row, index) => {
        const item = document.createElement("div");
        item.className = `drawer-event ${drawerEventClass(row)}`;

        item.innerHTML = `
            <div class="drawer-event-dot"></div>
            <div class="drawer-event-body">
                <div class="drawer-event-top">
                    <span class="drawer-event-index">#${index + 1}</span>
                    <span>${safeText(row.event_ts || "")}</span>
                    <strong>${safeText(row.event_type || "EVENT")}</strong>
                    <em>${safeText(row.platform || "Unknown")}</em>
                    <span style="${statusSoftStyle(row.ip_status)}">${safeText(row.ip_status || "UNKNOWN")}</span>
                </div>
                <div class="drawer-event-mid">
                    <span>PC: ${safeText(row.pc_id || "-")}</span>
                    <span>IP: ${safeText(row.ip_label || row.ip_address || "-")}</span>
                </div>
                <div class="drawer-event-details">${safeText(rawDetailsText(row.details || ""))}</div>
            </div>
        `;

        eventBox.appendChild(item);
    });
}

function copySelectedSessionDetails() {
    const data = window.__ghostLatestAnalyticsData || {};
    const events = getSessionEvents(
        data,
        window.__ghostSelectedSessionId,
        window.__ghostSelectedSessionProfileId
    );

    const summary = findSessionSummary(
        data,
        window.__ghostSelectedSessionId,
        window.__ghostSelectedSessionProfileId
    ) || inferSessionSummaryFromEvents(
        events,
        window.__ghostSelectedSessionId,
        window.__ghostSelectedSessionProfileId
    );

    const lines = [];

    lines.push("SESSION DETAILS");
    lines.push("================");
    lines.push(`Profile: ${summary.profile_id || ""}`);
    lines.push(`Session ID: ${summary.session_id || ""}`);
    lines.push(`PC: ${summary.pc_id || ""}`);
    lines.push(`Platform: ${summary.platform || ""}`);
    lines.push(`Status: ${summary.status || ""}`);
    lines.push(`Started: ${summary.started_at || ""}`);
    lines.push(`Ended: ${summary.ended_at || ""}`);
    lines.push(`Duration: ${formatDuration(summary.duration_seconds || 0)}`);
    lines.push(`Starting IP: ${summary.starting_ip || ""}`);
    lines.push(`Final IP: ${summary.final_ip || ""}`);
    lines.push(`Close Reason: ${summary.close_reason || ""}`);
    lines.push("");
    lines.push("EVENTS");
    lines.push("================");

    events.forEach((row, index) => {
        lines.push(
            `${index + 1}. ${row.event_ts || ""} | ${row.event_type || ""} | ${row.platform || ""} | ${row.ip_status || ""} | ${rawDetailsText(row.details || "")}`
        );
    });

    const text = lines.join("\n");

    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(() => {
            console.log("[Session Details] Copied to clipboard.");
        }).catch(() => {
            console.log(text);
            alert("Clipboard blocked. Details printed to console.");
        });
    } else {
        console.log(text);
        alert("Clipboard unavailable. Details printed to console.");
    }
}

function statusSoftStyle(status) {
    const s = String(status || "").toUpperCase();
    if (s.includes("HOME")) return "color:#e6cf3a;font-weight:800;";
    if (s.includes("DUPLICATE") || s.includes("BAD") || s.includes("BLOCKED") || s.includes("FAIL")) {
        return "color:#d85a5a;font-weight:800;";
    }
    if (s === "OK") return "color:#38d98a;font-weight:800;";
    return "color:#aeb7c9;font-weight:700;";
}

function platformFlags(row, prefix) {
    const platforms = [];
    ["youtube", "twitch", "spotify", "deezer"].forEach(p => {
        if (Number(row[`${prefix}_${p}`] || 0) === 1) {
            platforms.push(p);
        }
    });
    return platforms.length ? platforms.join(", ") : "-";
}

function addIpFromReputation(ip) {
    const input = document.getElementById("blacklist-ip-input");
    const reasonInput = document.getElementById("blacklist-reason-input");
    if (input) input.value = ip;
    if (reasonInput && !reasonInput.value.trim()) {
        reasonInput.value = "Manually blacklisted from IP Reputation table";
    }
    addBlacklistedIp();
}

function addBlacklistedIp() {
    const input = document.getElementById("blacklist-ip-input");
    const reasonInput = document.getElementById("blacklist-reason-input");
    const statusEl = document.getElementById("blacklist-action-status");

    const ip = input ? input.value.trim() : "";
    const reason = reasonInput ? reasonInput.value.trim() : "Manual blacklist from dashboard";

    if (!ip) {
        alert("Enter an IP address to blacklist.");
        return;
    }

    if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.add_blacklisted_ip !== "function") {
        alert("Blacklist API is not ready. Restart the dashboard after installing the patch.");
        return;
    }

    if (statusEl) statusEl.innerText = "Adding blacklist entry...";

    window.pywebview.api.add_blacklisted_ip(ip, reason).then(res => {
        if (res && res.ok) {
            if (statusEl) statusEl.innerText = `Blacklisted: ${res.ip}`;
            if (input) input.value = "";
            if (reasonInput) reasonInput.value = "";
            refreshAnalytics();
        } else {
            if (statusEl) statusEl.innerText = `Failed: ${(res && res.error) || "Unknown error"}`;
            alert((res && res.error) || "Could not blacklist IP.");
        }
    });
}

function removeBlacklistedIp(ip) {
    ip = String(ip || "").trim();
    if (!ip) return;

    if (!confirm(`Remove ${ip} from the IP blacklist?`)) {
        return;
    }

    if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.remove_blacklisted_ip !== "function") {
        alert("Blacklist API is not ready. Restart the dashboard after installing the patch.");
        return;
    }

    window.pywebview.api.remove_blacklisted_ip(ip).then(res => {
        if (!res || !res.ok) {
            alert((res && res.error) || "Could not remove IP from blacklist.");
        }
        refreshAnalytics();
    });
}


// --- ANALYTICS TABLE PAGINATION ---
const ANALYTICS_TABLE_PAGE_SIZE = 25;
window.__ghostAnalyticsProfilePage = window.__ghostAnalyticsProfilePage || 1;
window.__ghostAnalyticsEventPage = window.__ghostAnalyticsEventPage || 1;
window.__ghostLatestAnalyticsData = window.__ghostLatestAnalyticsData || null;

// Profile Reliability Score state
window.__ghostReliabilityFilter = window.__ghostReliabilityFilter || "all";
window.__ghostReliabilitySort = window.__ghostReliabilitySort || "score";

// Session Details Drawer state
window.__ghostSelectedSessionId = window.__ghostSelectedSessionId || "";
window.__ghostSelectedSessionProfileId = window.__ghostSelectedSessionProfileId || "";
window.__ghostSessionDrawerFilter = window.__ghostSessionDrawerFilter || "all";

// Session Timeline filters
window.__ghostTimelineProfileFilter = window.__ghostTimelineProfileFilter || "";
window.__ghostTimelineSessionFilter = window.__ghostTimelineSessionFilter || "";

function clampAnalyticsPage(page, totalRows) {
    const totalPages = Math.max(1, Math.ceil((parseInt(totalRows) || 0) / ANALYTICS_TABLE_PAGE_SIZE));
    let cleanPage = parseInt(page);
    if (Number.isNaN(cleanPage)) cleanPage = 1;
    return Math.max(1, Math.min(totalPages, cleanPage));
}

function getAnalyticsPageRows(rows, page) {
    if (!Array.isArray(rows)) rows = [];

    const totalRows = rows.length;
    const totalPages = Math.max(1, Math.ceil(totalRows / ANALYTICS_TABLE_PAGE_SIZE));
    const currentPage = clampAnalyticsPage(page, totalRows);
    const startIndex = totalRows === 0 ? 0 : (currentPage - 1) * ANALYTICS_TABLE_PAGE_SIZE;
    const endIndex = Math.min(startIndex + ANALYTICS_TABLE_PAGE_SIZE, totalRows);

    return {
        totalRows,
        totalPages,
        currentPage,
        startIndex,
        endIndex,
        startNumber: totalRows === 0 ? 0 : startIndex + 1,
        endNumber: endIndex,
        pageRows: rows.slice(startIndex, endIndex)
    };
}

function ensureAnalyticsPaginationControls(kind, tbodyId) {
    const controlId = `analytics-${kind}-pagination-controls`;
    let controls = document.getElementById(controlId);
    if (controls) return controls;

    const table = document.getElementById(tbodyId)?.closest('table');
    if (!table) return null;

    controls = document.createElement('div');
    controls.id = controlId;
    controls.className = 'profile-pagination-controls analytics-pagination-controls';
    table.insertAdjacentElement('afterend', controls);
    return controls;
}

function renderAnalyticsPaginationControls(kind, tbodyId, pageInfo) {
    const controls = ensureAnalyticsPaginationControls(kind, tbodyId);
    if (!controls) return;

    const disabledPrev = pageInfo.currentPage <= 1 ? 'disabled' : '';
    const disabledNext = pageInfo.currentPage >= pageInfo.totalPages ? 'disabled' : '';
    const label = kind === 'profile' ? 'Profile Performance' : 'Recent Events';

    controls.innerHTML = `
        <div class="profile-pagination-left">
            <span class="profile-pagination-summary">
                ${label}: showing <strong>${pageInfo.startNumber}</strong>-<strong>${pageInfo.endNumber}</strong> of <strong>${pageInfo.totalRows}</strong>
            </span>
            <span class="profile-pagination-selected">
                Limit: <strong>${ANALYTICS_TABLE_PAGE_SIZE}</strong> lines/page
            </span>
        </div>

        <div class="profile-pagination-right">
            <button class="btn btn-secondary pagination-btn" onclick="setAnalyticsPage('${kind}', 1)" ${disabledPrev}>FIRST</button>
            <button class="btn btn-secondary pagination-btn" onclick="setAnalyticsPage('${kind}', ${pageInfo.currentPage - 1})" ${disabledPrev}>PREV</button>
            <span class="profile-pagination-page-label">Page</span>
            <input
                id="analytics-${kind}-page-input"
                class="profile-page-input"
                type="number"
                min="1"
                max="${pageInfo.totalPages}"
                value="${pageInfo.currentPage}"
                onkeydown="if(event.key === 'Enter') goToAnalyticsPageFromInput('${kind}');"
            >
            <span class="profile-pagination-page-label">/ ${pageInfo.totalPages}</span>
            <button class="btn btn-secondary pagination-btn" onclick="goToAnalyticsPageFromInput('${kind}')">GO</button>
            <button class="btn btn-secondary pagination-btn" onclick="setAnalyticsPage('${kind}', ${pageInfo.currentPage + 1})" ${disabledNext}>NEXT</button>
            <button class="btn btn-secondary pagination-btn" onclick="setAnalyticsPage('${kind}', ${pageInfo.totalPages})" ${disabledNext}>LAST</button>
        </div>
    `;
}

function setAnalyticsPage(kind, page) {
    if (kind === 'profile') {
        window.__ghostAnalyticsProfilePage = page;
    } else if (kind === 'event') {
        window.__ghostAnalyticsEventPage = page;
    }

    if (window.__ghostLatestAnalyticsData) {
        renderAnalytics(window.__ghostLatestAnalyticsData);
    }
}

// ==============================
// SESSION TIMELINE PANEL
// ==============================

function setTimelineProfileFilter(profileId) {
    window.__ghostTimelineProfileFilter = String(profileId || "");
    window.__ghostTimelineSessionFilter = "";

    if (window.__ghostLatestAnalyticsData) {
        renderAnalytics(window.__ghostLatestAnalyticsData);
    }
}

function setTimelineSessionFilter(sessionId) {
    window.__ghostTimelineSessionFilter = String(sessionId || "");

    if (window.__ghostLatestAnalyticsData) {
        renderAnalytics(window.__ghostLatestAnalyticsData);
    }
}

function clearTimelineFilters() {
    window.__ghostTimelineProfileFilter = "";
    window.__ghostTimelineSessionFilter = "";

    if (window.__ghostLatestAnalyticsData) {
        renderAnalytics(window.__ghostLatestAnalyticsData);
    }
}

function timelineEventRank(eventType) {
    const e = String(eventType || "").toUpperCase();

    if (e.includes("ERROR") || e.includes("FAILED") || e.includes("BLOCKED") || e.includes("BLACKLISTED")) return 1;
    if (e.includes("IP_VERIFIED") || e.includes("SELENIUM_ATTACHED") || e.includes("BROWSER_LAUNCHED")) return 2;
    if (e.includes("PLATFORM") || e.includes("TARGET") || e.includes("PAGE")) return 3;
    if (e.includes("SESSION_ENDED") || e.includes("STOP")) return 4;

    return 5;
}

function timelineEventStyle(eventType, ipStatus) {
    const e = String(eventType || "").toUpperCase();
    const s = String(ipStatus || "").toUpperCase();

    if (
        e.includes("ERROR") ||
        e.includes("FAILED") ||
        e.includes("BLOCKED") ||
        e.includes("BLACKLISTED") ||
        s.includes("FAILED") ||
        s.includes("BLOCKED") ||
        s.includes("BLACKLISTED") ||
        s.includes("HOME")
    ) {
        return "timeline-bad";
    }

    if (
        e.includes("IP_VERIFIED") ||
        e.includes("SELENIUM_ATTACHED") ||
        e.includes("BROWSER_LAUNCHED") ||
        e.includes("PAGE_LOADED")
    ) {
        return "timeline-good";
    }

    if (
        e.includes("START") ||
        e.includes("CHECKING") ||
        e.includes("SELECTED") ||
        e.includes("RUNNER")
    ) {
        return "timeline-warn";
    }

    return "timeline-neutral";
}

function normalizeTimelineSessionId(value) {
    const raw = String(value || "").trim();
    return raw ? raw : "__NO_SESSION__";
}

function displayTimelineSessionId(value) {
    const raw = String(value || "").trim();
    if (!raw || raw === "__NO_SESSION__") return "No Session ID";
    return raw;
}

function eventTimeValue(row) {
    const raw = row && row.event_ts ? Date.parse(row.event_ts) : NaN;
    if (!Number.isNaN(raw)) return raw;

    const idVal = Number(row && row.id ? row.id : 0);
    return Number.isFinite(idVal) ? idVal : 0;
}

function compactDetails(value) {
    const raw = String(value || "").trim();

    if (!raw) return "";

    try {
        const parsed = JSON.parse(raw);

        if (parsed && typeof parsed === "object") {
            const parts = [];

            if (parsed.message) parts.push(parsed.message);
            if (parsed.details && typeof parsed.details === "string") parts.push(parsed.details);
            if (parsed.reason) parts.push("reason=" + parsed.reason);
            if (parsed.error) parts.push("error=" + parsed.error);

            if (parsed.browser && parsed.browser.url) {
                parts.push("url=" + parsed.browser.url);
            }

            if (parsed.selected_platform) {
                parts.push("selected=" + parsed.selected_platform);
            }

            if (parsed.active_platforms) {
                parts.push("active=" + parsed.active_platforms);
            }

            if (parts.length) {
                return parts.join(" | ");
            }
        }
    } catch (e) {
        // Not JSON. Keep raw string.
    }

    return raw.length > 240 ? raw.slice(0, 240) + "..." : raw;
}

function buildLatestByKey(rows, keyGetter) {
    const map = new Map();

    rows.forEach(row => {
        const key = keyGetter(row);
        if (!key) return;

        const current = map.get(key);
        if (!current || eventTimeValue(row) > eventTimeValue(current)) {
            map.set(key, row);
        }
    });

    return map;
}

function renderTimelineSelect(selectId, options, selectedValue, defaultLabel) {
    const select = document.getElementById(selectId);
    if (!select) return;

    select.innerHTML = "";

    const defaultOption = document.createElement("option");
    defaultOption.value = "";
    defaultOption.textContent = defaultLabel;
    select.appendChild(defaultOption);

    options.forEach(item => {
        const option = document.createElement("option");
        option.value = item.value;
        option.textContent = item.label;
        if (String(item.value) === String(selectedValue)) {
            option.selected = true;
        }
        select.appendChild(option);
    });
}

function renderSessionTimeline(data) {
    const body = document.getElementById("session-timeline-body");
    const summary = document.getElementById("timeline-summary");

    if (!body) return;

    const allEvents = Array.isArray(data.events) ? data.events : [];

    if (!allEvents.length) {
        body.innerHTML = `<div class="timeline-empty">No timeline events recorded yet.</div>`;
        if (summary) summary.innerText = "No session selected.";
        renderTimelineSelect("timeline-profile-filter", [], "", "Latest Profile");
        renderTimelineSelect("timeline-session-filter", [], "", "Latest Session");
        return;
    }

    const eventsWithProfile = allEvents.filter(row => String(row.profile_id || "").trim());

    if (!eventsWithProfile.length) {
        body.innerHTML = `<div class="timeline-empty">No profile-linked events yet.</div>`;
        if (summary) summary.innerText = "No profile session selected.";
        renderTimelineSelect("timeline-profile-filter", [], "", "Latest Profile");
        renderTimelineSelect("timeline-session-filter", [], "", "Latest Session");
        return;
    }

    const latestByProfile = buildLatestByKey(eventsWithProfile, row => String(row.profile_id || "").trim());

    const profileOptions = Array.from(latestByProfile.keys())
        .sort((a, b) => eventTimeValue(latestByProfile.get(b)) - eventTimeValue(latestByProfile.get(a)))
        .map(profileId => ({
            value: profileId,
            label: `Profile ${profileId}`
        }));

    let selectedProfile = String(window.__ghostTimelineProfileFilter || "").trim();

    if (!selectedProfile || !latestByProfile.has(selectedProfile)) {
        selectedProfile = profileOptions.length ? profileOptions[0].value : "";
        window.__ghostTimelineProfileFilter = selectedProfile;
    }

    renderTimelineSelect("timeline-profile-filter", profileOptions, selectedProfile, "Latest Profile");

    const profileEvents = eventsWithProfile.filter(row => String(row.profile_id || "").trim() === selectedProfile);

    const latestBySession = buildLatestByKey(
        profileEvents,
        row => normalizeTimelineSessionId(row.session_id)
    );

    const sessionOptions = Array.from(latestBySession.keys())
        .sort((a, b) => eventTimeValue(latestBySession.get(b)) - eventTimeValue(latestBySession.get(a)))
        .map(sessionId => ({
            value: sessionId,
            label: displayTimelineSessionId(sessionId)
        }));

    let selectedSession = String(window.__ghostTimelineSessionFilter || "").trim();

    if (!selectedSession || !latestBySession.has(selectedSession)) {
        selectedSession = sessionOptions.length ? sessionOptions[0].value : "";
        window.__ghostTimelineSessionFilter = selectedSession;
    }

    renderTimelineSelect("timeline-session-filter", sessionOptions, selectedSession, "Latest Session");

    const timelineRows = profileEvents
        .filter(row => normalizeTimelineSessionId(row.session_id) === selectedSession)
        .sort((a, b) => {
            const timeDiff = eventTimeValue(a) - eventTimeValue(b);
            if (timeDiff !== 0) return timeDiff;
            return Number(a.id || 0) - Number(b.id || 0);
        });

    if (!timelineRows.length) {
        body.innerHTML = `<div class="timeline-empty">No events found for selected profile/session.</div>`;
        if (summary) summary.innerText = `Profile ${selectedProfile} | ${displayTimelineSessionId(selectedSession)} | 0 events`;
        return;
    }

    const first = timelineRows[0];
    const last = timelineRows[timelineRows.length - 1];

    if (summary) {
        summary.innerText =
            `Profile ${selectedProfile} | ${displayTimelineSessionId(selectedSession)} | ` +
            `${timelineRows.length} events | ${first.event_ts || "-"} → ${last.event_ts || "-"}`;
    }

    body.innerHTML = "";

    timelineRows.forEach((row, index) => {
        const item = document.createElement("div");
        const styleClass = timelineEventStyle(row.event_type, row.ip_status);
        const rank = timelineEventRank(row.event_type);

        item.className = `timeline-item ${styleClass}`;
        item.dataset.rank = rank;
        item.style.cursor = "pointer";
        item.title = "Click to open Session Details";
        item.addEventListener("click", function () {
            openSessionDetailsDrawer(row.session_id || "", row.profile_id || "");
        });

        item.innerHTML = `
            <div class="timeline-dot"></div>
            <div class="timeline-content">
                <div class="timeline-topline">
                    <span class="timeline-index">#${index + 1}</span>
                    <span class="timeline-time">${safeText(row.event_ts || "")}</span>
                    <span class="timeline-event">${safeText(row.event_type || "EVENT")}</span>
                    <span class="timeline-platform">${safeText(row.platform || "Unknown")}</span>
                    <span class="timeline-ip-status" style="${statusSoftStyle(row.ip_status)}">${safeText(row.ip_status || "UNKNOWN")}</span>
                </div>
                <div class="timeline-meta">
                    <span>PC: ${safeText(row.pc_id || "-")}</span>
                    <span>IP: ${safeText(row.ip_label || row.ip_address || "-")}</span>
                </div>
                <div class="timeline-details">${safeText(compactDetails(row.details || ""))}</div>
            </div>
        `;

        body.appendChild(item);
    });
}

function renderAnalytics(data) {
    if (!data || data.ok === false) {
        console.log("[Ghost Analytics] No analytics data:", data);
        const message = data && data.error ? data.error : "No analytics data returned by backend.";
        const targets = [
            ["analytics-profile-body", 11],
            ["analytics-ip-body", 11],
            ["analytics-platform-body", 10],
            ["profile-reliability-body", 12],
            ["analytics-event-body", 10]
        ];
        targets.forEach(([id, colspan]) => {
            const el = document.getElementById(id);
            if (el) el.innerHTML = `<tr><td colspan="${colspan}">Analytics backend error: ${safeText(message)}</td></tr>`;
        });
        const timelineBody = document.getElementById("session-timeline-body");
        if (timelineBody) timelineBody.innerHTML = `<div class="timeline-empty">Analytics backend error: ${safeText(message)}</div>`;
        return;
    }

    window.__ghostLatestAnalyticsData = data;
    
	if (
        document.getElementById("session-details-drawer") &&
        document.getElementById("session-details-drawer").classList.contains("open") &&
        (window.__ghostSelectedSessionId || window.__ghostSelectedSessionProfileId)
    ) {
        openSessionDetailsDrawer(
            window.__ghostSelectedSessionId,
            window.__ghostSelectedSessionProfileId,
            false
        );
    }
	
    const summary = data.summary || {};

    const activeEl = document.getElementById("analytics-active-profiles");
    const adsEl = document.getElementById("analytics-ad-events");
    const minEl = document.getElementById("analytics-estimated-min");
    const valueEl = document.getElementById("analytics-estimated-value");
    const maxEl = document.getElementById("analytics-estimated-max");
    const badIpEl = document.getElementById("analytics-bad-ips");

    if (activeEl) activeEl.innerText = summary.active_profiles || 0;
    if (adsEl) adsEl.innerText = summary.ads_detected || 0;
    if (minEl) minEl.innerText = formatMoneyCompact(summary.estimated_revenue_min || 0);
    if (valueEl) valueEl.innerText = formatMoneyCompact(summary.estimated_revenue_avg || summary.estimated_revenue || 0);
    if (maxEl) maxEl.innerText = formatMoneyCompact(summary.estimated_revenue_max || 0);
    if (badIpEl) badIpEl.innerText = summary.blacklisted_count || summary.bad_ip_count || 0;

    const modelBody = document.getElementById("analytics-model-body");
    if (modelBody) {
        modelBody.innerHTML = "";
        const rows = data.revenue_models || [];

        if (!rows.length) {
            modelBody.innerHTML = `<tr><td colspan="6">No platform revenue model loaded yet.</td></tr>`;
        } else {
            rows.forEach(row => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td>${safeText(row.display_name || row.platform_key || "")}</td>
                    <td>${safeText(row.metric || "")}</td>
                    <td>${formatMoney(row.payout_min || 0)}</td>
                    <td>${formatMoney(row.payout_avg || 0)}</td>
                    <td>${formatMoney(row.payout_max || 0)}</td>
                    <td>${safeText(row.condition || "")}</td>
                `;
                modelBody.appendChild(tr);
            });
        }
    }

    const profileBody = document.getElementById("analytics-profile-body");
    if (profileBody) {
        profileBody.innerHTML = "";
        const rows = Array.isArray(data.profiles) ? data.profiles : [];
        const pageInfo = getAnalyticsPageRows(rows, window.__ghostAnalyticsProfilePage || 1);
        window.__ghostAnalyticsProfilePage = pageInfo.currentPage;

        if (!rows.length) {
            profileBody.innerHTML = `<tr><td colspan="11">No profile analytics yet.</td></tr>`;
        } else {
            pageInfo.pageRows.forEach(row => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td>${safeText(row.profile_name || ("Profile " + row.profile_id))}</td>
                    <td><span style="${statusSoftStyle(row.status)}">${safeText(row.status)}</span></td>
                    <td>${safeText(row.target_platform || "None")}</td>
                    <td>${safeText(row.last_ip || "Unknown")}</td>
                    <td>${safeText(row.events || 0)}</td>
                    <td>${safeText(row.ads_detected || 0)}</td>
                    <td>${formatMetricCount(row.metric_count || 0)}</td>
                    <td>${formatMoney(row.estimated_min || 0)}</td>
                    <td>${formatMoney(row.estimated_avg || row.estimated_revenue || 0)}</td>
                    <td>${formatMoney(row.estimated_max || 0)}</td>
                    <td>${safeText(row.last_event || "-")}</td>
                `;
                profileBody.appendChild(tr);
            });
        }

        renderAnalyticsPaginationControls('profile', 'analytics-profile-body', pageInfo);
    }

    const ipBody = document.getElementById("analytics-ip-body");
    if (ipBody) {
        ipBody.innerHTML = "";
        const rows = data.ip_reputation || [];

        if (!rows.length) {
            ipBody.innerHTML = `<tr><td colspan="11">No IP reputation data yet. Launch profiles to populate this table.</td></tr>`;
        } else {
            rows.forEach(row => {
                const location = [
                    row.city || "",
                    row.country || "",
                    row.provider || ""
                ].filter(Boolean).join(" | ");

                const isBlacklisted = Number(row.blacklisted || 0) === 1 || String(row.status || "").toUpperCase() === "BLACKLISTED";
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td>${safeText(row.ip_address || "")}</td>
                    <td>${safeText(location || row.ip_label || "")}</td>
                    <td><span style="${statusSoftStyle(row.status)}">${safeText(row.status || "UNKNOWN")}</span></td>
                    <td>${isBlacklisted ? "YES" : "NO"}</td>
                    <td>${safeText(row.blacklist_reason || "-")}</td>
                    <td>${safeText(row.total_ads_detected || 0)}</td>
                    <td>${safeText(row.total_failures || 0)}</td>
                    <td>${formatMoney(row.estimated_revenue_avg || row.estimated_revenue || 0)}</td>
                    <td>${safeText(platformFlags(row, "good_for"))}</td>
                    <td>${safeText(platformFlags(row, "bad_for"))}</td>
                    <td>
                        ${isBlacklisted
                            ? `<button class="btn btn-small btn-secondary" onclick="removeBlacklistedIp('${safeText(row.ip_address || "")}')">UNBLACKLIST</button>`
                            : `<button class="btn btn-small btn-danger" onclick="addIpFromReputation('${safeText(row.ip_address || "")}')">BLACKLIST</button>`
                        }
                    </td>
                `;
                ipBody.appendChild(tr);
            });
        }
    }

    const platformBody = document.getElementById("analytics-platform-body");
    if (platformBody) {
        platformBody.innerHTML = "";
        const rows = Array.isArray(data.platforms) ? data.platforms : [];

        if (!rows.length) {
            platformBody.innerHTML = `<tr><td colspan="10">No platform analytics yet.</td></tr>`;
        } else {
            rows.forEach(row => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td>${safeText(row.platform || "Unknown")}</td>
                    <td>${safeText(row.profiles_used || 0)}</td>
                    <td>${safeText(row.unique_ips || 0)}</td>
                    <td>${safeText(row.total_events || 0)}</td>
                    <td>${safeText(row.ads_detected || 0)}</td>
                    <td>${formatMetricCount(row.metric_count || 0)}</td>
                    <td>${formatMoney(row.estimated_min || 0)}</td>
                    <td>${formatMoney(row.estimated_avg || row.estimated_revenue || 0)}</td>
                    <td>${formatMoney(row.estimated_max || 0)}</td>
                    <td>${safeText(row.last_event || "-")}</td>
                `;
                platformBody.appendChild(tr);
            });
        }
    }

    try {
        if (typeof renderProfileReliability === "function") {
            renderProfileReliability(data);
        }
    } catch (e) {
        console.error("[Ghost Analytics] Profile Reliability render failed:", e);
        const reliabilityBody = document.getElementById("profile-reliability-body");
        if (reliabilityBody) {
            reliabilityBody.innerHTML = `<tr><td colspan="12">Profile Reliability failed: ${safeText(e.message || e)}</td></tr>`;
        }
    }

    try {
        if (typeof renderSessionTimeline === "function") {
            renderSessionTimeline(data);
        }
    } catch (e) {
        console.error("[Ghost Analytics] Session Timeline render failed:", e);
        const timelineBody = document.getElementById("session-timeline-body");
        if (timelineBody) {
            timelineBody.innerHTML = `<div class="timeline-empty">Session Timeline failed: ${safeText(e.message || e)}</div>`;
        }
    }

    const eventBody = document.getElementById("analytics-event-body");
    if (eventBody) {
        eventBody.innerHTML = "";
        const rows = Array.isArray(data.events) ? data.events : [];
        const pageInfo = getAnalyticsPageRows(rows, window.__ghostAnalyticsEventPage || 1);
        window.__ghostAnalyticsEventPage = pageInfo.currentPage;

        if (!rows.length) {
            eventBody.innerHTML = `<tr><td colspan="10">No analytics events yet.</td></tr>`;
        } else {
            pageInfo.pageRows.forEach(row => {
                const tr = document.createElement("tr");

                tr.style.cursor = "pointer";
                tr.title = "Click to open Session Details";

                tr.addEventListener("click", function () {
                    openSessionDetailsDrawer(row.session_id || "", row.profile_id || "");
                });

                tr.innerHTML = `
                    <td>${safeText(row.event_ts || "")}</td>
                    <td>${safeText(row.pc_id || "")}</td>
                    <td>${safeText(row.profile_id || "")}</td>
                    <td>${safeText(row.platform || "")}</td>
                    <td>${safeText(row.ip_label || row.ip_address || "")}</td>
                    <td><span style="${statusSoftStyle(row.ip_status)}">${safeText(row.ip_status || "UNKNOWN")}</span></td>
                    <td>${safeText(row.event_type || "")}</td>
                    <td>${formatMetricCount(row.metric_count || 0)}</td>
                    <td>${formatMoney(row.estimated_avg || row.estimated_value || 0)}</td>
                    <td>${safeText(row.details || "")}</td>
                `;
                eventBody.appendChild(tr);
            });
        }

        renderAnalyticsPaginationControls('event', 'analytics-event-body', pageInfo);
    }
}

function refreshAnalytics() {
    if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_analytics_data !== "function") {
        console.log("[Ghost Analytics] get_analytics_data API is not available yet.");
        renderAnalytics({ ok: false, error: "get_analytics_data API is not available. Restart the dashboard or check start_dashboard.py." });
        return;
    }

    window.pywebview.api.get_analytics_data().then(data => {
        renderAnalytics(data);
    }).catch(err => {
        console.log("[Ghost Analytics] Refresh failed:", err);
        renderAnalytics({ ok: false, error: String(err || "Analytics refresh failed") });
    });
}

setInterval(function () {
    const analyticsSection = document.getElementById('analytics-section');
    if (analyticsSection && analyticsSection.style.display !== 'none') {
        refreshAnalytics();
    }
}, 5000);


// =====================================================
// MOBILE TASK QUEUE PANEL
// Injected safely into PC Control tab.
// =====================================================

(function () {
    const MOBILE_TASK_PANEL_MARKER = "mobile-task-panel-v1";

    function mtEscape(value) {
        return String(value === undefined || value === null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function mtShort(value, maxLen = 120) {
        const text = String(value === undefined || value === null ? "" : value);
        if (text.length <= maxLen) return text;
        return text.slice(0, maxLen) + "...";
    }

    function mtFormatTime(value) {
        if (!value) return "—";

        const n = Number(value);
        if (!Number.isFinite(n) || n <= 0) return "—";

        try {
            return new Date(n * 1000).toLocaleString();
        } catch (e) {
            return String(value);
        }
    }

    function mtStatusClass(status) {
        const s = String(status || "").toUpperCase();

        if (s === "COMPLETED") return "mobile-task-status-completed";
        if (s === "RUNNING") return "mobile-task-status-running";
        if (s === "FAILED") return "mobile-task-status-failed";
        if (s === "PENDING") return "mobile-task-status-pending";

        return "mobile-task-status-unknown";
    }

    function mtGetSelectedDevice() {
        const select = document.getElementById("mobile-task-device-select");
        return select ? String(select.value || "").trim() : "";
    }

    function mtSetStatus(message, isError = false) {
        const el = document.getElementById("mobile-task-status-line");
        if (!el) return;

        el.textContent = message || "";
        el.className = isError ? "mobile-task-status-line mobile-task-error" : "mobile-task-status-line";
    }

    function mtEnsurePanel() {
        if (document.getElementById(MOBILE_TASK_PANEL_MARKER)) {
            return true;
        }

        const pcSection = document.getElementById("pc-control-section");

        if (!pcSection) {
            return false;
        }

        const panel = document.createElement("div");
        panel.id = MOBILE_TASK_PANEL_MARKER;
        panel.className = "mobile-task-panel";

        panel.innerHTML = `
            <div class="mobile-task-header">
                <div>
                    <h3>Mobile Task Queue</h3>
                    <div class="mobile-task-subtitle">Send safe worker tasks to connected phones/tablets.</div>
                </div>
                <div class="mobile-task-controls">
                    <select id="mobile-task-device-select" class="mobile-task-select">
                        <option value="PHONE-01">PHONE-01</option>
                    </select>
                    <button class="btn btn-primary" onclick="refreshMobileTaskPanel()">REFRESH TASKS</button>
                </div>
            </div>

            <div class="mobile-task-buttons">
                <button class="btn btn-primary" onclick="sendMobileTask('PING')">PING</button>
                <button class="btn btn-primary" onclick="sendMobileTask('STATUS_SNAPSHOT')">STATUS SNAPSHOT</button>
                <button class="btn btn-primary" onclick="sendMobileTask('BATTERY_REPORT')">BATTERY REPORT</button>
                <button class="btn btn-primary" onclick="sendMobileTask('MARK_AVAILABLE')">MARK AVAILABLE</button>
                <button class="btn btn-warning" onclick="sendMobileTask('MARK_UNAVAILABLE')">MARK UNAVAILABLE</button>
                <button class="btn btn-danger" onclick="sendMobileTask('STOP_WORKER')">STOP WORKER</button>
            </div>

            <div id="mobile-task-status-line" class="mobile-task-status-line">Waiting for task data...</div>

            <div class="mobile-task-table-wrap">
                <table class="ghost-table mobile-task-table">
                    <thead>
                        <tr>
                            <th>Task ID</th>
                            <th>Device</th>
                            <th>Task Type</th>
                            <th>Status</th>
                            <th>Created</th>
                            <th>Claimed</th>
                            <th>Completed</th>
                            <th>Result</th>
                            <th>Error</th>
                        </tr>
                    </thead>
                    <tbody id="mobile-task-table-body">
                        <tr>
                            <td colspan="9">No mobile tasks loaded yet.</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        `;

        pcSection.appendChild(panel);
        return true;
    }

    async function mtRefreshDevices() {
        const select = document.getElementById("mobile-task-device-select");

        if (!select) {
            return;
        }

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_worker_data !== "function") {
            return;
        }

        try {
            const current = select.value || "PHONE-01";
            const response = await window.pywebview.api.get_worker_data();
            const workers = response && Array.isArray(response.workers) ? response.workers : [];

            let mobileWorkers = workers.filter(worker => {
                const type = String(worker.device_type || worker.type || "").toLowerCase();
                const pcId = String(worker.pc_id || "").toLowerCase();
                const canMobile = (
                    worker.can_run_mobile_tasks === true ||
                    worker.can_run_mobile_tasks === 1 ||
                    String(worker.can_run_mobile_tasks).toLowerCase() === "true"
                );

                return canMobile || type.includes("phone") || type.includes("tablet") || pcId.startsWith("phone");
            });

            if (mobileWorkers.length === 0) {
                mobileWorkers = workers.filter(worker => {
                    const pcId = String(worker.pc_id || "").trim();
                    return pcId.length > 0;
                });
            }

            const options = [];

            if (mobileWorkers.length === 0) {
                options.push(`<option value="PHONE-01">PHONE-01</option>`);
            } else {
                mobileWorkers.forEach(worker => {
                    const pcId = String(worker.pc_id || "").trim();
                    if (!pcId) return;

                    const type = worker.device_type || worker.device_role || "Device";
                    const label = `${pcId} (${type})`;

                    options.push(`<option value="${mtEscape(pcId)}">${mtEscape(label)}</option>`);
                });
            }

            select.innerHTML = options.join("");

            const values = Array.from(select.options).map(option => option.value);
            if (values.includes(current)) {
                select.value = current;
            }

        } catch (err) {
            console.log("[MobileTasks] Device refresh failed:", err);
        }
    }

    function mtRenderTasks(response) {
        const tbody = document.getElementById("mobile-task-table-body");

        if (!tbody) {
            return;
        }

        const tasks = response && Array.isArray(response.tasks) ? response.tasks : [];

        if (!response || response.ok === false) {
            tbody.innerHTML = `<tr><td colspan="9">Mobile task API unavailable: ${mtEscape(response && response.error ? response.error : "Unknown error")}</td></tr>`;
            return;
        }

        if (tasks.length === 0) {
            tbody.innerHTML = `<tr><td colspan="9">No tasks found for this device.</td></tr>`;
            return;
        }

        tbody.innerHTML = "";

        tasks.forEach(task => {
            const result = task.result || {};
            const resultText = Object.keys(result).length ? JSON.stringify(result) : "";

            const tr = document.createElement("tr");

            tr.innerHTML = `
                <td>${mtEscape(task.task_id || "")}</td>
                <td>${mtEscape(task.pc_id || "")}</td>
                <td>${mtEscape(task.task_type || "")}</td>
                <td><span class="mobile-task-status-pill ${mtStatusClass(task.status)}">${mtEscape(task.status || "")}</span></td>
                <td>${mtEscape(mtFormatTime(task.created_at))}</td>
                <td>${mtEscape(mtFormatTime(task.claimed_at))}</td>
                <td>${mtEscape(mtFormatTime(task.completed_at))}</td>
                <td title="${mtEscape(resultText)}">${mtEscape(mtShort(resultText, 120))}</td>
                <td>${mtEscape(mtShort(task.error || "", 80))}</td>
            `;

            tbody.appendChild(tr);
        });
    }

    window.refreshMobileTaskPanel = async function refreshMobileTaskPanel() {
        if (!mtEnsurePanel()) {
            return;
        }

        await mtRefreshDevices();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_mobile_tasks !== "function") {
            mtSetStatus("Dashboard backend bridge missing: get_mobile_tasks", true);
            mtRenderTasks({
                ok: false,
                error: "get_mobile_tasks bridge missing",
                tasks: []
            });
            return;
        }

        const pcId = mtGetSelectedDevice() || "PHONE-01";

        try {
            mtSetStatus(`Loading tasks for ${pcId}...`);

            const response = await window.pywebview.api.get_mobile_tasks(pcId, "", 50);

            mtRenderTasks(response);

            if (response && response.ok) {
                mtSetStatus(`Loaded recent tasks for ${pcId}.`);
            } else {
                mtSetStatus(response && response.error ? response.error : "Could not load mobile tasks.", true);
            }

        } catch (err) {
            console.log("[MobileTasks] refresh failed:", err);
            mtSetStatus(String(err), true);
            mtRenderTasks({
                ok: false,
                error: String(err),
                tasks: []
            });
        }
    };

    window.sendMobileTask = async function sendMobileTask(taskType) {
        if (!mtEnsurePanel()) {
            return;
        }

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.create_mobile_task !== "function") {
            mtSetStatus("Dashboard backend bridge missing: create_mobile_task", true);
            return;
        }

        const pcId = mtGetSelectedDevice() || "PHONE-01";
        const cleanTask = String(taskType || "").toUpperCase();

        if (!pcId) {
            mtSetStatus("Select a device first.", true);
            return;
        }

        if (cleanTask === "STOP_WORKER") {
            if (!confirm(`Stop mobile worker on ${pcId}?`)) {
                return;
            }
        }

        try {
            mtSetStatus(`Sending ${cleanTask} to ${pcId}...`);

            const response = await window.pywebview.api.create_mobile_task(pcId, cleanTask, {
                source: "dashboard",
                requested_at: Date.now()
            });

            if (!response || response.ok === false) {
                mtSetStatus(response && response.error ? response.error : "Task create failed.", true);
                return;
            }

            mtSetStatus(`Task ${cleanTask} created for ${pcId}. Waiting for worker result...`);

            setTimeout(window.refreshMobileTaskPanel, 1500);
            setTimeout(window.refreshMobileTaskPanel, 5000);

        } catch (err) {
            console.log("[MobileTasks] create task failed:", err);
            mtSetStatus(String(err), true);
        }
    };

    function mtAutoRefreshWhenPcControlVisible() {
        const pcSection = document.getElementById("pc-control-section");

        if (!pcSection || pcSection.style.display === "none") {
            return;
        }

        mtEnsurePanel();
        window.refreshMobileTaskPanel();
    }

    document.addEventListener("DOMContentLoaded", function () {
        setTimeout(mtAutoRefreshWhenPcControlVisible, 1000);
    });

    setInterval(function () {
        const panel = document.getElementById(MOBILE_TASK_PANEL_MARKER);
        const pcSection = document.getElementById("pc-control-section");

        if (pcSection && pcSection.style.display !== "none") {
            if (!panel) {
                mtEnsurePanel();
            }

            window.refreshMobileTaskPanel();
        }
    }, 10000);
})();



// =====================================================
// BACKUP + ROLLBACK MANAGER PANEL
// Injected safely into PC Control tab.
// =====================================================

(function () {
    const BACKUP_PANEL_MARKER = "backup-rollback-panel-v1";

    function bmEscape(value) {
        return String(value === undefined || value === null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function bmShort(value, maxLen = 120) {
        const text = String(value === undefined || value === null ? "" : value);
        if (text.length <= maxLen) return text;
        return text.slice(0, maxLen) + "...";
    }

    function bmSetStatus(message, isError = false) {
        const el = document.getElementById("backup-manager-status-line");
        if (!el) return;

        el.textContent = message || "";
        el.className = isError ? "backup-manager-status-line backup-manager-error" : "backup-manager-status-line";
    }

    function bmGetSelectedBackup() {
        const select = document.getElementById("backup-manager-select");
        return select ? String(select.value || "").trim() : "";
    }

    function bmEnsurePanel() {
        if (document.getElementById(BACKUP_PANEL_MARKER)) {
            return true;
        }

        const pcSection = document.getElementById("pc-control-section");

        if (!pcSection) {
            return false;
        }

        const panel = document.createElement("div");
        panel.id = BACKUP_PANEL_MARKER;
        panel.className = "backup-manager-panel";

        panel.innerHTML = `
            <div class="backup-manager-header">
                <div>
                    <h3>Backup + Rollback Manager</h3>
                    <div class="backup-manager-subtitle">
                        Protects source code files only. Configs, DBs, profiles, extensions, and logs are excluded.
                    </div>
                </div>
                <div class="backup-manager-controls">
                    <select id="backup-manager-select" class="backup-manager-select">
                        <option value="">No backups loaded</option>
                    </select>
                    <button class="btn btn-primary" onclick="refreshBackupManagerPanel()">REFRESH BACKUPS</button>
                </div>
            </div>

            <div class="backup-manager-buttons">
                <button class="btn btn-primary" onclick="createBackupFromDashboard()">CREATE BACKUP</button>
                <button class="btn btn-warning" onclick="restoreSelectedBackup()">RESTORE SELECTED</button>
                <button class="btn btn-warning" onclick="restoreLatestBackup()">RESTORE LATEST</button>
                <button class="btn btn-danger" onclick="deleteSelectedBackup()">DELETE SELECTED</button>
            </div>

            <div id="backup-manager-status-line" class="backup-manager-status-line">
                Waiting for backup data...
            </div>

            <div class="backup-manager-summary" id="backup-manager-summary">
                Backup root: —
            </div>

            <div class="backup-manager-table-wrap">
                <table class="ghost-table backup-manager-table">
                    <thead>
                        <tr>
                            <th>Backup ID</th>
                            <th>Label</th>
                            <th>Created</th>
                            <th>Files</th>
                            <th>Size</th>
                            <th>Path</th>
                        </tr>
                    </thead>
                    <tbody id="backup-manager-table-body">
                        <tr>
                            <td colspan="6">No backups loaded yet.</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        `;

        pcSection.appendChild(panel);
        return true;
    }

    function bmRenderBackups(response) {
        const tbody = document.getElementById("backup-manager-table-body");
        const select = document.getElementById("backup-manager-select");
        const summary = document.getElementById("backup-manager-summary");

        if (!tbody || !select) {
            return;
        }

        const backups = response && Array.isArray(response.backups) ? response.backups : [];

        if (summary) {
            summary.textContent = response && response.backup_root
                ? `Backup root: ${response.backup_root}`
                : "Backup root: —";
        }

        if (!response || response.ok === false) {
            const error = response && response.error ? response.error : "Unknown error";
            tbody.innerHTML = `<tr><td colspan="6">Backup manager unavailable: ${bmEscape(error)}</td></tr>`;
            select.innerHTML = `<option value="">Backup manager unavailable</option>`;
            return;
        }

        if (backups.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6">No backups found. Click CREATE BACKUP first.</td></tr>`;
            select.innerHTML = `<option value="">No backups found</option>`;
            return;
        }

        select.innerHTML = backups.map((backup, index) => {
            const selected = index === 0 ? "selected" : "";
            return `<option value="${bmEscape(backup.backup_id)}" ${selected}>${bmEscape(backup.backup_id)}</option>`;
        }).join("");

        tbody.innerHTML = "";

        backups.forEach(backup => {
            const tr = document.createElement("tr");

            tr.innerHTML = `
                <td>${bmEscape(backup.backup_id || "")}</td>
                <td>${bmEscape(backup.label || "")}</td>
                <td>${bmEscape(backup.created_at || "")}</td>
                <td>${bmEscape(backup.file_count || 0)}</td>
                <td>${bmEscape(backup.size_text || "")}</td>
                <td title="${bmEscape(backup.path || "")}">${bmEscape(bmShort(backup.path || "", 90))}</td>
            `;

            tbody.appendChild(tr);
        });
    }

    window.refreshBackupManagerPanel = async function refreshBackupManagerPanel() {
        if (!bmEnsurePanel()) {
            return;
        }

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_backup_manager_status !== "function") {
            bmSetStatus("Dashboard backend bridge missing: get_backup_manager_status", true);
            bmRenderBackups({
                ok: false,
                error: "get_backup_manager_status bridge missing",
                backups: []
            });
            return;
        }

        try {
            bmSetStatus("Loading backups...");

            const response = await window.pywebview.api.get_backup_manager_status();

            bmRenderBackups(response);

            if (response && response.ok) {
                bmSetStatus(`Loaded ${response.backup_count || 0} backup(s).`);
            } else {
                bmSetStatus(response && response.error ? response.error : "Could not load backups.", true);
            }

        } catch (err) {
            console.log("[BackupManager] refresh failed:", err);
            bmSetStatus(String(err), true);
            bmRenderBackups({
                ok: false,
                error: String(err),
                backups: []
            });
        }
    };

    window.createBackupFromDashboard = async function createBackupFromDashboard() {
        if (!bmEnsurePanel()) {
            return;
        }

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.create_system_backup !== "function") {
            bmSetStatus("Dashboard backend bridge missing: create_system_backup", true);
            return;
        }

        const label = prompt("Backup label:", "manual");

        if (label === null) {
            return;
        }

        try {
            bmSetStatus("Creating backup...");

            const response = await window.pywebview.api.create_system_backup(label || "manual");

            if (!response || response.ok === false) {
                bmSetStatus(response && response.error ? response.error : "Backup create failed.", true);
                return;
            }

            bmSetStatus(`Backup created: ${response.backup_id} (${response.copied_count} files).`);
            setTimeout(window.refreshBackupManagerPanel, 500);

        } catch (err) {
            console.log("[BackupManager] create failed:", err);
            bmSetStatus(String(err), true);
        }
    };

    window.restoreSelectedBackup = async function restoreSelectedBackup() {
        const backupId = bmGetSelectedBackup();

        if (!backupId) {
            bmSetStatus("Select a backup first.", true);
            return;
        }

        if (!confirm(`Restore backup?\n\n${backupId}\n\nA pre-restore backup will be created first. Restart will be required.`)) {
            return;
        }

        await bmRestoreBackup(backupId);
    };

    window.restoreLatestBackup = async function restoreLatestBackup() {
        const select = document.getElementById("backup-manager-select");

        if (!select || !select.options.length || !select.options[0].value) {
            bmSetStatus("No latest backup available.", true);
            return;
        }

        const backupId = select.options[0].value;

        if (!confirm(`Restore latest backup?\n\n${backupId}\n\nA pre-restore backup will be created first. Restart will be required.`)) {
            return;
        }

        await bmRestoreBackup(backupId);
    };

    async function bmRestoreBackup(backupId) {
        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.restore_system_backup !== "function") {
            bmSetStatus("Dashboard backend bridge missing: restore_system_backup", true);
            return;
        }

        try {
            bmSetStatus(`Restoring ${backupId}...`);

            const response = await window.pywebview.api.restore_system_backup(backupId);

            if (!response || response.ok === false) {
                bmSetStatus(response && response.error ? response.error : "Restore failed.", true);
                return;
            }

            bmSetStatus(`Restore complete from ${backupId}. Pre-restore backup: ${response.pre_restore_backup}. Restart required.`);
            alert("Restore complete. Close and restart the dashboard/coordinator for restored code to take effect.");

            setTimeout(window.refreshBackupManagerPanel, 500);

        } catch (err) {
            console.log("[BackupManager] restore failed:", err);
            bmSetStatus(String(err), true);
        }
    }

    window.deleteSelectedBackup = async function deleteSelectedBackup() {
        const backupId = bmGetSelectedBackup();

        if (!backupId) {
            bmSetStatus("Select a backup first.", true);
            return;
        }

        if (!confirm(`Delete backup?\n\n${backupId}\n\nThis cannot be undone.`)) {
            return;
        }

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.delete_system_backup !== "function") {
            bmSetStatus("Dashboard backend bridge missing: delete_system_backup", true);
            return;
        }

        try {
            bmSetStatus(`Deleting ${backupId}...`);

            const response = await window.pywebview.api.delete_system_backup(backupId);

            if (!response || response.ok === false) {
                bmSetStatus(response && response.error ? response.error : "Delete failed.", true);
                return;
            }

            bmSetStatus(`Deleted backup: ${backupId}`);
            setTimeout(window.refreshBackupManagerPanel, 500);

        } catch (err) {
            console.log("[BackupManager] delete failed:", err);
            bmSetStatus(String(err), true);
        }
    };

    function bmAutoRefreshWhenPcControlVisible() {
        const pcSection = document.getElementById("pc-control-section");

        if (!pcSection || pcSection.style.display === "none") {
            return;
        }

        bmEnsurePanel();
        window.refreshBackupManagerPanel();
    }

    document.addEventListener("DOMContentLoaded", function () {
        setTimeout(bmAutoRefreshWhenPcControlVisible, 1200);
    });

    setInterval(function () {
        const pcSection = document.getElementById("pc-control-section");

        if (pcSection && pcSection.style.display !== "none") {
            bmEnsurePanel();
        }
    }, 10000);
})();



// =====================================================
// SYSTEM DIAGNOSTICS + LOG VIEWER PANEL
// Injected safely into PC Control tab.
// =====================================================

(function () {
    const DIAG_PANEL_MARKER = "system-diagnostics-panel-v1";

    function dxEscape(value) {
        return String(value === undefined || value === null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function dxShort(value, maxLen = 100) {
        const text = String(value === undefined || value === null ? "" : value);
        if (text.length <= maxLen) return text;
        return text.slice(0, maxLen) + "...";
    }

    function dxSetStatus(message, isError = false) {
        const el = document.getElementById("diagnostics-status-line");
        if (!el) return;

        el.textContent = message || "";
        el.className = isError ? "diagnostics-status-line diagnostics-error" : "diagnostics-status-line";
    }

    function dxBoolPill(ok, labelOk = "OK", labelBad = "FAILED") {
        if (ok) {
            return `<span class="diagnostics-pill diagnostics-pill-ok">${labelOk}</span>`;
        }

        return `<span class="diagnostics-pill diagnostics-pill-bad">${labelBad}</span>`;
    }

    function dxEnsurePanel() {
        if (document.getElementById(DIAG_PANEL_MARKER)) {
            return true;
        }

        const pcSection = document.getElementById("pc-control-section");

        if (!pcSection) {
            return false;
        }

        const panel = document.createElement("div");
        panel.id = DIAG_PANEL_MARKER;
        panel.className = "diagnostics-panel";

        panel.innerHTML = `
            <div class="diagnostics-header">
                <div>
                    <h3>System Diagnostics + Log Viewer</h3>
                    <div class="diagnostics-subtitle">
                        Checks coordinator routes, local files, Python compile status, and recent logs.
                    </div>
                </div>
                <div class="diagnostics-controls">
                    <select id="diagnostics-log-select" class="diagnostics-select">
                        <option value="crash">crash_log.txt</option>
                        <option value="health">health_log.txt</option>
                        <option value="sync_client">sync_client_log.txt</option>
                        <option value="coordinator">coordinator_log.txt</option>
                        <option value="mobile_worker">mobile_worker_log.txt</option>
                    </select>
                    <button class="btn btn-primary" onclick="refreshSystemDiagnostics()">REFRESH DIAGNOSTICS</button>
                </div>
            </div>

            <div class="diagnostics-buttons">
                <button class="btn btn-primary" onclick="refreshSystemDiagnostics()">RUN FULL SYSTEM CHECK</button>
                <button class="btn btn-primary" onclick="openSelectedSystemLog()">OPEN SELECTED LOG</button>
                <button class="btn btn-warning" onclick="clearSelectedSystemLog()">CLEAR SELECTED LOG</button>
                <button class="btn btn-primary" onclick="clearDiagnosticsViewer()">CLEAR VIEWER</button>
            </div>

            <div id="diagnostics-status-line" class="diagnostics-status-line">
                Waiting for diagnostics...
            </div>

            <div class="diagnostics-summary-grid" id="diagnostics-summary-grid">
                <div class="diagnostics-card">Overall: —</div>
                <div class="diagnostics-card">Routes: —</div>
                <div class="diagnostics-card">Compile: —</div>
                <div class="diagnostics-card">Files: —</div>
            </div>

            <div class="diagnostics-grid">
                <div class="diagnostics-block">
                    <h4>Coordinator Routes</h4>
                    <table class="ghost-table diagnostics-table">
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>Route</th>
                                <th>Required</th>
                                <th>Status</th>
                                <th>Error</th>
                            </tr>
                        </thead>
                        <tbody id="diagnostics-routes-body">
                            <tr><td colspan="5">No route checks loaded.</td></tr>
                        </tbody>
                    </table>
                </div>

                <div class="diagnostics-block">
                    <h4>Python Compile Check</h4>
                    <table class="ghost-table diagnostics-table">
                        <thead>
                            <tr>
                                <th>File</th>
                                <th>Status</th>
                                <th>Error</th>
                            </tr>
                        </thead>
                        <tbody id="diagnostics-compile-body">
                            <tr><td colspan="3">No compile checks loaded.</td></tr>
                        </tbody>
                    </table>
                </div>

                <div class="diagnostics-block">
                    <h4>Local Files</h4>
                    <table class="ghost-table diagnostics-table">
                        <thead>
                            <tr>
                                <th>File</th>
                                <th>Exists</th>
                                <th>Size</th>
                            </tr>
                        </thead>
                        <tbody id="diagnostics-files-body">
                            <tr><td colspan="3">No file checks loaded.</td></tr>
                        </tbody>
                    </table>
                </div>

                <div class="diagnostics-block">
                    <h4>Logs</h4>
                    <table class="ghost-table diagnostics-table">
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>Exists</th>
                                <th>Size</th>
                            </tr>
                        </thead>
                        <tbody id="diagnostics-logs-body">
                            <tr><td colspan="3">No log checks loaded.</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <div class="diagnostics-log-viewer">
                <div class="diagnostics-log-title" id="diagnostics-log-title">
                    Log viewer
                </div>
                <pre id="diagnostics-log-content">No log loaded.</pre>
            </div>
        `;

        pcSection.appendChild(panel);
        return true;
    }

    function dxRenderDiagnostics(response) {
        const summary = document.getElementById("diagnostics-summary-grid");
        const routesBody = document.getElementById("diagnostics-routes-body");
        const compileBody = document.getElementById("diagnostics-compile-body");
        const filesBody = document.getElementById("diagnostics-files-body");
        const logsBody = document.getElementById("diagnostics-logs-body");

        if (!summary || !routesBody || !compileBody || !filesBody || !logsBody) {
            return;
        }

        if (!response || response.ok === false) {
            const error = response && response.error ? response.error : "Unknown diagnostics error";

            summary.innerHTML = `
                <div class="diagnostics-card diagnostics-card-bad">Overall: FAILED</div>
                <div class="diagnostics-card">Routes: —</div>
                <div class="diagnostics-card">Compile: —</div>
                <div class="diagnostics-card">Files: —</div>
            `;

            routesBody.innerHTML = `<tr><td colspan="5">Diagnostics unavailable: ${dxEscape(error)}</td></tr>`;
            compileBody.innerHTML = `<tr><td colspan="3">Diagnostics unavailable.</td></tr>`;
            filesBody.innerHTML = `<tr><td colspan="3">Diagnostics unavailable.</td></tr>`;
            logsBody.innerHTML = `<tr><td colspan="3">Diagnostics unavailable.</td></tr>`;
            return;
        }

        const s = response.summary || {};

        summary.innerHTML = `
            <div class="diagnostics-card ${response.overall_ok ? "diagnostics-card-ok" : "diagnostics-card-bad"}">
                Overall: ${response.overall_ok ? "OK" : "FAILED"}
            </div>
            <div class="diagnostics-card">Route Failures: ${dxEscape(s.required_route_failures || 0)}</div>
            <div class="diagnostics-card">Compile Failures: ${dxEscape(s.compile_failures || 0)}</div>
            <div class="diagnostics-card">Missing Files: ${dxEscape(s.missing_files || 0)}</div>
        `;

        const routes = Array.isArray(response.routes) ? response.routes : [];
        if (routes.length === 0) {
            routesBody.innerHTML = `<tr><td colspan="5">No route checks found.</td></tr>`;
        } else {
            routesBody.innerHTML = "";
            routes.forEach(route => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td>${dxEscape(route.name || "")}</td>
                    <td>${dxEscape(route.path || "")}</td>
                    <td>${route.required ? "YES" : "NO"}</td>
                    <td>${dxBoolPill(route.ok)}</td>
                    <td title="${dxEscape(route.error || "")}">${dxEscape(dxShort(route.error || "", 80))}</td>
                `;
                routesBody.appendChild(tr);
            });
        }

        const compile = Array.isArray(response.compile) ? response.compile : [];
        if (compile.length === 0) {
            compileBody.innerHTML = `<tr><td colspan="3">No compile checks found.</td></tr>`;
        } else {
            compileBody.innerHTML = "";
            compile.forEach(item => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td>${dxEscape(item.file || "")}</td>
                    <td>${dxBoolPill(item.ok)}</td>
                    <td title="${dxEscape(item.error || "")}">${dxEscape(dxShort(item.error || "", 120))}</td>
                `;
                compileBody.appendChild(tr);
            });
        }

        const files = Array.isArray(response.files) ? response.files : [];
        if (files.length === 0) {
            filesBody.innerHTML = `<tr><td colspan="3">No file checks found.</td></tr>`;
        } else {
            filesBody.innerHTML = "";
            files.forEach(item => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td>${dxEscape(item.file || "")}</td>
                    <td>${item.exists ? dxBoolPill(true, "YES", "NO") : dxBoolPill(false, "YES", "NO")}</td>
                    <td>${dxEscape(item.size_text || "")}</td>
                `;
                filesBody.appendChild(tr);
            });
        }

        const logs = Array.isArray(response.logs) ? response.logs : [];
        if (logs.length === 0) {
            logsBody.innerHTML = `<tr><td colspan="3">No log checks found.</td></tr>`;
        } else {
            logsBody.innerHTML = "";
            logs.forEach(item => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td>${dxEscape(item.name || "")}</td>
                    <td>${item.exists ? dxBoolPill(true, "YES", "NO") : dxBoolPill(false, "YES", "NO")}</td>
                    <td>${dxEscape(item.size_text || "")}</td>
                `;
                logsBody.appendChild(tr);
            });
        }
    }

    window.refreshSystemDiagnostics = async function refreshSystemDiagnostics() {
        if (!dxEnsurePanel()) {
            return;
        }

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_system_diagnostics !== "function") {
            dxSetStatus("Dashboard backend bridge missing: get_system_diagnostics", true);
            dxRenderDiagnostics({
                ok: false,
                error: "get_system_diagnostics bridge missing"
            });
            return;
        }

        try {
            dxSetStatus("Running full system diagnostics...");

            const response = await window.pywebview.api.get_system_diagnostics();

            dxRenderDiagnostics(response);

            if (response && response.ok) {
                dxSetStatus(response.overall_ok ? "Diagnostics passed." : "Diagnostics found issues.", !response.overall_ok);
            } else {
                dxSetStatus(response && response.error ? response.error : "Diagnostics failed.", true);
            }

        } catch (err) {
            console.log("[Diagnostics] refresh failed:", err);
            dxSetStatus(String(err), true);
            dxRenderDiagnostics({
                ok: false,
                error: String(err)
            });
        }
    };

    window.openSelectedSystemLog = async function openSelectedSystemLog() {
        if (!dxEnsurePanel()) {
            return;
        }

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.read_system_log !== "function") {
            dxSetStatus("Dashboard backend bridge missing: read_system_log", true);
            return;
        }

        const select = document.getElementById("diagnostics-log-select");
        const logName = select ? select.value : "crash";

        try {
            dxSetStatus(`Loading ${logName} log...`);

            const response = await window.pywebview.api.read_system_log(logName, 500);

            const title = document.getElementById("diagnostics-log-title");
            const content = document.getElementById("diagnostics-log-content");

            if (!response || response.ok === false) {
                dxSetStatus(response && response.error ? response.error : "Could not read log.", true);
                return;
            }

            if (title) {
                title.textContent = `${response.log_name} log — ${response.path}`;
            }

            if (content) {
                if (!response.exists) {
                    content.textContent = "Log file does not exist yet.";
                } else {
                    content.textContent = response.content || "";
                }
            }

            dxSetStatus(`Loaded ${logName} log.`);

        } catch (err) {
            console.log("[Diagnostics] read log failed:", err);
            dxSetStatus(String(err), true);
        }
    };

    window.clearSelectedSystemLog = async function clearSelectedSystemLog() {
        if (!dxEnsurePanel()) {
            return;
        }

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.clear_system_log !== "function") {
            dxSetStatus("Dashboard backend bridge missing: clear_system_log", true);
            return;
        }

        const select = document.getElementById("diagnostics-log-select");
        const logName = select ? select.value : "crash";

        if (!confirm(`Clear ${logName} log?`)) {
            return;
        }

        try {
            const response = await window.pywebview.api.clear_system_log(logName);

            if (!response || response.ok === false) {
                dxSetStatus(response && response.error ? response.error : "Could not clear log.", true);
                return;
            }

            dxSetStatus(`Cleared ${logName} log.`);
            window.openSelectedSystemLog();
            window.refreshSystemDiagnostics();

        } catch (err) {
            console.log("[Diagnostics] clear log failed:", err);
            dxSetStatus(String(err), true);
        }
    };

    window.clearDiagnosticsViewer = function clearDiagnosticsViewer() {
        const content = document.getElementById("diagnostics-log-content");
        const title = document.getElementById("diagnostics-log-title");

        if (content) {
            content.textContent = "Viewer cleared.";
        }

        if (title) {
            title.textContent = "Log viewer";
        }

        dxSetStatus("Viewer cleared.");
    };

    function dxAutoRefreshWhenPcControlVisible() {
        const pcSection = document.getElementById("pc-control-section");

        if (!pcSection || pcSection.style.display === "none") {
            return;
        }

        dxEnsurePanel();
        window.refreshSystemDiagnostics();
    }

    document.addEventListener("DOMContentLoaded", function () {
        setTimeout(dxAutoRefreshWhenPcControlVisible, 1500);
    });

    setInterval(function () {
        const pcSection = document.getElementById("pc-control-section");

        if (pcSection && pcSection.style.display !== "none") {
            dxEnsurePanel();
        }
    }, 10000);
})();

// =====================================================
// EASY VERSION STATUS + SYNC HISTORY PANEL
// =====================================================

(function () {
    const ID = "easy-version-panel";

    function e(v) {
        return String(v === undefined || v === null ? "" : v)
            .replace(/&/g, "&amp;").replace(/</g, "&lt;")
            .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }

    function short(v) {
        v = String(v || "");
        return v.length > 14 ? v.slice(0, 14) + "..." : v;
    }

    function pill(status) {
        let cls = "version-pill-muted";
        if (status === "MATCH") cls = "version-pill-ok";
        if (status === "DIFFERENT") cls = "version-pill-warn";
        if (String(status).includes("MISSING")) cls = "version-pill-bad";
        return `<span class="version-pill ${cls}">${e(status)}</span>`;
    }

    function ensurePanel() {
        if (document.getElementById(ID)) return true;

        const pc = document.getElementById("pc-control-section");
        if (!pc) return false;

        const div = document.createElement("div");
        div.id = ID;
        div.className = "version-panel";
        div.innerHTML = `
            <div class="version-header">
                <div>
                    <h3>Version Status + Sync History</h3>
                    <div class="version-subtitle">Simple check: laptop files vs main PC files.</div>
                </div>
                <div class="version-controls">
                    <button class="btn btn-primary" onclick="refreshVersionStatusPanel()">REFRESH</button>
                    <button class="btn btn-primary" onclick="createVersionSnapshotFromDashboard()">SNAPSHOT</button>
                    <button class="btn btn-warning" onclick="clearSyncHistoryFromDashboard()">CLEAR HISTORY</button>
                </div>
            </div>
            <div id="version-status-line" class="version-status-line">Waiting...</div>
            <div class="version-summary-grid" id="version-summary-grid">
                <div class="version-card">Remote: —</div>
                <div class="version-card">Local: —</div>
                <div class="version-card">Remote Files: —</div>
                <div class="version-card">Different: —</div>
            </div>
            <div class="version-block version-block-wide">
                <h4>File Compare</h4>
                <table class="ghost-table version-table">
                    <thead><tr><th>File</th><th>Status</th><th>Local Size</th><th>Remote Size</th><th>Local SHA</th><th>Remote SHA</th></tr></thead>
                    <tbody id="version-compare-body"><tr><td colspan="6">No data yet.</td></tr></tbody>
                </table>
            </div>
            <div class="version-block version-block-wide">
                <h4>Sync History</h4>
                <table class="ghost-table version-table">
                    <thead><tr><th>Time</th><th>Status</th><th>Changed</th><th>Error</th></tr></thead>
                    <tbody id="version-history-body"><tr><td colspan="4">No history yet.</td></tr></tbody>
                </table>
            </div>
        `;
        pc.appendChild(div);
        return true;
    }

    window.refreshVersionStatusPanel = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_version_status !== "function") {
            document.getElementById("version-status-line").textContent = "Backend function missing: get_version_status";
            return;
        }

        const res = await window.pywebview.api.get_version_status();
        const s = res.summary || {};
        document.getElementById("version-status-line").textContent = res.remote_available ? "Version status loaded." : (res.remote_error || "Remote unavailable.");

        document.getElementById("version-summary-grid").innerHTML = `
            <div class="version-card ${res.remote_available ? "version-card-ok" : "version-card-bad"}">Remote: ${res.remote_available ? "CONNECTED" : "UNAVAILABLE"}</div>
            <div class="version-card">Local: ${e(s.local_count || 0)}</div>
            <div class="version-card">Remote Files: ${e(s.remote_count || 0)}</div>
            <div class="version-card ${Number(s.different || 0) ? "version-card-warn" : "version-card-ok"}">Different: ${e(s.different || 0)}</div>
        `;

        const body = document.getElementById("version-compare-body");
        body.innerHTML = "";
        (res.comparisons || []).forEach(x => {
            const tr = document.createElement("tr");
            tr.innerHTML = `<td>${e(x.path)}</td><td>${pill(x.status)}</td><td>${e(x.local_size)}</td><td>${e(x.remote_size)}</td><td title="${e(x.local_sha256)}">${e(short(x.local_sha256))}</td><td title="${e(x.remote_sha256)}">${e(short(x.remote_sha256))}</td>`;
            body.appendChild(tr);
        });

        const hbody = document.getElementById("version-history-body");
        hbody.innerHTML = "";
        const hist = res.sync_history || [];
        if (!hist.length) {
            hbody.innerHTML = `<tr><td colspan="4">No sync history yet.</td></tr>`;
        } else {
            hist.forEach(x => {
                const changed = Array.isArray(x.changed) ? x.changed.length : (x.changed_count || 0);
                const tr = document.createElement("tr");
                tr.innerHTML = `<td>${e(x.started_at || "")}</td><td>${x.ok ? "OK" : "FAILED"}</td><td>${e(changed)}</td><td>${e(x.error || "")}</td>`;
                hbody.appendChild(tr);
            });
        }
    };

    window.createVersionSnapshotFromDashboard = async function () {
        const label = prompt("Snapshot label:", "version_snapshot");
        if (label === null) return;
        const res = await window.pywebview.api.create_version_snapshot(label);
        alert(res.ok ? "Snapshot created: " + res.snapshot_id : "Snapshot failed: " + res.error);
        refreshVersionStatusPanel();
    };

    window.clearSyncHistoryFromDashboard = async function () {
        if (!confirm("Clear sync history?")) return;
        const res = await window.pywebview.api.clear_sync_history();
        alert(res.ok ? "Sync history cleared" : "Failed: " + res.error);
        refreshVersionStatusPanel();
    };

    document.addEventListener("DOMContentLoaded", function () {
        setTimeout(function () {
            const pc = document.getElementById("pc-control-section");
            if (pc && pc.style.display !== "none") {
                ensurePanel();
                refreshVersionStatusPanel();
            }
        }, 1800);
    });

    setInterval(function () {
        const pc = document.getElementById("pc-control-section");
        if (pc && pc.style.display !== "none") ensurePanel();
    }, 10000);
})();

// =====================================================
// DEVICE GROUPS + PERMISSIONS PANEL
// =====================================================
(function () {
    const PANEL_ID = "device-permissions-panel";
    let selectedDeviceId = "";
    function esc(v){return String(v===undefined||v===null?"":v).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}
    function yes(v){return v?"YES":"NO";}
    function short(v,m=80){v=String(v||"");return v.length>m?v.slice(0,m)+"...":v;}
    function status(msg,bad=false){const el=document.getElementById("device-permissions-status"); if(el){el.textContent=msg||""; el.className=bad?"device-permissions-status bad":"device-permissions-status";}}
    function ensurePanel(){
        if(document.getElementById(PANEL_ID)) return true;
        const pc=document.getElementById("pc-control-section"); if(!pc) return false;
        const panel=document.createElement("div"); panel.id=PANEL_ID; panel.className="device-permissions-panel";
        panel.innerHTML=`
            <div class="device-permissions-header"><div><h3>Device Groups + Permissions</h3><div class="device-permissions-subtitle">Assign each connected PC, laptop, or phone to a controlled role.</div></div>
            <div class="device-permissions-controls"><select id="device-role-select" class="device-role-select"><option value="main_controller">Main Controller</option><option value="worker_laptop">Worker Laptop</option><option value="worker_pc">Worker PC</option><option value="phone_worker">Phone Worker</option><option value="monitor_only">Monitor Only</option><option value="blocked">Blocked</option></select><button class="btn btn-primary" onclick="refreshDevicePermissionsPanel()">REFRESH DEVICES</button><button class="btn btn-primary" onclick="applySelectedDeviceRole()">APPLY ROLE</button><button class="btn btn-warning" onclick="blockSelectedDevice()">BLOCK</button><button class="btn btn-primary" onclick="unblockSelectedDevice()">UNBLOCK</button></div></div>
            <div id="device-permissions-status" class="device-permissions-status">Waiting for device permissions...</div>
            <div class="device-permissions-table-wrap"><table class="ghost-table device-permissions-table"><thead><tr><th>Select</th><th>Device ID</th><th>Role</th><th>Blocked</th><th>Launch</th><th>Mobile Tasks</th><th>Control Fleet</th><th>Edit Targets</th><th>Delete Profiles</th><th>Worker Info</th></tr></thead><tbody id="device-permissions-body"><tr><td colspan="10">No device data loaded.</td></tr></tbody></table></div>`;
        pc.appendChild(panel); return true;
    }
    function normalizeWorkers(workers){ if(!Array.isArray(workers)) return []; return workers.map((w,i)=>Object.assign({},w,{pc_id:String(w.pc_id||w.id||w.name||w.device_id||("worker_"+i))})); }
    function defaultPerm(role,pcId){ role=String(role||"monitor_only").toLowerCase(); const p={main_controller:{role,pc_id:pcId,is_blocked:false,can_launch_profiles:true,can_run_mobile_tasks:true,can_control_fleet:true,can_edit_targets:true,can_delete_profiles:true},worker_laptop:{role,pc_id:pcId,is_blocked:false,can_launch_profiles:true,can_run_mobile_tasks:true,can_control_fleet:false,can_edit_targets:false,can_delete_profiles:false},worker_pc:{role,pc_id:pcId,is_blocked:false,can_launch_profiles:true,can_run_mobile_tasks:false,can_control_fleet:false,can_edit_targets:false,can_delete_profiles:false},phone_worker:{role,pc_id:pcId,is_blocked:false,can_launch_profiles:false,can_run_mobile_tasks:true,can_control_fleet:false,can_edit_targets:false,can_delete_profiles:false},monitor_only:{role,pc_id:pcId,is_blocked:false,can_launch_profiles:false,can_run_mobile_tasks:false,can_control_fleet:false,can_edit_targets:false,can_delete_profiles:false},blocked:{role,pc_id:pcId,is_blocked:true,can_launch_profiles:false,can_run_mobile_tasks:false,can_control_fleet:false,can_edit_targets:false,can_delete_profiles:false}}; return p[role]||p.monitor_only; }
    function render(data){
        const body=document.getElementById("device-permissions-body"); if(!body) return;
        const workers=normalizeWorkers(data.workers||[]), devices=data.devices||{}, rows={};
        workers.forEach(w=>rows[w.pc_id]={worker:w,permission:devices[w.pc_id]||null}); Object.keys(devices).forEach(id=>{if(!rows[id]) rows[id]={worker:null,permission:devices[id]};});
        const ids=Object.keys(rows).sort(); if(!ids.length){body.innerHTML='<tr><td colspan="10">No devices found yet. Start workers or mobile devices first.</td></tr>'; return;}
        body.innerHTML=""; ids.forEach(id=>{const r=rows[id], w=r.worker||{}, p=r.permission||defaultPerm("monitor_only",id); const info=[w.device_type||w.type||"", w.ip||w.source_ip||w.host||"", w.status||w.state||"", w.last_seen||w.updated_at||""].filter(Boolean).join(" | "); const tr=document.createElement("tr"); tr.innerHTML=`<td><input type="radio" name="device-permission-select" value="${esc(id)}" ${selectedDeviceId===id?"checked":""}></td><td>${esc(id)}</td><td><span class="device-role-pill">${esc(p.role||"monitor_only")}</span></td><td>${yes(p.is_blocked)}</td><td>${yes(p.can_launch_profiles)}</td><td>${yes(p.can_run_mobile_tasks)}</td><td>${yes(p.can_control_fleet)}</td><td>${yes(p.can_edit_targets)}</td><td>${yes(p.can_delete_profiles)}</td><td title="${esc(info)}">${esc(short(info||"—",90))}</td>`; body.appendChild(tr);});
        body.querySelectorAll('input[name="device-permission-select"]').forEach(input=>input.addEventListener("change",function(){selectedDeviceId=this.value;}));
    }
    window.refreshDevicePermissionsPanel=async function(){ ensurePanel(); if(!window.pywebview||!window.pywebview.api||typeof window.pywebview.api.get_device_permissions!=="function"){status("Backend bridge missing: get_device_permissions",true); return;} try{status("Loading device permissions..."); const data=await window.pywebview.api.get_device_permissions(); if(!data||data.ok===false){status(data&&data.error?data.error:"Could not load device permissions.",true); render({workers:[],devices:{}}); return;} render(data); status("Device permissions loaded.");}catch(err){status(String(err),true);}};
    window.applySelectedDeviceRole=async function(){ if(!selectedDeviceId){alert("Select a device first.");return;} const role=(document.getElementById("device-role-select")||{}).value||"monitor_only"; try{status("Applying role..."); const r=await window.pywebview.api.set_device_permission(selectedDeviceId,role); if(!r||r.ok===false){status(r&&r.error?r.error:"Could not apply role.",true);return;} status("Role applied."); refreshDevicePermissionsPanel();}catch(err){status(String(err),true);}};
    window.blockSelectedDevice=async function(){ if(!selectedDeviceId){alert("Select a device first.");return;} if(!confirm("Block this device?"))return; const r=await window.pywebview.api.block_device_permission(selectedDeviceId,true); if(!r||r.ok===false){status(r&&r.error?r.error:"Could not block device.",true);return;} status("Device blocked."); refreshDevicePermissionsPanel();};
    window.unblockSelectedDevice=async function(){ if(!selectedDeviceId){alert("Select a device first.");return;} const r=await window.pywebview.api.block_device_permission(selectedDeviceId,false); if(!r||r.ok===false){status(r&&r.error?r.error:"Could not unblock device.",true);return;} status("Device unblocked as monitor_only. Apply Worker role if needed."); refreshDevicePermissionsPanel();};
    document.addEventListener("DOMContentLoaded",()=>setTimeout(()=>{const pc=document.getElementById("pc-control-section"); if(pc&&pc.style.display!=="none"){ensurePanel(); refreshDevicePermissionsPanel();}},2200));
    setInterval(()=>{const pc=document.getElementById("pc-control-section"); if(pc&&pc.style.display!=="none") ensurePanel();},10000);
})();

// =====================================================
// SECURITY AUDIT LOG + EVENTS PANEL
// =====================================================

(function () {
    const PANEL_ID = "security-audit-panel";

    function esc(value) {
        return String(value === undefined || value === null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function short(value, max = 90) {
        value = String(value || "");
        return value.length > max ? value.slice(0, max) + "..." : value;
    }

    function statusLine(message, bad = false) {
        const el = document.getElementById("security-audit-status");
        if (!el) return;
        el.textContent = message || "";
        el.className = bad ? "security-audit-status bad" : "security-audit-status";
    }

    function eventClass(status) {
        status = String(status || "").toLowerCase();
        if (status === "allowed") return "security-event-ok";
        if (status === "denied") return "security-event-bad";
        if (status === "error") return "security-event-warn";
        return "security-event-muted";
    }

    function ensurePanel() {
        if (document.getElementById(PANEL_ID)) return true;

        const pc = document.getElementById("pc-control-section");
        if (!pc) return false;

        const panel = document.createElement("div");
        panel.id = PANEL_ID;
        panel.className = "security-audit-panel";
        panel.innerHTML = `
            <div class="security-audit-header">
                <div>
                    <h3>Permission Audit Log + Security Events</h3>
                    <div class="security-audit-subtitle">
                        Shows blocked attempts, permission denials, device role changes, and sensitive actions.
                    </div>
                </div>
                <div class="security-audit-controls">
                    <select id="security-audit-status-filter" class="security-audit-select">
                        <option value="">All Status</option>
                        <option value="allowed">Allowed</option>
                        <option value="denied">Denied</option>
                        <option value="error">Error</option>
                    </select>

                    <select id="security-audit-type-filter" class="security-audit-select">
                        <option value="">All Events</option>
                        <option value="permission_denied">Permission Denied</option>
                        <option value="permission_change">Permission Change</option>
                        <option value="mobile_task">Mobile Task</option>
                        <option value="profile_acquire">Profile Acquire</option>
                        <option value="profile_release">Profile Release</option>
                        <option value="sync_action">Sync Action</option>
                        <option value="block_action">Block Action</option>
                        <option value="server_error">Server Error</option>
                    </select>

                    <input id="security-audit-pc-filter" class="security-audit-input" placeholder="Device ID filter">

                    <button class="btn btn-primary" onclick="refreshSecurityAuditPanel()">REFRESH EVENTS</button>
                    <button class="btn btn-warning" onclick="clearSecurityAuditLog()">CLEAR LOG</button>
                </div>
            </div>

            <div id="security-audit-status" class="security-audit-status">
                Waiting for security events...
            </div>

            <div class="security-audit-table-wrap">
                <table class="ghost-table security-audit-table">
                    <thead>
                        <tr>
                            <th>Time</th>
                            <th>Status</th>
                            <th>Event</th>
                            <th>Device</th>
                            <th>Role</th>
                            <th>IP</th>
                            <th>Method</th>
                            <th>Path</th>
                            <th>Code</th>
                        </tr>
                    </thead>
                    <tbody id="security-audit-body">
                        <tr><td colspan="9">No security events loaded.</td></tr>
                    </tbody>
                </table>
            </div>
        `;

        pc.appendChild(panel);
        return true;
    }

    function renderEvents(data) {
        const body = document.getElementById("security-audit-body");
        if (!body) return;

        const events = Array.isArray(data.events) ? data.events : [];

        if (!events.length) {
            body.innerHTML = `<tr><td colspan="9">No security events found.</td></tr>`;
            return;
        }

        body.innerHTML = "";

        events.forEach(ev => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${esc(ev.time_text || ev.time || "—")}</td>
                <td><span class="security-event-pill ${eventClass(ev.status)}">${esc(ev.status || "—")}</span></td>
                <td>${esc(ev.event_type || "—")}</td>
                <td>${esc(ev.pc_id || "UNKNOWN")}</td>
                <td>${esc(ev.role || "unknown")}</td>
                <td>${esc(ev.remote_addr || "—")}</td>
                <td>${esc(ev.method || "—")}</td>
                <td title="${esc(ev.path || "")}">${esc(short(ev.path || "—", 100))}</td>
                <td>${esc(ev.status_code || "—")}</td>
            `;
            body.appendChild(tr);
        });
    }

    window.refreshSecurityAuditPanel = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_security_events !== "function") {
            statusLine("Backend bridge missing: get_security_events", true);
            return;
        }

        const typeEl = document.getElementById("security-audit-type-filter");
        const statusEl = document.getElementById("security-audit-status-filter");
        const pcEl = document.getElementById("security-audit-pc-filter");

        const eventType = typeEl ? typeEl.value : "";
        const eventStatus = statusEl ? statusEl.value : "";
        const pcId = pcEl ? pcEl.value : "";

        try {
            statusLine("Loading security events...");

            const data = await window.pywebview.api.get_security_events(250, eventType, pcId, eventStatus);

            if (!data || data.ok === false) {
                statusLine(data && data.error ? data.error : "Could not load security events.", true);
                renderEvents({ events: [] });
                return;
            }

            renderEvents(data);
            statusLine(`Loaded ${data.count || (data.events || []).length || 0} security event(s).`);

        } catch (err) {
            statusLine(String(err), true);
        }
    };

    window.clearSecurityAuditLog = async function () {
        if (!confirm("Clear the security audit log?")) return;

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.clear_security_events !== "function") {
            statusLine("Backend bridge missing: clear_security_events", true);
            return;
        }

        try {
            const result = await window.pywebview.api.clear_security_events();

            if (!result || result.ok === false) {
                statusLine(result && result.error ? result.error : "Could not clear security events.", true);
                return;
            }

            statusLine("Security audit log cleared.");
            refreshSecurityAuditPanel();

        } catch (err) {
            statusLine(String(err), true);
        }
    };

    document.addEventListener("DOMContentLoaded", function () {
        setTimeout(function () {
            const pc = document.getElementById("pc-control-section");
            if (pc && pc.style.display !== "none") {
                ensurePanel();
                refreshSecurityAuditPanel();
            }
        }, 2600);
    });

    setInterval(function () {
        const pc = document.getElementById("pc-control-section");
        if (pc && pc.style.display !== "none") ensurePanel();
    }, 10000);
})();

// =====================================================
// MAIN PC ↔ LAPTOP COMMAND CENTER PANEL
// =====================================================

(function () {
    const PANEL_ID = "command-center-panel";

    function esc(value) {
        return String(value === undefined || value === null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function short(value, max = 120) {
        value = String(value || "");
        return value.length > max ? value.slice(0, max) + "..." : value;
    }

    function statusLine(message, bad = false) {
        const el = document.getElementById("command-center-status");
        if (!el) return;
        el.textContent = message || "";
        el.className = bad ? "command-center-status bad" : "command-center-status";
    }

    function ensurePanel() {
        if (document.getElementById(PANEL_ID)) return true;

        const pc = document.getElementById("pc-control-section");
        if (!pc) return false;

        const panel = document.createElement("div");
        panel.id = PANEL_ID;
        panel.className = "command-center-panel";
        panel.innerHTML = `
            <div class="command-center-header">
                <div>
                    <h3>Main PC ↔ Laptop Command Center</h3>
                    <div class="command-center-subtitle">
                        Send safe commands to laptops/workers that are running device_command_worker.py.
                    </div>
                </div>
                <div class="command-center-controls">
                    <input id="command-target-pc" class="command-center-input" placeholder="Target Device ID / PC_ID">
                    <select id="command-type-select" class="command-center-select">
                        <option value="PING">Ping Device</option>
                        <option value="STATUS_REPORT">Status Report</option>
                        <option value="START_DASHBOARD">Start Dashboard</option>
                        <option value="START_MOBILE_WORKER">Start Mobile Worker</option>
                        <option value="START_SYNC">Start Sync</option>
                        <option value="MARK_AVAILABLE">Mark Available</option>
                        <option value="MARK_UNAVAILABLE">Mark Unavailable</option>
                        <option value="STOP_COMMAND_WORKER">Stop Command Worker</option>
                    </select>
                    <button class="btn btn-primary" onclick="sendDeviceCommandFromPanel()">SEND COMMAND</button>
                    <button class="btn btn-primary" onclick="refreshCommandCenterPanel()">REFRESH COMMANDS</button>
                </div>
            </div>

            <div id="command-center-status" class="command-center-status">
                Waiting for commands...
            </div>

            <div class="command-center-help">
                Tip: the target must match the worker PC_ID shown in Device Groups + Permissions or worker logs.
            </div>

            <div class="command-center-table-wrap">
                <table class="ghost-table command-center-table">
                    <thead>
                        <tr>
                            <th>Created</th>
                            <th>Target</th>
                            <th>Command</th>
                            <th>Status</th>
                            <th>Created By</th>
                            <th>Claimed</th>
                            <th>Completed</th>
                            <th>Result</th>
                            <th>Error</th>
                        </tr>
                    </thead>
                    <tbody id="command-center-body">
                        <tr><td colspan="9">No commands loaded.</td></tr>
                    </tbody>
                </table>
            </div>
        `;

        pc.appendChild(panel);
        return true;
    }

    function renderCommands(data) {
        const body = document.getElementById("command-center-body");
        if (!body) return;

        const commands = Array.isArray(data.commands) ? data.commands : [];

        if (!commands.length) {
            body.innerHTML = `<tr><td colspan="9">No commands found.</td></tr>`;
            return;
        }

        body.innerHTML = "";

        commands.forEach(cmd => {
            const result = cmd.result ? JSON.stringify(cmd.result) : "";
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${esc(cmd.created_at || "—")}</td>
                <td>${esc(cmd.target_pc_id || "—")}</td>
                <td>${esc(cmd.command_type || "—")}</td>
                <td><span class="command-status-pill">${esc(cmd.status || "—")}</span></td>
                <td>${esc(cmd.created_by || "—")}</td>
                <td>${esc(cmd.claimed_at || "—")}</td>
                <td>${esc(cmd.completed_at || "—")}</td>
                <td title="${esc(result)}">${esc(short(result || "—", 160))}</td>
                <td title="${esc(cmd.error || "")}">${esc(short(cmd.error || "—", 100))}</td>
            `;
            body.appendChild(tr);
        });
    }

    window.refreshCommandCenterPanel = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_device_commands !== "function") {
            statusLine("Backend bridge missing: get_device_commands", true);
            return;
        }

        try {
            statusLine("Loading command list...");
            const data = await window.pywebview.api.get_device_commands("", "", 150);

            if (!data || data.ok === false) {
                statusLine(data && data.error ? data.error : "Could not load commands.", true);
                renderCommands({ commands: [] });
                return;
            }

            renderCommands(data);
            statusLine(`Loaded ${data.count || (data.commands || []).length || 0} command(s).`);

        } catch (err) {
            statusLine(String(err), true);
        }
    };

    window.sendDeviceCommandFromPanel = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.create_device_command !== "function") {
            statusLine("Backend bridge missing: create_device_command", true);
            return;
        }

        const targetEl = document.getElementById("command-target-pc");
        const typeEl = document.getElementById("command-type-select");

        const target = targetEl ? targetEl.value.trim() : "";
        const commandType = typeEl ? typeEl.value : "PING";

        if (!target) {
            alert("Enter a target Device ID / PC_ID first.");
            return;
        }

        try {
            statusLine(`Sending ${commandType} to ${target}...`);

            const result = await window.pywebview.api.create_device_command(target, commandType, {});

            if (!result || result.ok === false) {
                statusLine(result && result.error ? result.error : "Could not send command.", true);
                return;
            }

            statusLine(`Command sent: ${commandType} → ${target}`);
            setTimeout(window.refreshCommandCenterPanel, 500);

        } catch (err) {
            statusLine(String(err), true);
        }
    };

    document.addEventListener("DOMContentLoaded", function () {
        setTimeout(function () {
            const pc = document.getElementById("pc-control-section");
            if (pc && pc.style.display !== "none") {
                ensurePanel();
                refreshCommandCenterPanel();
            }
        }, 3000);
    });

    setInterval(function () {
        const pc = document.getElementById("pc-control-section");
        if (pc && pc.style.display !== "none") ensurePanel();
    }, 10000);
})();

// =====================================================
// COMMAND CENTER DEVICE DROPDOWN
// Adds a device dropdown so PC_ID is selected instead of typed.
// =====================================================

(function () {
    const DROPDOWN_ID = "command-center-device-dropdown";
    const LOAD_BUTTON_ID = "command-center-load-devices-btn";

    function esc(value) {
        return String(value === undefined || value === null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function setCommandCenterStatus(message, bad = false) {
        const el = document.getElementById("command-center-status");
        if (!el) return;
        el.textContent = message || "";
        el.className = bad ? "command-center-status bad" : "command-center-status";
    }

    function normalizeWorkerId(worker, index) {
        return String(
            worker.pc_id ||
            worker.id ||
            worker.device_id ||
            worker.worker_id ||
            worker.name ||
            ""
        ).trim();
    }

    function buildDeviceRows(data) {
        const rows = [];
        const seen = new Set();

        const devices = data && data.devices ? data.devices : {};
        const workers = Array.isArray(data && data.workers) ? data.workers : [];

        workers.forEach((worker, index) => {
            const pcId = normalizeWorkerId(worker, index);
            if (!pcId || seen.has(pcId)) return;

            const permission = devices[pcId] || {};
            const role = permission.role || worker.role || worker.device_type || worker.type || "worker";
            const state = worker.status || worker.state || worker.online || "";
            const label = `${pcId}  |  ${role}${state ? "  |  " + state : ""}`;

            rows.push({
                pc_id: pcId,
                label,
                role,
                source: "worker"
            });

            seen.add(pcId);
        });

        Object.keys(devices).sort().forEach(pcId => {
            if (!pcId || seen.has(pcId)) return;

            const permission = devices[pcId] || {};
            const role = permission.role || "monitor_only";
            const blocked = permission.is_blocked ? " | BLOCKED" : "";
            const label = `${pcId}  |  ${role}${blocked}`;

            rows.push({
                pc_id: pcId,
                label,
                role,
                source: "permission"
            });

            seen.add(pcId);
        });

        return rows;
    }

    function ensureDeviceDropdown() {
        const targetInput = document.getElementById("command-target-pc");
        if (!targetInput) return false;

        if (document.getElementById(DROPDOWN_ID)) return true;

        const select = document.createElement("select");
        select.id = DROPDOWN_ID;
        select.className = "command-center-select command-center-device-dropdown";
        select.innerHTML = `<option value="">Select Device ID</option>`;

        select.addEventListener("change", function () {
            const value = this.value || "";
            if (value) {
                targetInput.value = value;
                setCommandCenterStatus(`Selected target device: ${value}`);
            }
        });

        const loadButton = document.createElement("button");
        loadButton.id = LOAD_BUTTON_ID;
        loadButton.className = "btn btn-primary";
        loadButton.textContent = "LOAD DEVICES";
        loadButton.onclick = window.loadCommandCenterDeviceDropdown;

        const controls = targetInput.parentElement;
        controls.insertBefore(select, targetInput);
        controls.insertBefore(loadButton, targetInput);

        return true;
    }

    window.loadCommandCenterDeviceDropdown = async function () {
        ensureDeviceDropdown();

        const select = document.getElementById(DROPDOWN_ID);
        const targetInput = document.getElementById("command-target-pc");

        if (!select || !targetInput) {
            return;
        }

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_device_permissions !== "function") {
            setCommandCenterStatus("Backend bridge missing: get_device_permissions", true);
            return;
        }

        try {
            setCommandCenterStatus("Loading devices for dropdown...");

            const data = await window.pywebview.api.get_device_permissions();

            if (!data || data.ok === false) {
                setCommandCenterStatus(data && data.error ? data.error : "Could not load device list.", true);
                return;
            }

            const rows = buildDeviceRows(data);

            select.innerHTML = `<option value="">Select Device ID</option>`;

            if (!rows.length) {
                select.innerHTML += `<option value="">No devices found</option>`;
                setCommandCenterStatus("No devices found. Start workers first.", true);
                return;
            }

            rows.forEach(row => {
                const option = document.createElement("option");
                option.value = row.pc_id;
                option.textContent = row.label;
                select.appendChild(option);
            });

            // Auto-select exact existing target if it exists in dropdown.
            const currentTarget = String(targetInput.value || "").trim();
            if (currentTarget && rows.some(row => row.pc_id === currentTarget)) {
                select.value = currentTarget;
            }

            setCommandCenterStatus(`Loaded ${rows.length} device(s). Select one, then send command.`);

        } catch (err) {
            setCommandCenterStatus(String(err), true);
        }
    };

    // Wrap send command to reject bad copied labels like "PC_ID=LAPTOP DEVICE_TYPE".
    const originalSendDeviceCommand = window.sendDeviceCommandFromPanel;

    window.sendDeviceCommandFromPanel = async function () {
        const targetInput = document.getElementById("command-target-pc");

        if (targetInput) {
            let target = String(targetInput.value || "").trim();

            if (target.includes("PC_ID=")) {
                const match = target.match(/PC_ID\s*=\s*([^\s]+)/i);
                if (match && match[1]) {
                    target = match[1].trim();
                    targetInput.value = target;
                    setCommandCenterStatus(`Cleaned target PC_ID to: ${target}`);
                }
            }

            if (target.includes("DEVICE_TYPE")) {
                target = target.replace(/DEVICE_TYPE.*/i, "").trim();
                targetInput.value = target;
            }
        }

        if (typeof originalSendDeviceCommand === "function") {
            return originalSendDeviceCommand();
        }

        setCommandCenterStatus("Original send command function is missing.", true);
    };

    function setupWhenVisible() {
        const pc = document.getElementById("pc-control-section");

        if (!pc || pc.style.display === "none") {
            return;
        }

        const ok = ensureDeviceDropdown();

        if (ok) {
            const select = document.getElementById(DROPDOWN_ID);
            if (select && select.options.length <= 1) {
                window.loadCommandCenterDeviceDropdown();
            }
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        setTimeout(setupWhenVisible, 3500);
    });

    setInterval(setupWhenVisible, 6000);
})();

// =====================================================
// ML RELIABILITY + ANOMALY DETECTION PANEL v1
// Safe dashboard panel. It reads coordinator ML routes only.
// =====================================================

(function () {
    const PANEL_ID = "ml-reliability-panel-v1";

    function esc(value) {
        return String(value === undefined || value === null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function short(value, max = 140) {
        value = String(value || "");
        return value.length > max ? value.slice(0, max) + "..." : value;
    }

    function setMlStatus(message, bad = false) {
        const el = document.getElementById("ml-reliability-status-v1");
        if (!el) return;
        el.textContent = message || "";
        el.className = bad ? "ml-reliability-status bad" : "ml-reliability-status";
    }

    function riskClass(value) {
        value = String(value || "").toLowerCase();
        if (value.includes("critical")) return "critical";
        if (value.includes("high")) return "high";
        if (value.includes("medium") || value.includes("watch")) return "medium";
        if (value.includes("low") || value.includes("ok")) return "low";
        return "unknown";
    }

    function ensurePanel() {
        if (document.getElementById(PANEL_ID)) return true;

        const pc = document.getElementById("pc-control-section");
        if (!pc) return false;

        const panel = document.createElement("div");
        panel.id = PANEL_ID;
        panel.className = "ml-reliability-panel";
        panel.innerHTML = `
            <div class="ml-reliability-header">
                <div>
                    <h3>ML Reliability + Anomaly Detection v1</h3>
                    <div class="ml-reliability-subtitle">
                        Safe read-only sidecar. Scores devices, detects anomalies, predicts command risk, and recommends fixes.
                    </div>
                </div>
                <div class="ml-reliability-controls">
                    <button class="btn btn-primary" onclick="refreshMlReliabilityPanel()">REFRESH ML</button>
                    <button class="btn btn-primary" onclick="predictSelectedDeviceCommand()">PREDICT COMMAND</button>
                    <button class="btn btn-primary" onclick="clearMlEventsFromPanel()">CLEAR ML EVENTS</button>
                </div>
            </div>

            <div id="ml-reliability-status-v1" class="ml-reliability-status">
                Waiting for ML engine...
            </div>

            <div class="ml-summary-grid">
                <div class="ml-summary-card">
                    <div class="ml-summary-label">Overall</div>
                    <div id="ml-overall-value" class="ml-summary-value">—</div>
                </div>
                <div class="ml-summary-card">
                    <div class="ml-summary-label">Devices</div>
                    <div id="ml-devices-value" class="ml-summary-value">—</div>
                </div>
                <div class="ml-summary-card">
                    <div class="ml-summary-label">Anomalies</div>
                    <div id="ml-anomalies-value" class="ml-summary-value">—</div>
                </div>
                <div class="ml-summary-card">
                    <div class="ml-summary-label">Command Prediction</div>
                    <div id="ml-prediction-value" class="ml-summary-value">—</div>
                </div>
            </div>

            <div class="ml-section-title">Device Reliability Scores</div>
            <div class="ml-table-wrap">
                <table class="ghost-table ml-table">
                    <thead>
                        <tr>
                            <th>Device</th>
                            <th>Role</th>
                            <th>Score</th>
                            <th>Risk</th>
                            <th>Prediction</th>
                            <th>Completed</th>
                            <th>Failed</th>
                            <th>Pending</th>
                        </tr>
                    </thead>
                    <tbody id="ml-device-score-body">
                        <tr><td colspan="8">No device scores loaded.</td></tr>
                    </tbody>
                </table>
            </div>

            <div class="ml-section-title">Anomaly Alerts + Recommended Fixes</div>
            <div class="ml-table-wrap">
                <table class="ghost-table ml-table">
                    <thead>
                        <tr>
                            <th>Severity</th>
                            <th>Kind</th>
                            <th>Message</th>
                            <th>Recommended Fix</th>
                            <th>Confidence</th>
                        </tr>
                    </thead>
                    <tbody id="ml-anomaly-body">
                        <tr><td colspan="5">No anomalies loaded.</td></tr>
                    </tbody>
                </table>
            </div>

            <div class="ml-section-title">Recent ML Events</div>
            <div class="ml-table-wrap">
                <table class="ghost-table ml-table">
                    <thead>
                        <tr>
                            <th>Time</th>
                            <th>Severity</th>
                            <th>Type</th>
                            <th>Message</th>
                            <th>Recommendation</th>
                        </tr>
                    </thead>
                    <tbody id="ml-events-body">
                        <tr><td colspan="5">No ML events loaded.</td></tr>
                    </tbody>
                </table>
            </div>
        `;

        pc.appendChild(panel);
        return true;
    }

    function renderStatus(data) {
        const overall = data.overall || "unknown";
        const counts = data.counts || {};
        const overallEl = document.getElementById("ml-overall-value");
        const devicesEl = document.getElementById("ml-devices-value");
        const anomaliesEl = document.getElementById("ml-anomalies-value");

        if (overallEl) {
            overallEl.textContent = overall.toUpperCase();
            overallEl.className = "ml-summary-value " + riskClass(overall);
        }

        if (devicesEl) devicesEl.textContent = String(counts.devices || (data.device_scores || []).length || 0);
        if (anomaliesEl) anomaliesEl.textContent = String(counts.anomalies || (data.anomalies || []).length || 0);
    }

    function renderScores(scores) {
        const body = document.getElementById("ml-device-score-body");
        if (!body) return;

        scores = Array.isArray(scores) ? scores : [];

        if (!scores.length) {
            body.innerHTML = `<tr><td colspan="8">No device scores found yet. Send PING/STATUS_REPORT to build history.</td></tr>`;
            return;
        }

        body.innerHTML = "";

        scores.forEach(row => {
            const risk = row.risk || "unknown";
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${esc(row.pc_id || "—")}</td>
                <td>${esc(row.role || "—")}</td>
                <td><strong>${esc(row.score)}%</strong></td>
                <td><span class="ml-risk-pill ${riskClass(risk)}">${esc(risk)}</span></td>
                <td>${esc(row.success_prediction_percent || "—")}%</td>
                <td>${esc(row.commands_completed || 0)}</td>
                <td>${esc(row.commands_failed || 0)}</td>
                <td>${esc(row.commands_pending || 0)}</td>
            `;
            body.appendChild(tr);
        });
    }

    function renderAnomalies(anomalies) {
        const body = document.getElementById("ml-anomaly-body");
        if (!body) return;

        anomalies = Array.isArray(anomalies) ? anomalies : [];

        if (!anomalies.length) {
            body.innerHTML = `<tr><td colspan="5">No anomalies detected.</td></tr>`;
            return;
        }

        body.innerHTML = "";

        anomalies.forEach(row => {
            const severity = row.severity || "unknown";
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td><span class="ml-risk-pill ${riskClass(severity)}">${esc(severity)}</span></td>
                <td>${esc(row.kind || "—")}</td>
                <td title="${esc(row.message || "")}">${esc(short(row.message || "—", 160))}</td>
                <td title="${esc(row.recommendation || "")}">${esc(short(row.recommendation || "—", 200))}</td>
                <td>${esc(row.confidence || "—")}%</td>
            `;
            body.appendChild(tr);
        });
    }

    function renderEvents(events) {
        const body = document.getElementById("ml-events-body");
        if (!body) return;

        events = Array.isArray(events) ? events : [];

        if (!events.length) {
            body.innerHTML = `<tr><td colspan="5">No ML events found.</td></tr>`;
            return;
        }

        body.innerHTML = "";

        events.slice(0, 150).forEach(row => {
            const severity = row.severity || "info";
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${esc(row.created_at || "—")}</td>
                <td><span class="ml-risk-pill ${riskClass(severity)}">${esc(severity)}</span></td>
                <td>${esc(row.event_type || row.kind || "—")}</td>
                <td title="${esc(row.message || "")}">${esc(short(row.message || "—", 180))}</td>
                <td title="${esc(row.recommendation || "")}">${esc(short(row.recommendation || "—", 220))}</td>
            `;
            body.appendChild(tr);
        });
    }

    window.refreshMlReliabilityPanel = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_ml_status !== "function") {
            setMlStatus("Backend bridge missing: get_ml_status", true);
            return;
        }

        try {
            setMlStatus("Running ML reliability analysis...");

            const data = await window.pywebview.api.get_ml_status();

            if (!data || data.ok === false) {
                setMlStatus(data && data.error ? data.error : "ML status failed.", true);
                return;
            }

            renderStatus(data);
            renderScores(data.device_scores || []);
            renderAnomalies(data.anomalies || []);

            if (window.pywebview.api.get_ml_events) {
                const events = await window.pywebview.api.get_ml_events(200);
                if (events && events.ok !== false) renderEvents(events.events || []);
            }

            setMlStatus(`ML analysis complete. Overall: ${(data.overall || "unknown").toUpperCase()}`);

        } catch (err) {
            setMlStatus(String(err), true);
        }
    };

    window.predictSelectedDeviceCommand = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.predict_device_command_success !== "function") {
            setMlStatus("Backend bridge missing: predict_device_command_success", true);
            return;
        }

        const targetEl = document.getElementById("command-target-pc");
        const commandEl = document.getElementById("command-type-select");

        const target = targetEl ? String(targetEl.value || "").trim() : "";
        const commandType = commandEl ? String(commandEl.value || "").trim() : "";

        if (!target) {
            alert("Select or enter a Command Center target device first.");
            return;
        }

        try {
            setMlStatus(`Predicting command success for ${target}...`);

            const data = await window.pywebview.api.predict_device_command_success(target, commandType);

            if (!data || data.ok === false) {
                setMlStatus(data && data.error ? data.error : "Prediction failed.", true);
                return;
            }

            const predEl = document.getElementById("ml-prediction-value");
            if (predEl) {
                predEl.textContent = `${data.prediction_percent}%`;
                predEl.className = "ml-summary-value " + riskClass(data.risk);
            }

            setMlStatus(`${commandType || "COMMAND"} → ${target}: ${data.prediction_percent}% likely. ${data.recommendation || ""}`);

        } catch (err) {
            setMlStatus(String(err), true);
        }
    };

    window.clearMlEventsFromPanel = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.clear_ml_events !== "function") {
            setMlStatus("Backend bridge missing: clear_ml_events", true);
            return;
        }

        if (!confirm("Clear ML events only? This does not clear security events or command history.")) {
            return;
        }

        try {
            const data = await window.pywebview.api.clear_ml_events();

            if (!data || data.ok === false) {
                setMlStatus(data && data.error ? data.error : "Clear ML events failed.", true);
                return;
            }

            setMlStatus("ML events cleared.");
            setTimeout(window.refreshMlReliabilityPanel, 400);

        } catch (err) {
            setMlStatus(String(err), true);
        }
    };

    function setupMlPanelWhenVisible() {
        const pc = document.getElementById("pc-control-section");

        if (!pc || pc.style.display === "none") {
            return;
        }

        if (ensurePanel()) {
            const statusEl = document.getElementById("ml-reliability-status-v1");
            if (statusEl && statusEl.textContent.includes("Waiting")) {
                window.refreshMlReliabilityPanel();
            }
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        setTimeout(setupMlPanelWhenVisible, 4000);
    });

    setInterval(setupMlPanelWhenVisible, 10000);
})();

// =====================================================
// ML HISTORY + TREND LEARNING PANEL v1
// Safe panel for historical ML snapshots and trend analysis.
// =====================================================

(function () {
    const PANEL_ID = "ml-history-trends-panel-v1";

    function esc(value) {
        return String(value === undefined || value === null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function short(value, max = 160) {
        value = String(value || "");
        return value.length > max ? value.slice(0, max) + "..." : value;
    }

    function riskClass(value) {
        value = String(value || "").toLowerCase();
        if (value.includes("critical")) return "critical";
        if (value.includes("high")) return "high";
        if (value.includes("medium") || value.includes("watch") || value.includes("learning")) return "medium";
        if (value.includes("low") || value.includes("ok") || value.includes("stable")) return "low";
        return "unknown";
    }

    function setHistoryStatus(message, bad = false) {
        const el = document.getElementById("ml-history-status-v1");
        if (!el) return;
        el.textContent = message || "";
        el.className = bad ? "ml-history-status bad" : "ml-history-status";
    }

    function ensurePanel() {
        if (document.getElementById(PANEL_ID)) return true;

        const pc = document.getElementById("pc-control-section");
        if (!pc) return false;

        const panel = document.createElement("div");
        panel.id = PANEL_ID;
        panel.className = "ml-history-panel";
        panel.innerHTML = `
            <div class="ml-history-header">
                <div>
                    <h3>ML History + Trend Learning v1</h3>
                    <div class="ml-history-subtitle">
                        Tracks ML snapshots over time so the system can learn reliability trends safely.
                    </div>
                </div>
                <div class="ml-history-controls">
                    <button class="btn btn-primary" onclick="createMlHistorySnapshotFromPanel()">CREATE SNAPSHOT</button>
                    <button class="btn btn-primary" onclick="refreshMlHistoryTrendsPanel()">REFRESH TRENDS</button>
                    <button class="btn btn-primary" onclick="clearMlHistoryFromPanel()">CLEAR HISTORY</button>
                </div>
            </div>

            <div id="ml-history-status-v1" class="ml-history-status">
                Waiting for ML history...
            </div>

            <div class="ml-history-summary-grid">
                <div class="ml-history-summary-card">
                    <div class="ml-history-summary-label">Trend Overall</div>
                    <div id="ml-history-overall-value" class="ml-history-summary-value">—</div>
                </div>
                <div class="ml-history-summary-card">
                    <div class="ml-history-summary-label">Snapshots</div>
                    <div id="ml-history-samples-value" class="ml-history-summary-value">—</div>
                </div>
                <div class="ml-history-summary-card">
                    <div class="ml-history-summary-label">Tracked Devices</div>
                    <div id="ml-history-devices-value" class="ml-history-summary-value">—</div>
                </div>
                <div class="ml-history-summary-card">
                    <div class="ml-history-summary-label">Top Anomaly</div>
                    <div id="ml-history-top-anomaly-value" class="ml-history-summary-value small">—</div>
                </div>
            </div>

            <div class="ml-history-section-title">Device Trend Learning</div>
            <div class="ml-history-table-wrap">
                <table class="ghost-table ml-history-table">
                    <thead>
                        <tr>
                            <th>Device</th>
                            <th>Samples</th>
                            <th>Latest Score</th>
                            <th>Avg Score</th>
                            <th>Recent Δ</th>
                            <th>Total Δ</th>
                            <th>Direction</th>
                            <th>Risk</th>
                            <th>Prediction</th>
                        </tr>
                    </thead>
                    <tbody id="ml-history-device-body">
                        <tr><td colspan="9">No trend data loaded.</td></tr>
                    </tbody>
                </table>
            </div>

            <div class="ml-history-section-title">Trend Recommendations</div>
            <div class="ml-history-table-wrap">
                <table class="ghost-table ml-history-table">
                    <thead>
                        <tr>
                            <th>Severity</th>
                            <th>Message</th>
                            <th>Recommended Fix</th>
                            <th>Confidence</th>
                        </tr>
                    </thead>
                    <tbody id="ml-history-recommendation-body">
                        <tr><td colspan="4">No recommendations loaded.</td></tr>
                    </tbody>
                </table>
            </div>

            <div class="ml-history-section-title">Anomaly Frequency</div>
            <div class="ml-history-table-wrap">
                <table class="ghost-table ml-history-table">
                    <thead>
                        <tr>
                            <th>Anomaly Type</th>
                            <th>Count</th>
                        </tr>
                    </thead>
                    <tbody id="ml-history-anomaly-body">
                        <tr><td colspan="2">No anomaly frequency loaded.</td></tr>
                    </tbody>
                </table>
            </div>
        `;

        pc.appendChild(panel);
        return true;
    }

    function renderTrends(data) {
        const overall = data.overall || "unknown";
        const trends = Array.isArray(data.device_trends) ? data.device_trends : [];
        const anomalies = Array.isArray(data.anomaly_trends) ? data.anomaly_trends : [];
        const recommendations = Array.isArray(data.recommendations) ? data.recommendations : [];

        const overallEl = document.getElementById("ml-history-overall-value");
        const sampleEl = document.getElementById("ml-history-samples-value");
        const devicesEl = document.getElementById("ml-history-devices-value");
        const topEl = document.getElementById("ml-history-top-anomaly-value");

        if (overallEl) {
            overallEl.textContent = overall.toUpperCase();
            overallEl.className = "ml-history-summary-value " + riskClass(overall);
        }

        if (sampleEl) sampleEl.textContent = String(data.sample_count || 0);
        if (devicesEl) devicesEl.textContent = String(trends.length);
        if (topEl) topEl.textContent = anomalies.length ? short(anomalies[0].kind || "—", 22) : "—";

        const deviceBody = document.getElementById("ml-history-device-body");
        if (deviceBody) {
            if (!trends.length) {
                deviceBody.innerHTML = `<tr><td colspan="9">No device trend data yet. Create snapshots first.</td></tr>`;
            } else {
                deviceBody.innerHTML = "";

                trends.forEach(row => {
                    const tr = document.createElement("tr");
                    tr.innerHTML = `
                        <td>${esc(row.pc_id || "—")}</td>
                        <td>${esc(row.samples || 0)}</td>
                        <td><strong>${esc(row.latest_score || "—")}%</strong></td>
                        <td>${esc(row.average_score || "—")}%</td>
                        <td>${esc(row.delta_recent || 0)}</td>
                        <td>${esc(row.delta_total || 0)}</td>
                        <td>${esc(row.direction || "—")}</td>
                        <td><span class="ml-history-risk-pill ${riskClass(row.risk)}">${esc(row.risk || "—")}</span></td>
                        <td>${esc(row.latest_prediction || "—")}%</td>
                    `;
                    deviceBody.appendChild(tr);
                });
            }
        }

        const recBody = document.getElementById("ml-history-recommendation-body");
        if (recBody) {
            if (!recommendations.length) {
                recBody.innerHTML = `<tr><td colspan="4">No recommendations.</td></tr>`;
            } else {
                recBody.innerHTML = "";

                recommendations.forEach(row => {
                    const severity = row.severity || "info";
                    const tr = document.createElement("tr");
                    tr.innerHTML = `
                        <td><span class="ml-history-risk-pill ${riskClass(severity)}">${esc(severity)}</span></td>
                        <td title="${esc(row.message || "")}">${esc(short(row.message || "—", 180))}</td>
                        <td title="${esc(row.recommendation || "")}">${esc(short(row.recommendation || "—", 220))}</td>
                        <td>${esc(row.confidence || "—")}%</td>
                    `;
                    recBody.appendChild(tr);
                });
            }
        }

        const anomalyBody = document.getElementById("ml-history-anomaly-body");
        if (anomalyBody) {
            if (!anomalies.length) {
                anomalyBody.innerHTML = `<tr><td colspan="2">No anomaly frequency yet.</td></tr>`;
            } else {
                anomalyBody.innerHTML = "";

                anomalies.forEach(row => {
                    const tr = document.createElement("tr");
                    tr.innerHTML = `
                        <td>${esc(row.kind || "—")}</td>
                        <td>${esc(row.count || 0)}</td>
                    `;
                    anomalyBody.appendChild(tr);
                });
            }
        }
    }

    window.refreshMlHistoryTrendsPanel = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_ml_trends !== "function") {
            setHistoryStatus("Backend bridge missing: get_ml_trends", true);
            return;
        }

        try {
            setHistoryStatus("Loading ML trends...");

            const data = await window.pywebview.api.get_ml_trends(500);

            if (!data || data.ok === false) {
                setHistoryStatus(data && data.error ? data.error : "Could not load ML trends.", true);
                return;
            }

            renderTrends(data);
            setHistoryStatus(`Trend analysis loaded. Overall: ${(data.overall || "unknown").toUpperCase()} | Snapshots: ${data.sample_count || 0}`);

        } catch (err) {
            setHistoryStatus(String(err), true);
        }
    };

    window.createMlHistorySnapshotFromPanel = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.create_ml_history_snapshot !== "function") {
            setHistoryStatus("Backend bridge missing: create_ml_history_snapshot", true);
            return;
        }

        try {
            setHistoryStatus("Creating ML history snapshot...");

            const data = await window.pywebview.api.create_ml_history_snapshot();

            if (!data || data.ok === false) {
                setHistoryStatus(data && data.error ? data.error : "Snapshot failed.", true);
                return;
            }

            setHistoryStatus("Snapshot created. Refreshing trends...");
            setTimeout(window.refreshMlHistoryTrendsPanel, 500);

        } catch (err) {
            setHistoryStatus(String(err), true);
        }
    };

    window.clearMlHistoryFromPanel = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.clear_ml_history !== "function") {
            setHistoryStatus("Backend bridge missing: clear_ml_history", true);
            return;
        }

        if (!confirm("Clear ML history snapshots? This only clears ml_history.jsonl, not command/security logs.")) {
            return;
        }

        try {
            const data = await window.pywebview.api.clear_ml_history();

            if (!data || data.ok === false) {
                setHistoryStatus(data && data.error ? data.error : "Clear history failed.", true);
                return;
            }

            setHistoryStatus("ML history cleared.");
            setTimeout(window.refreshMlHistoryTrendsPanel, 500);

        } catch (err) {
            setHistoryStatus(String(err), true);
        }
    };

    function setupPanelWhenVisible() {
        const pc = document.getElementById("pc-control-section");

        if (!pc || pc.style.display === "none") {
            return;
        }

        if (ensurePanel()) {
            const statusEl = document.getElementById("ml-history-status-v1");
            if (statusEl && statusEl.textContent.includes("Waiting")) {
                window.refreshMlHistoryTrendsPanel();
            }
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        setTimeout(setupPanelWhenVisible, 5000);
    });

    setInterval(setupPanelWhenVisible, 10000);
})();

// =====================================================
// ML AUTO-RECOMMENDATION ACTION QUEUE PANEL v1
// Safe approval-only queue. No automatic execution.
// =====================================================

(function () {
    const PANEL_ID = "ml-action-queue-panel-v1";
    let ML_ACTION_CACHE = [];

    function esc(value) {
        return String(value === undefined || value === null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function short(value, max = 160) {
        value = String(value || "");
        return value.length > max ? value.slice(0, max) + "..." : value;
    }

    function riskClass(value) {
        value = String(value || "").toLowerCase();
        if (value.includes("critical")) return "critical";
        if (value.includes("high")) return "high";
        if (value.includes("medium") || value.includes("recommended") || value.includes("approved")) return "medium";
        if (value.includes("low") || value.includes("completed") || value.includes("info")) return "low";
        if (value.includes("rejected") || value.includes("failed") || value.includes("cancelled")) return "critical";
        return "unknown";
    }

    function setActionStatus(message, bad = false) {
        const el = document.getElementById("ml-action-status-v1");
        if (!el) return;
        el.textContent = message || "";
        el.className = bad ? "ml-action-status bad" : "ml-action-status";
    }

    function ensurePanel() {
        if (document.getElementById(PANEL_ID)) return true;

        const pc = document.getElementById("pc-control-section");
        if (!pc) return false;

        const panel = document.createElement("div");
        panel.id = PANEL_ID;
        panel.className = "ml-action-panel";
        panel.innerHTML = `
            <div class="ml-action-header">
                <div>
                    <h3>ML Auto-Recommendation Action Queue v1</h3>
                    <div class="ml-action-subtitle">
                        ML creates recommended fixes. You approve/reject/complete manually. No automatic execution.
                    </div>
                </div>
                <div class="ml-action-controls">
                    <select id="ml-action-status-filter" class="ml-action-select">
                        <option value="">All Statuses</option>
                        <option value="recommended">Recommended</option>
                        <option value="approved">Approved</option>
                        <option value="completed">Completed</option>
                        <option value="rejected">Rejected</option>
                        <option value="failed">Failed</option>
                    </select>
                    <button class="btn btn-primary" onclick="generateMlActionsFromPanel()">GENERATE ACTIONS</button>
                    <button class="btn btn-primary" onclick="refreshMlActionsPanel()">REFRESH ACTIONS</button>
                    <button class="btn btn-primary" onclick="clearCompletedMlActionsFromPanel()">CLEAR DONE</button>
                </div>
            </div>

            <div id="ml-action-status-v1" class="ml-action-status">
                Waiting for ML action queue...
            </div>

            <div class="ml-action-summary-grid">
                <div class="ml-action-summary-card">
                    <div class="ml-action-summary-label">Total</div>
                    <div id="ml-action-total-value" class="ml-action-summary-value">—</div>
                </div>
                <div class="ml-action-summary-card">
                    <div class="ml-action-summary-label">Recommended</div>
                    <div id="ml-action-recommended-value" class="ml-action-summary-value">—</div>
                </div>
                <div class="ml-action-summary-card">
                    <div class="ml-action-summary-label">Approved</div>
                    <div id="ml-action-approved-value" class="ml-action-summary-value">—</div>
                </div>
                <div class="ml-action-summary-card">
                    <div class="ml-action-summary-label">Critical/High</div>
                    <div id="ml-action-risk-value" class="ml-action-summary-value">—</div>
                </div>
            </div>

            <div class="ml-action-table-wrap">
                <table class="ghost-table ml-action-table">
                    <thead>
                        <tr>
                            <th>Status</th>
                            <th>Severity</th>
                            <th>Target</th>
                            <th>Action</th>
                            <th>Reason</th>
                            <th>Recommended Fix</th>
                            <th>Confidence</th>
                            <th>Controls</th>
                        </tr>
                    </thead>
                    <tbody id="ml-action-body">
                        <tr><td colspan="8">No actions loaded.</td></tr>
                    </tbody>
                </table>
            </div>
        `;

        pc.appendChild(panel);

        const filter = document.getElementById("ml-action-status-filter");
        if (filter) {
            filter.addEventListener("change", window.refreshMlActionsPanel);
        }

        return true;
    }

    function renderSummary(actions) {
        const totalEl = document.getElementById("ml-action-total-value");
        const recommendedEl = document.getElementById("ml-action-recommended-value");
        const approvedEl = document.getElementById("ml-action-approved-value");
        const riskEl = document.getElementById("ml-action-risk-value");

        const total = actions.length;
        const recommended = actions.filter(a => String(a.status || "").toLowerCase() === "recommended").length;
        const approved = actions.filter(a => String(a.status || "").toLowerCase() === "approved").length;
        const risky = actions.filter(a => ["critical", "high"].includes(String(a.severity || "").toLowerCase())).length;

        if (totalEl) totalEl.textContent = String(total);
        if (recommendedEl) recommendedEl.textContent = String(recommended);
        if (approvedEl) approvedEl.textContent = String(approved);
        if (riskEl) {
            riskEl.textContent = String(risky);
            riskEl.className = risky > 0 ? "ml-action-summary-value high" : "ml-action-summary-value low";
        }
    }

    function renderActions(actions) {
        const body = document.getElementById("ml-action-body");
        if (!body) return;

        actions = Array.isArray(actions) ? actions : [];
        ML_ACTION_CACHE = actions;

        renderSummary(actions);

        if (!actions.length) {
            body.innerHTML = `<tr><td colspan="8">No ML actions found. Click GENERATE ACTIONS.</td></tr>`;
            return;
        }

        body.innerHTML = "";

        actions.forEach(action => {
            const status = action.status || "recommended";
            const severity = action.severity || "medium";
            const id = action.action_id || "";

            const canApprove = status === "recommended";
            const canReject = status === "recommended" || status === "approved";
            const canComplete = status === "approved" || status === "recommended";

            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td><span class="ml-action-pill ${riskClass(status)}">${esc(status)}</span></td>
                <td><span class="ml-action-pill ${riskClass(severity)}">${esc(severity)}</span></td>
                <td>${esc(action.target_pc_id || "SYSTEM")}</td>
                <td title="${esc(action.action_type || "")}"><strong>${esc(short(action.title || action.action_type || "—", 120))}</strong></td>
                <td title="${esc(action.reason || "")}">${esc(short(action.reason || "—", 170))}</td>
                <td title="${esc(action.recommended_fix || "")}">${esc(short(action.recommended_fix || "—", 210))}</td>
                <td>${esc(action.confidence || "—")}%</td>
                <td class="ml-action-control-cell">
                    <button class="btn btn-small" ${canApprove ? "" : "disabled"} onclick="approveMlActionFromPanel('${esc(id)}')">Approve</button>
                    <button class="btn btn-small" ${canReject ? "" : "disabled"} onclick="rejectMlActionFromPanel('${esc(id)}')">Reject</button>
                    <button class="btn btn-small" ${canComplete ? "" : "disabled"} onclick="completeMlActionFromPanel('${esc(id)}')">Complete</button>
                </td>
            `;
            body.appendChild(tr);
        });
    }

    window.refreshMlActionsPanel = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_ml_actions !== "function") {
            setActionStatus("Backend bridge missing: get_ml_actions", true);
            return;
        }

        const filter = document.getElementById("ml-action-status-filter");
        const status = filter ? filter.value : "";

        try {
            setActionStatus("Loading ML action queue...");

            const data = await window.pywebview.api.get_ml_actions(status, "", 300);

            if (!data || data.ok === false) {
                setActionStatus(data && data.error ? data.error : "Could not load ML actions.", true);
                renderActions([]);
                return;
            }

            renderActions(data.actions || []);
            setActionStatus(`Loaded ${data.count || (data.actions || []).length || 0} ML action(s).`);

        } catch (err) {
            setActionStatus(String(err), true);
        }
    };

    window.generateMlActionsFromPanel = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.generate_ml_actions !== "function") {
            setActionStatus("Backend bridge missing: generate_ml_actions", true);
            return;
        }

        try {
            setActionStatus("Generating ML recommended actions...");

            const data = await window.pywebview.api.generate_ml_actions();

            if (!data || data.ok === false) {
                setActionStatus(data && data.error ? data.error : "Could not generate ML actions.", true);
                return;
            }

            setActionStatus(`Generated ${data.added_count || 0} new action(s).`);
            setTimeout(window.refreshMlActionsPanel, 500);

        } catch (err) {
            setActionStatus(String(err), true);
        }
    };

    window.approveMlActionFromPanel = async function (actionId) {
        if (!actionId) return;

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.approve_ml_action !== "function") {
            setActionStatus("Backend bridge missing: approve_ml_action", true);
            return;
        }

        try {
            const data = await window.pywebview.api.approve_ml_action(actionId, "Approved from dashboard.");

            if (!data || data.ok === false) {
                setActionStatus(data && data.error ? data.error : "Approve failed.", true);
                return;
            }

            setActionStatus("Action approved. No automatic execution was performed.");
            setTimeout(window.refreshMlActionsPanel, 400);

        } catch (err) {
            setActionStatus(String(err), true);
        }
    };

    window.rejectMlActionFromPanel = async function (actionId) {
        if (!actionId) return;

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.reject_ml_action !== "function") {
            setActionStatus("Backend bridge missing: reject_ml_action", true);
            return;
        }

        try {
            const data = await window.pywebview.api.reject_ml_action(actionId, "Rejected from dashboard.");

            if (!data || data.ok === false) {
                setActionStatus(data && data.error ? data.error : "Reject failed.", true);
                return;
            }

            setActionStatus("Action rejected.");
            setTimeout(window.refreshMlActionsPanel, 400);

        } catch (err) {
            setActionStatus(String(err), true);
        }
    };

    window.completeMlActionFromPanel = async function (actionId) {
        if (!actionId) return;

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.complete_ml_action !== "function") {
            setActionStatus("Backend bridge missing: complete_ml_action", true);
            return;
        }

        try {
            const data = await window.pywebview.api.complete_ml_action(actionId, "completed", "Marked completed from dashboard.");

            if (!data || data.ok === false) {
                setActionStatus(data && data.error ? data.error : "Complete failed.", true);
                return;
            }

            setActionStatus("Action marked completed.");
            setTimeout(window.refreshMlActionsPanel, 400);

        } catch (err) {
            setActionStatus(String(err), true);
        }
    };

    window.clearCompletedMlActionsFromPanel = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.clear_ml_actions !== "function") {
            setActionStatus("Backend bridge missing: clear_ml_actions", true);
            return;
        }

        if (!confirm("Clear completed/rejected/failed/cancelled ML actions only?")) {
            return;
        }

        try {
            const data = await window.pywebview.api.clear_ml_actions("completed");

            if (!data || data.ok === false) {
                setActionStatus(data && data.error ? data.error : "Clear failed.", true);
                return;
            }

            setActionStatus(`Cleared ${data.removed || 0} done action(s).`);
            setTimeout(window.refreshMlActionsPanel, 400);

        } catch (err) {
            setActionStatus(String(err), true);
        }
    };

    function setupPanelWhenVisible() {
        const pc = document.getElementById("pc-control-section");

        if (!pc || pc.style.display === "none") {
            return;
        }

        if (ensurePanel()) {
            const statusEl = document.getElementById("ml-action-status-v1");
            if (statusEl && statusEl.textContent.includes("Waiting")) {
                window.refreshMlActionsPanel();
            }
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        setTimeout(setupPanelWhenVisible, 5500);
    });

    setInterval(setupPanelWhenVisible, 10000);
})();

// =====================================================
// ML SAFE AUTO-EXECUTOR PANEL v1
// Automatic only for safe actions: PING, STATUS_REPORT.
// =====================================================

(function () {
    const PANEL_ID = "ml-safe-auto-executor-panel-v1";

    function esc(value) {
        return String(value === undefined || value === null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function short(value, max = 160) {
        value = String(value || "");
        return value.length > max ? value.slice(0, max) + "..." : value;
    }

    function setStatus(message, bad = false) {
        const el = document.getElementById("ml-auto-executor-status-v1");
        if (!el) return;
        el.textContent = message || "";
        el.className = bad ? "ml-auto-executor-status bad" : "ml-auto-executor-status";
    }

    function ensurePanel() {
        if (document.getElementById(PANEL_ID)) return true;

        const pc = document.getElementById("pc-control-section");
        if (!pc) return false;

        const panel = document.createElement("div");
        panel.id = PANEL_ID;
        panel.className = "ml-auto-executor-panel";
        panel.innerHTML = `
            <div class="ml-auto-executor-header">
                <div>
                    <h3>ML Safe Auto-Executor v1</h3>
                    <div class="ml-auto-executor-subtitle">
                        Automatically runs only safe actions: SEND_PING, SEND_STATUS_REPORT, NO_ACTION_NEEDED. Repairs/permission changes stay manual.
                    </div>
                </div>
                <div class="ml-auto-executor-controls">
                    <button class="btn btn-primary" onclick="enableMlAutoExecutorFromPanel()">ENABLE AUTO</button>
                    <button class="btn btn-primary" onclick="disableMlAutoExecutorFromPanel()">DISABLE AUTO</button>
                    <button class="btn btn-primary" onclick="runMlAutoExecutorNowFromPanel()">RUN NOW</button>
                    <button class="btn btn-primary" onclick="refreshMlAutoExecutorPanel()">REFRESH</button>
                </div>
            </div>

            <div id="ml-auto-executor-status-v1" class="ml-auto-executor-status">
                Waiting for ML Safe Auto-Executor...
            </div>

            <div class="ml-auto-executor-summary-grid">
                <div class="ml-auto-executor-card">
                    <div class="ml-auto-executor-label">Auto Mode</div>
                    <div id="ml-auto-enabled-value" class="ml-auto-executor-value">—</div>
                </div>
                <div class="ml-auto-executor-card">
                    <div class="ml-auto-executor-label">Safe Auto Actions</div>
                    <div id="ml-auto-safe-actions-value" class="ml-auto-executor-value small">—</div>
                </div>
                <div class="ml-auto-executor-card">
                    <div class="ml-auto-executor-label">Max Per Cycle</div>
                    <div id="ml-auto-max-value" class="ml-auto-executor-value">—</div>
                </div>
                <div class="ml-auto-executor-card">
                    <div class="ml-auto-executor-label">Last Run</div>
                    <div id="ml-auto-last-value" class="ml-auto-executor-value small">—</div>
                </div>
            </div>

            <div class="ml-auto-executor-note">
                Safe automatic actions only create Command Center tasks for PING/STATUS_REPORT. They do not run emergency repair, change permissions, block devices, delete files, or clear queues.
            </div>

            <div class="ml-auto-executor-table-wrap">
                <table class="ghost-table ml-auto-executor-table">
                    <thead>
                        <tr>
                            <th>Time</th>
                            <th>Executed</th>
                            <th>Skipped</th>
                            <th>Generated</th>
                            <th>Details</th>
                        </tr>
                    </thead>
                    <tbody id="ml-auto-executor-events-body">
                        <tr><td colspan="5">No auto-executor events loaded.</td></tr>
                    </tbody>
                </table>
            </div>
        `;

        pc.appendChild(panel);
        return true;
    }

    function renderConfig(config) {
        const enabledEl = document.getElementById("ml-auto-enabled-value");
        const safeEl = document.getElementById("ml-auto-safe-actions-value");
        const maxEl = document.getElementById("ml-auto-max-value");

        if (enabledEl) {
            enabledEl.textContent = config.enabled ? "ENABLED" : "DISABLED";
            enabledEl.className = config.enabled ? "ml-auto-executor-value good" : "ml-auto-executor-value bad";
        }

        if (safeEl) safeEl.textContent = (config.safe_auto_action_types || []).join(", ") || "—";
        if (maxEl) maxEl.textContent = String(config.max_auto_commands_per_cycle || "—");
    }

    function renderEvents(events) {
        const body = document.getElementById("ml-auto-executor-events-body");
        if (!body) return;

        events = Array.isArray(events) ? events : [];

        if (!events.length) {
            body.innerHTML = `<tr><td colspan="5">No auto-executor events yet.</td></tr>`;
            return;
        }

        body.innerHTML = "";

        events.slice(0, 100).forEach(row => {
            const generated = row.generated && typeof row.generated === "object" ? row.generated.added_count : "";
            const details = JSON.stringify({
                executed: row.executed || [],
                skipped: row.skipped || []
            });

            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${esc(row.time || "—")}</td>
                <td>${esc(row.executed_count || 0)}</td>
                <td>${esc(row.skipped_count || 0)}</td>
                <td>${esc(generated || 0)}</td>
                <td title="${esc(details)}">${esc(short(details, 260))}</td>
            `;
            body.appendChild(tr);
        });
    }

    window.refreshMlAutoExecutorPanel = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_ml_auto_executor_config !== "function") {
            setStatus("Backend bridge missing: get_ml_auto_executor_config", true);
            return;
        }

        try {
            setStatus("Loading safe auto-executor config...");

            const config = await window.pywebview.api.get_ml_auto_executor_config();

            if (!config || config.ok === false) {
                setStatus(config && config.error ? config.error : "Could not load auto-executor config.", true);
                return;
            }

            renderConfig(config);

            if (window.pywebview.api.get_ml_auto_executor_events) {
                const events = await window.pywebview.api.get_ml_auto_executor_events(200);
                if (events && events.ok !== false) {
                    renderEvents(events.events || []);
                    const lastEl = document.getElementById("ml-auto-last-value");
                    if (lastEl) lastEl.textContent = events.events && events.events.length ? String(events.events[0].time || "—") : "—";
                }
            }

            setStatus(`Safe auto-executor is ${config.enabled ? "ENABLED" : "DISABLED"}.`);

        } catch (err) {
            setStatus(String(err), true);
        }
    };

    window.enableMlAutoExecutorFromPanel = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.set_ml_auto_executor_config !== "function") {
            setStatus("Backend bridge missing: set_ml_auto_executor_config", true);
            return;
        }

        try {
            const data = await window.pywebview.api.set_ml_auto_executor_config(true, 5);

            if (!data || data.ok === false) {
                setStatus(data && data.error ? data.error : "Enable failed.", true);
                return;
            }

            setStatus("Safe auto-executor enabled.");
            setTimeout(window.refreshMlAutoExecutorPanel, 400);

        } catch (err) {
            setStatus(String(err), true);
        }
    };

    window.disableMlAutoExecutorFromPanel = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.set_ml_auto_executor_config !== "function") {
            setStatus("Backend bridge missing: set_ml_auto_executor_config", true);
            return;
        }

        try {
            const data = await window.pywebview.api.set_ml_auto_executor_config(false, 5);

            if (!data || data.ok === false) {
                setStatus(data && data.error ? data.error : "Disable failed.", true);
                return;
            }

            setStatus("Safe auto-executor disabled.");
            setTimeout(window.refreshMlAutoExecutorPanel, 400);

        } catch (err) {
            setStatus(String(err), true);
        }
    };

    window.runMlAutoExecutorNowFromPanel = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.run_ml_auto_executor_once !== "function") {
            setStatus("Backend bridge missing: run_ml_auto_executor_once", true);
            return;
        }

        try {
            setStatus("Running safe auto-executor now...");

            const data = await window.pywebview.api.run_ml_auto_executor_once();

            if (!data || data.ok === false) {
                setStatus(data && data.error ? data.error : "Auto-run failed.", true);
                return;
            }

            setStatus(`Auto-run complete. Executed ${data.executed_count || 0}, skipped ${data.skipped_count || 0}.`);
            setTimeout(window.refreshMlAutoExecutorPanel, 500);

            if (window.refreshMlActionsPanel) {
                setTimeout(window.refreshMlActionsPanel, 700);
            }

            if (window.refreshCommandCenterPanel) {
                setTimeout(window.refreshCommandCenterPanel, 900);
            }

        } catch (err) {
            setStatus(String(err), true);
        }
    };

    function setupPanelWhenVisible() {
        const pc = document.getElementById("pc-control-section");

        if (!pc || pc.style.display === "none") {
            return;
        }

        if (ensurePanel()) {
            const statusEl = document.getElementById("ml-auto-executor-status-v1");
            if (statusEl && statusEl.textContent.includes("Waiting")) {
                window.refreshMlAutoExecutorPanel();
            }
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        setTimeout(setupPanelWhenVisible, 6000);
    });

    setInterval(setupPanelWhenVisible, 10000);
})();

// =====================================================
// ML RESULT FEEDBACK LOOP PANEL v1
// Links auto-executor actions to actual Command Center results.
// =====================================================

(function () {
    const PANEL_ID = "ml-result-feedback-loop-panel-v1";

    function esc(value) {
        return String(value === undefined || value === null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function short(value, max = 180) {
        value = String(value || "");
        return value.length > max ? value.slice(0, max) + "..." : value;
    }

    function setStatus(message, bad = false) {
        const el = document.getElementById("ml-feedback-status-v1");
        if (!el) return;
        el.textContent = message || "";
        el.className = bad ? "ml-feedback-status bad" : "ml-feedback-status";
    }

    function ensurePanel() {
        if (document.getElementById(PANEL_ID)) return true;

        const pc = document.getElementById("pc-control-section");
        if (!pc) return false;

        const panel = document.createElement("div");
        panel.id = PANEL_ID;
        panel.className = "ml-feedback-panel";
        panel.innerHTML = `
            <div class="ml-feedback-header">
                <div>
                    <h3>ML Auto-Executor Result Feedback Loop v1</h3>
                    <div class="ml-feedback-subtitle">
                        Tracks whether ML-created PING/STATUS_REPORT commands actually complete or fail.
                    </div>
                </div>
                <div class="ml-feedback-controls">
                    <button class="btn btn-primary" onclick="enableMlFeedbackFromPanel()">ENABLE FEEDBACK</button>
                    <button class="btn btn-primary" onclick="disableMlFeedbackFromPanel()">DISABLE FEEDBACK</button>
                    <button class="btn btn-primary" onclick="runMlFeedbackNowFromPanel()">RUN FEEDBACK NOW</button>
                    <button class="btn btn-primary" onclick="refreshMlFeedbackPanel()">REFRESH</button>
                </div>
            </div>

            <div id="ml-feedback-status-v1" class="ml-feedback-status">
                Waiting for ML feedback loop...
            </div>

            <div class="ml-feedback-summary-grid">
                <div class="ml-feedback-card">
                    <div class="ml-feedback-label">Feedback Mode</div>
                    <div id="ml-feedback-enabled-value" class="ml-feedback-value">—</div>
                </div>
                <div class="ml-feedback-card">
                    <div class="ml-feedback-label">Checked Last Run</div>
                    <div id="ml-feedback-checked-value" class="ml-feedback-value">—</div>
                </div>
                <div class="ml-feedback-card">
                    <div class="ml-feedback-label">Updated Last Run</div>
                    <div id="ml-feedback-updated-value" class="ml-feedback-value">—</div>
                </div>
                <div class="ml-feedback-card">
                    <div class="ml-feedback-label">Last Event</div>
                    <div id="ml-feedback-last-value" class="ml-feedback-value small">—</div>
                </div>
            </div>

            <div class="ml-feedback-note">
                This loop only updates ML action feedback status. It does not restart devices, repair code, change permissions, or delete anything.
            </div>

            <div class="ml-feedback-table-wrap">
                <table class="ghost-table ml-feedback-table">
                    <thead>
                        <tr>
                            <th>Time</th>
                            <th>Checked</th>
                            <th>Updated</th>
                            <th>Updates</th>
                        </tr>
                    </thead>
                    <tbody id="ml-feedback-events-body">
                        <tr><td colspan="4">No feedback events loaded.</td></tr>
                    </tbody>
                </table>
            </div>
        `;

        pc.appendChild(panel);
        return true;
    }

    function renderConfig(config) {
        const enabledEl = document.getElementById("ml-feedback-enabled-value");
        if (enabledEl) {
            enabledEl.textContent = config.enabled ? "ENABLED" : "DISABLED";
            enabledEl.className = config.enabled ? "ml-feedback-value good" : "ml-feedback-value bad";
        }
    }

    function renderEvents(events) {
        const body = document.getElementById("ml-feedback-events-body");
        if (!body) return;

        events = Array.isArray(events) ? events : [];

        if (!events.length) {
            body.innerHTML = `<tr><td colspan="4">No feedback events yet.</td></tr>`;
            return;
        }

        body.innerHTML = "";

        events.slice(0, 100).forEach((row, index) => {
            const updates = JSON.stringify(row.updates || []);
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${esc(row.time || "—")}</td>
                <td>${esc(row.checked_count || 0)}</td>
                <td>${esc(row.updated_count || 0)}</td>
                <td title="${esc(updates)}">${esc(short(updates, 320))}</td>
            `;
            body.appendChild(tr);

            if (index === 0) {
                const checkedEl = document.getElementById("ml-feedback-checked-value");
                const updatedEl = document.getElementById("ml-feedback-updated-value");
                const lastEl = document.getElementById("ml-feedback-last-value");

                if (checkedEl) checkedEl.textContent = String(row.checked_count || 0);
                if (updatedEl) updatedEl.textContent = String(row.updated_count || 0);
                if (lastEl) lastEl.textContent = String(row.time || "—");
            }
        });
    }

    window.refreshMlFeedbackPanel = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_ml_feedback_config !== "function") {
            setStatus("Backend bridge missing: get_ml_feedback_config", true);
            return;
        }

        try {
            setStatus("Loading feedback loop status...");

            const config = await window.pywebview.api.get_ml_feedback_config();

            if (!config || config.ok === false) {
                setStatus(config && config.error ? config.error : "Could not load feedback config.", true);
                return;
            }

            renderConfig(config);

            if (window.pywebview.api.get_ml_feedback_events) {
                const events = await window.pywebview.api.get_ml_feedback_events(200);
                if (events && events.ok !== false) {
                    renderEvents(events.events || []);
                }
            }

            setStatus(`Feedback loop is ${config.enabled ? "ENABLED" : "DISABLED"}.`);

        } catch (err) {
            setStatus(String(err), true);
        }
    };

    window.enableMlFeedbackFromPanel = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.set_ml_feedback_config !== "function") {
            setStatus("Backend bridge missing: set_ml_feedback_config", true);
            return;
        }

        try {
            const data = await window.pywebview.api.set_ml_feedback_config(true);

            if (!data || data.ok === false) {
                setStatus(data && data.error ? data.error : "Enable feedback failed.", true);
                return;
            }

            setStatus("Feedback loop enabled.");
            setTimeout(window.refreshMlFeedbackPanel, 400);

        } catch (err) {
            setStatus(String(err), true);
        }
    };

    window.disableMlFeedbackFromPanel = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.set_ml_feedback_config !== "function") {
            setStatus("Backend bridge missing: set_ml_feedback_config", true);
            return;
        }

        try {
            const data = await window.pywebview.api.set_ml_feedback_config(false);

            if (!data || data.ok === false) {
                setStatus(data && data.error ? data.error : "Disable feedback failed.", true);
                return;
            }

            setStatus("Feedback loop disabled.");
            setTimeout(window.refreshMlFeedbackPanel, 400);

        } catch (err) {
            setStatus(String(err), true);
        }
    };

    window.runMlFeedbackNowFromPanel = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.run_ml_feedback_once !== "function") {
            setStatus("Backend bridge missing: run_ml_feedback_once", true);
            return;
        }

        try {
            setStatus("Running feedback loop now...");

            const data = await window.pywebview.api.run_ml_feedback_once();

            if (!data || data.ok === false) {
                setStatus(data && data.error ? data.error : "Feedback run failed.", true);
                return;
            }

            const checkedEl = document.getElementById("ml-feedback-checked-value");
            const updatedEl = document.getElementById("ml-feedback-updated-value");

            if (checkedEl) checkedEl.textContent = String(data.checked_count || 0);
            if (updatedEl) updatedEl.textContent = String(data.updated_count || 0);

            setStatus(`Feedback run complete. Checked ${data.checked_count || 0}, updated ${data.updated_count || 0}.`);

            setTimeout(window.refreshMlFeedbackPanel, 500);

            if (window.refreshMlActionsPanel) {
                setTimeout(window.refreshMlActionsPanel, 700);
            }

            if (window.refreshMlReliabilityPanel) {
                setTimeout(window.refreshMlReliabilityPanel, 900);
            }

        } catch (err) {
            setStatus(String(err), true);
        }
    };

    function setupPanelWhenVisible() {
        const pc = document.getElementById("pc-control-section");

        if (!pc || pc.style.display === "none") {
            return;
        }

        if (ensurePanel()) {
            const statusEl = document.getElementById("ml-feedback-status-v1");
            if (statusEl && statusEl.textContent.includes("Waiting")) {
                window.refreshMlFeedbackPanel();
            }
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        setTimeout(setupPanelWhenVisible, 6500);
    });

    setInterval(setupPanelWhenVisible, 10000);
})();

// =====================================================
// ML AUTO-RESOLVE + SCORE ADJUSTMENT PANEL v1
// Resolves safe ML actions and tracks device score deltas.
// =====================================================

(function () {
    const PANEL_ID = "ml-auto-resolver-panel-v1";

    function esc(value) {
        return String(value === undefined || value === null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function short(value, max = 180) {
        value = String(value || "");
        return value.length > max ? value.slice(0, max) + "..." : value;
    }

    function riskClass(value) {
        value = String(value || "").toLowerCase();
        if (value.includes("critical")) return "critical";
        if (value.includes("high")) return "high";
        if (value.includes("medium")) return "medium";
        if (value.includes("low")) return "low";
        return "unknown";
    }

    function setStatus(message, bad = false) {
        const el = document.getElementById("ml-auto-resolver-status-v1");
        if (!el) return;
        el.textContent = message || "";
        el.className = bad ? "ml-auto-resolver-status bad" : "ml-auto-resolver-status";
    }

    function ensurePanel() {
        if (document.getElementById(PANEL_ID)) return true;

        const pc = document.getElementById("pc-control-section");
        if (!pc) return false;

        const panel = document.createElement("div");
        panel.id = PANEL_ID;
        panel.className = "ml-auto-resolver-panel";
        panel.innerHTML = `
            <div class="ml-auto-resolver-header">
                <div>
                    <h3>ML Auto-Resolve + Device Score Adjustment v1</h3>
                    <div class="ml-auto-resolver-subtitle">
                        Auto-resolves successful safe ML actions and adjusts device reliability using real command feedback.
                    </div>
                </div>
                <div class="ml-auto-resolver-controls">
                    <button class="btn btn-primary" onclick="enableMlAutoResolverFromPanel()">ENABLE RESOLVER</button>
                    <button class="btn btn-primary" onclick="disableMlAutoResolverFromPanel()">DISABLE RESOLVER</button>
                    <button class="btn btn-primary" onclick="runMlAutoResolverNowFromPanel()">RUN RESOLVER NOW</button>
                    <button class="btn btn-primary" onclick="refreshMlAutoResolverPanel()">REFRESH</button>
                </div>
            </div>

            <div id="ml-auto-resolver-status-v1" class="ml-auto-resolver-status">
                Waiting for ML auto-resolver...
            </div>

            <div class="ml-auto-resolver-summary-grid">
                <div class="ml-auto-resolver-card">
                    <div class="ml-auto-resolver-label">Resolver Mode</div>
                    <div id="ml-resolver-enabled-value" class="ml-auto-resolver-value">—</div>
                </div>
                <div class="ml-auto-resolver-card">
                    <div class="ml-auto-resolver-label">Resolved Last Run</div>
                    <div id="ml-resolver-resolved-value" class="ml-auto-resolver-value">—</div>
                </div>
                <div class="ml-auto-resolver-card">
                    <div class="ml-auto-resolver-label">Needs Attention</div>
                    <div id="ml-resolver-attention-value" class="ml-auto-resolver-value">—</div>
                </div>
                <div class="ml-auto-resolver-card">
                    <div class="ml-auto-resolver-label">Last Event</div>
                    <div id="ml-resolver-last-value" class="ml-auto-resolver-value small">—</div>
                </div>
            </div>

            <div class="ml-auto-resolver-note">
                This only resolves safe ML actions and adjusts scores. It does not run repairs, change permissions, block devices, delete files, or alter launch logic.
            </div>

            <div class="ml-auto-resolver-section-title">Adjusted Device Reliability</div>
            <div class="ml-auto-resolver-table-wrap">
                <table class="ghost-table ml-auto-resolver-table">
                    <thead>
                        <tr>
                            <th>Device</th>
                            <th>Raw Score</th>
                            <th>Adjustment</th>
                            <th>Adjusted Score</th>
                            <th>Risk</th>
                            <th>Success</th>
                            <th>Failures</th>
                            <th>Last Update</th>
                        </tr>
                    </thead>
                    <tbody id="ml-adjusted-score-body">
                        <tr><td colspan="8">No adjusted scores loaded.</td></tr>
                    </tbody>
                </table>
            </div>

            <div class="ml-auto-resolver-section-title">Resolver Events</div>
            <div class="ml-auto-resolver-table-wrap">
                <table class="ghost-table ml-auto-resolver-table">
                    <thead>
                        <tr>
                            <th>Time</th>
                            <th>Resolved</th>
                            <th>Needs Attention</th>
                            <th>Skipped</th>
                            <th>Details</th>
                        </tr>
                    </thead>
                    <tbody id="ml-auto-resolver-events-body">
                        <tr><td colspan="5">No resolver events loaded.</td></tr>
                    </tbody>
                </table>
            </div>
        `;

        pc.appendChild(panel);
        return true;
    }

    function renderConfig(config) {
        const enabledEl = document.getElementById("ml-resolver-enabled-value");

        if (enabledEl) {
            enabledEl.textContent = config.enabled ? "ENABLED" : "DISABLED";
            enabledEl.className = config.enabled ? "ml-auto-resolver-value good" : "ml-auto-resolver-value bad";
        }
    }

    function renderAdjustedScores(rows) {
        const body = document.getElementById("ml-adjusted-score-body");
        if (!body) return;

        rows = Array.isArray(rows) ? rows : [];

        if (!rows.length) {
            body.innerHTML = `<tr><td colspan="8">No adjusted reliability data yet.</td></tr>`;
            return;
        }

        body.innerHTML = "";

        rows.forEach(row => {
            const risk = row.adjusted_risk || row.risk || "unknown";
            const delta = Number(row.score_adjustment || 0);
            const deltaText = delta > 0 ? "+" + delta.toFixed(1) : delta.toFixed(1);

            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${esc(row.pc_id || "—")}</td>
                <td>${esc(row.raw_score || row.score || "—")}%</td>
                <td><strong>${esc(deltaText)}</strong></td>
                <td><strong>${esc(row.adjusted_score || row.score || "—")}%</strong></td>
                <td><span class="ml-auto-resolver-pill ${riskClass(risk)}">${esc(risk)}</span></td>
                <td>${esc(row.resolver_success_count || 0)}</td>
                <td>${esc(row.resolver_failure_count || 0)}</td>
                <td>${esc(row.last_resolver_update || "—")}</td>
            `;
            body.appendChild(tr);
        });
    }

    function renderEvents(events) {
        const body = document.getElementById("ml-auto-resolver-events-body");
        if (!body) return;

        events = Array.isArray(events) ? events : [];

        if (!events.length) {
            body.innerHTML = `<tr><td colspan="5">No resolver events yet.</td></tr>`;
            return;
        }

        body.innerHTML = "";

        events.slice(0, 100).forEach((row, index) => {
            const details = JSON.stringify({
                resolved: row.resolved || [],
                needs_attention: row.needs_attention || [],
                skipped: row.skipped || []
            });

            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${esc(row.time || "—")}</td>
                <td>${esc(row.resolved_count || 0)}</td>
                <td>${esc(row.attention_count || 0)}</td>
                <td>${esc(row.skipped_count || 0)}</td>
                <td title="${esc(details)}">${esc(short(details, 320))}</td>
            `;
            body.appendChild(tr);

            if (index === 0) {
                const resolvedEl = document.getElementById("ml-resolver-resolved-value");
                const attentionEl = document.getElementById("ml-resolver-attention-value");
                const lastEl = document.getElementById("ml-resolver-last-value");

                if (resolvedEl) resolvedEl.textContent = String(row.resolved_count || 0);
                if (attentionEl) attentionEl.textContent = String(row.attention_count || 0);
                if (lastEl) lastEl.textContent = String(row.time || "—");
            }
        });
    }

    window.refreshMlAutoResolverPanel = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_ml_auto_resolver_config !== "function") {
            setStatus("Backend bridge missing: get_ml_auto_resolver_config", true);
            return;
        }

        try {
            setStatus("Loading auto-resolver status...");

            const config = await window.pywebview.api.get_ml_auto_resolver_config();

            if (!config || config.ok === false) {
                setStatus(config && config.error ? config.error : "Could not load auto-resolver config.", true);
                return;
            }

            renderConfig(config);

            if (window.pywebview.api.get_ml_adjusted_reliability) {
                const adjusted = await window.pywebview.api.get_ml_adjusted_reliability();
                if (adjusted && adjusted.ok !== false) {
                    renderAdjustedScores(adjusted.device_scores || []);
                }
            }

            if (window.pywebview.api.get_ml_auto_resolver_events) {
                const events = await window.pywebview.api.get_ml_auto_resolver_events(200);
                if (events && events.ok !== false) {
                    renderEvents(events.events || []);
                }
            }

            setStatus(`Auto-resolver is ${config.enabled ? "ENABLED" : "DISABLED"}.`);

        } catch (err) {
            setStatus(String(err), true);
        }
    };

    window.enableMlAutoResolverFromPanel = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.set_ml_auto_resolver_config !== "function") {
            setStatus("Backend bridge missing: set_ml_auto_resolver_config", true);
            return;
        }

        try {
            const data = await window.pywebview.api.set_ml_auto_resolver_config(true);

            if (!data || data.ok === false) {
                setStatus(data && data.error ? data.error : "Enable resolver failed.", true);
                return;
            }

            setStatus("Auto-resolver enabled.");
            setTimeout(window.refreshMlAutoResolverPanel, 400);

        } catch (err) {
            setStatus(String(err), true);
        }
    };

    window.disableMlAutoResolverFromPanel = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.set_ml_auto_resolver_config !== "function") {
            setStatus("Backend bridge missing: set_ml_auto_resolver_config", true);
            return;
        }

        try {
            const data = await window.pywebview.api.set_ml_auto_resolver_config(false);

            if (!data || data.ok === false) {
                setStatus(data && data.error ? data.error : "Disable resolver failed.", true);
                return;
            }

            setStatus("Auto-resolver disabled.");
            setTimeout(window.refreshMlAutoResolverPanel, 400);

        } catch (err) {
            setStatus(String(err), true);
        }
    };

    window.runMlAutoResolverNowFromPanel = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.run_ml_auto_resolver_once !== "function") {
            setStatus("Backend bridge missing: run_ml_auto_resolver_once", true);
            return;
        }

        try {
            setStatus("Running auto-resolver now...");

            const data = await window.pywebview.api.run_ml_auto_resolver_once();

            if (!data || data.ok === false) {
                setStatus(data && data.error ? data.error : "Auto-resolver run failed.", true);
                return;
            }

            setStatus(`Resolver complete. Resolved ${data.resolved_count || 0}, needs attention ${data.attention_count || 0}.`);

            setTimeout(window.refreshMlAutoResolverPanel, 500);

            if (window.refreshMlActionsPanel) {
                setTimeout(window.refreshMlActionsPanel, 700);
            }

            if (window.refreshMlReliabilityPanel) {
                setTimeout(window.refreshMlReliabilityPanel, 900);
            }

        } catch (err) {
            setStatus(String(err), true);
        }
    };

    function setupPanelWhenVisible() {
        const pc = document.getElementById("pc-control-section");

        if (!pc || pc.style.display === "none") {
            return;
        }

        if (ensurePanel()) {
            const statusEl = document.getElementById("ml-auto-resolver-status-v1");
            if (statusEl && statusEl.textContent.includes("Waiting")) {
                window.refreshMlAutoResolverPanel();
            }
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        setTimeout(setupPanelWhenVisible, 7000);
    });

    setInterval(setupPanelWhenVisible, 10000);
})();

// =====================================================
// UNIFIED ML CONTROL CENTER + DEVICE HEALTH TIMELINE v1
// One clean view that summarizes ML status and device history.
// =====================================================

(function () {
    const PANEL_ID = "unified-ml-control-center-v1";
    let UNIFIED_ML_STATE = null;

    function esc(value) {
        return String(value === undefined || value === null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function short(value, max = 180) {
        value = String(value || "");
        return value.length > max ? value.slice(0, max) + "..." : value;
    }

    function riskClass(value) {
        value = String(value || "").toLowerCase();
        if (value.includes("critical")) return "critical";
        if (value.includes("high")) return "high";
        if (value.includes("watch") || value.includes("medium") || value.includes("learning")) return "medium";
        if (value.includes("ok") || value.includes("low") || value.includes("stable") || value.includes("completed") || value.includes("resolved")) return "low";
        if (value.includes("failed") || value.includes("attention")) return "critical";
        return "unknown";
    }

    function setUnifiedStatus(message, bad = false) {
        const el = document.getElementById("unified-ml-status-v1");
        if (!el) return;
        el.textContent = message || "";
        el.className = bad ? "unified-ml-status bad" : "unified-ml-status";
    }

    function ensurePanel() {
        if (document.getElementById(PANEL_ID)) return true;

        const pc = document.getElementById("pc-control-section");
        if (!pc) return false;

        const panel = document.createElement("div");
        panel.id = PANEL_ID;
        panel.className = "unified-ml-panel";
        panel.innerHTML = `
            <div class="unified-ml-header">
                <div>
                    <h3>Unified ML Control Center + Device Timeline v1</h3>
                    <div class="unified-ml-subtitle">
                        One clean view for reliability, trends, actions, command results, safe automation, and device timeline.
                    </div>
                </div>
                <div class="unified-ml-controls">
                    <select id="unified-ml-device-select" class="unified-ml-select">
                        <option value="">All Devices</option>
                    </select>
                    <button class="btn btn-primary" onclick="refreshUnifiedMlControlCenter()">REFRESH CONTROL CENTER</button>
                    <button class="btn btn-primary" onclick="refreshUnifiedMlTimeline()">LOAD TIMELINE</button>
                </div>
            </div>

            <div id="unified-ml-status-v1" class="unified-ml-status">
                Waiting for Unified ML Control Center...
            </div>

            <div class="unified-ml-summary-grid">
                <div class="unified-ml-card">
                    <div class="unified-ml-label">Overall</div>
                    <div id="unified-overall-value" class="unified-ml-value">—</div>
                </div>
                <div class="unified-ml-card">
                    <div class="unified-ml-label">Devices</div>
                    <div id="unified-devices-value" class="unified-ml-value">—</div>
                </div>
                <div class="unified-ml-card">
                    <div class="unified-ml-label">Open Actions</div>
                    <div id="unified-actions-value" class="unified-ml-value">—</div>
                </div>
                <div class="unified-ml-card">
                    <div class="unified-ml-label">Commands</div>
                    <div id="unified-commands-value" class="unified-ml-value">—</div>
                </div>
                <div class="unified-ml-card">
                    <div class="unified-ml-label">Snapshots</div>
                    <div id="unified-snapshots-value" class="unified-ml-value">—</div>
                </div>
                <div class="unified-ml-card">
                    <div class="unified-ml-label">Auto Executor</div>
                    <div id="unified-auto-value" class="unified-ml-value small">—</div>
                </div>
                <div class="unified-ml-card">
                    <div class="unified-ml-label">Feedback Loop</div>
                    <div id="unified-feedback-value" class="unified-ml-value small">—</div>
                </div>
                <div class="unified-ml-card">
                    <div class="unified-ml-label">Auto Resolver</div>
                    <div id="unified-resolver-value" class="unified-ml-value small">—</div>
                </div>
            </div>

            <div class="unified-ml-section-title">Unified Device Table</div>
            <div class="unified-ml-table-wrap">
                <table class="ghost-table unified-ml-table">
                    <thead>
                        <tr>
                            <th>Device</th>
                            <th>Role</th>
                            <th>Raw Score</th>
                            <th>Adjustment</th>
                            <th>Adjusted Score</th>
                            <th>Risk</th>
                            <th>Trend</th>
                            <th>Prediction</th>
                            <th>Completed</th>
                            <th>Failed</th>
                            <th>Pending</th>
                        </tr>
                    </thead>
                    <tbody id="unified-device-body">
                        <tr><td colspan="11">No device data loaded.</td></tr>
                    </tbody>
                </table>
            </div>

            <div class="unified-ml-section-title">Device Health Timeline</div>
            <div id="unified-timeline-sparkline" class="unified-timeline-sparkline">
                No timeline loaded.
            </div>
            <div class="unified-ml-table-wrap">
                <table class="ghost-table unified-ml-table">
                    <thead>
                        <tr>
                            <th>Time</th>
                            <th>Source</th>
                            <th>Device</th>
                            <th>Status / Risk</th>
                            <th>Score</th>
                            <th>Message</th>
                        </tr>
                    </thead>
                    <tbody id="unified-timeline-body">
                        <tr><td colspan="6">No timeline loaded.</td></tr>
                    </tbody>
                </table>
            </div>
        `;

        pc.appendChild(panel);

        const select = document.getElementById("unified-ml-device-select");
        if (select) {
            select.addEventListener("change", window.refreshUnifiedMlTimeline);
        }

        return true;
    }

    function value(id, text, cls) {
        const el = document.getElementById(id);
        if (!el) return;
        el.textContent = text;
        if (cls) el.className = "unified-ml-value " + cls;
    }

    function renderSummary(data) {
        const overall = data.overall || "unknown";
        const actions = data.actions || {};
        const commands = data.commands || {};
        const trends = data.trends || {};
        const configs = data.configs || {};

        const openActions = Number(actions.recommended || 0) + Number(actions.approved || 0) + Number(actions.waiting_result || 0) + Number(actions.needs_attention || 0);

        value("unified-overall-value", overall.toUpperCase(), riskClass(overall));
        value("unified-devices-value", String(data.device_count || (data.devices || []).length || 0));
        value("unified-actions-value", String(openActions), openActions > 0 ? "medium" : "low");
        value("unified-commands-value", String(commands.total || 0));
        value("unified-snapshots-value", String(trends.sample_count || 0));
        value("unified-auto-value", configs.auto_executor ? (configs.auto_executor.enabled ? "ENABLED" : "DISABLED") : "N/A", configs.auto_executor && configs.auto_executor.enabled ? "low" : "medium");
        value("unified-feedback-value", configs.feedback_loop ? (configs.feedback_loop.enabled ? "ENABLED" : "DISABLED") : "N/A", configs.feedback_loop && configs.feedback_loop.enabled ? "low" : "medium");
        value("unified-resolver-value", configs.auto_resolver ? (configs.auto_resolver.enabled ? "ENABLED" : "DISABLED") : "N/A", configs.auto_resolver && configs.auto_resolver.enabled ? "low" : "medium");
    }

    function renderDeviceSelect(devices) {
        const select = document.getElementById("unified-ml-device-select");
        if (!select) return;

        const current = select.value || "";
        select.innerHTML = `<option value="">All Devices</option>`;

        devices.forEach(row => {
            const pcId = row.pc_id || "";
            if (!pcId) return;

            const score = row.adjusted_score ?? row.score ?? "—";
            const option = document.createElement("option");
            option.value = pcId;
            option.textContent = `${pcId} | score ${score}`;
            select.appendChild(option);
        });

        if (current) select.value = current;
    }

    function renderDevices(devices) {
        const body = document.getElementById("unified-device-body");
        if (!body) return;

        devices = Array.isArray(devices) ? devices : [];

        if (!devices.length) {
            body.innerHTML = `<tr><td colspan="11">No unified device data found yet.</td></tr>`;
            return;
        }

        body.innerHTML = "";

        devices.forEach(row => {
            const raw = row.raw_score ?? row.score ?? "—";
            const adjusted = row.adjusted_score ?? row.score ?? "—";
            const risk = row.adjusted_risk || row.risk || row.trend_risk || "unknown";
            const delta = Number(row.score_adjustment || 0);
            const deltaText = delta > 0 ? "+" + delta.toFixed(1) : delta.toFixed(1);

            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td><strong>${esc(row.pc_id || "—")}</strong></td>
                <td>${esc(row.role || "—")}</td>
                <td>${esc(raw)}%</td>
                <td>${esc(deltaText)}</td>
                <td><strong>${esc(adjusted)}%</strong></td>
                <td><span class="unified-ml-pill ${riskClass(risk)}">${esc(risk)}</span></td>
                <td>${esc(row.trend_direction || "—")}</td>
                <td>${esc(row.success_prediction_percent || row.trend_prediction || "—")}%</td>
                <td>${esc(row.commands_completed || 0)}</td>
                <td>${esc(row.commands_failed || 0)}</td>
                <td>${esc(row.commands_pending || 0)}</td>
            `;
            body.appendChild(tr);
        });
    }

    function renderSparkline(points) {
        const el = document.getElementById("unified-timeline-sparkline");
        if (!el) return;

        points = Array.isArray(points) ? points : [];

        if (!points.length) {
            el.innerHTML = "No score history points yet.";
            return;
        }

        const bars = points.slice(-50).map(p => {
            const score = Math.max(0, Math.min(100, Number(p.score || 0)));
            const h = Math.max(6, Math.round(score * 0.55));
            return `<span class="unified-spark-bar ${riskClass(p.risk)}" style="height:${h}px" title="score ${esc(score)}"></span>`;
        }).join("");

        el.innerHTML = `<div class="unified-spark-bars">${bars}</div>`;
    }

    function renderTimeline(data) {
        const body = document.getElementById("unified-timeline-body");
        if (!body) return;

        const rows = Array.isArray(data.timeline) ? data.timeline : [];

        renderSparkline(data.history_points || []);

        if (!rows.length) {
            body.innerHTML = `<tr><td colspan="6">No timeline rows found.</td></tr>`;
            return;
        }

        body.innerHTML = "";

        rows.slice(0, 250).forEach(row => {
            const status = row.status || row.risk || row.feedback_status || row.resolution_status || "—";
            const score = row.score ?? row.score_adjustment_points ?? "—";
            const message = row.message || row.error || row.action_type || row.command_type || "—";

            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${esc(row.time || "—")}</td>
                <td>${esc(row.source || "—")}</td>
                <td>${esc(row.pc_id || "—")}</td>
                <td><span class="unified-ml-pill ${riskClass(status)}">${esc(status)}</span></td>
                <td>${esc(score)}</td>
                <td title="${esc(message)}">${esc(short(message, 260))}</td>
            `;
            body.appendChild(tr);
        });
    }

    window.refreshUnifiedMlControlCenter = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_unified_ml_control_center !== "function") {
            setUnifiedStatus("Backend bridge missing: get_unified_ml_control_center", true);
            return;
        }

        try {
            setUnifiedStatus("Loading Unified ML Control Center...");

            const data = await window.pywebview.api.get_unified_ml_control_center();

            if (!data || data.ok === false) {
                setUnifiedStatus(data && data.error ? data.error : "Could not load Unified ML Control Center.", true);
                return;
            }

            UNIFIED_ML_STATE = data;
            renderSummary(data);
            renderDeviceSelect(data.devices || []);
            renderDevices(data.devices || []);

            setUnifiedStatus(`Unified ML loaded. Overall: ${(data.overall || "unknown").toUpperCase()}. Devices: ${data.device_count || 0}.`);

            setTimeout(window.refreshUnifiedMlTimeline, 300);

        } catch (err) {
            setUnifiedStatus(String(err), true);
        }
    };

    window.refreshUnifiedMlTimeline = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_ml_device_timeline !== "function") {
            setUnifiedStatus("Backend bridge missing: get_ml_device_timeline", true);
            return;
        }

        const select = document.getElementById("unified-ml-device-select");
        const pcId = select ? select.value : "";

        try {
            setUnifiedStatus(`Loading timeline${pcId ? " for " + pcId : ""}...`);

            const data = await window.pywebview.api.get_ml_device_timeline(pcId, 500);

            if (!data || data.ok === false) {
                setUnifiedStatus(data && data.error ? data.error : "Could not load timeline.", true);
                return;
            }

            renderTimeline(data);
            setUnifiedStatus(`Timeline loaded. Rows: ${data.count || 0}${pcId ? " | Device: " + pcId : ""}.`);

        } catch (err) {
            setUnifiedStatus(String(err), true);
        }
    };

    function setupPanelWhenVisible() {
        const pc = document.getElementById("pc-control-section");

        if (!pc || pc.style.display === "none") {
            return;
        }

        if (ensurePanel()) {
            const statusEl = document.getElementById("unified-ml-status-v1");
            if (statusEl && statusEl.textContent.includes("Waiting")) {
                window.refreshUnifiedMlControlCenter();
            }
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        setTimeout(setupPanelWhenVisible, 7500);
    });

    setInterval(setupPanelWhenVisible, 10000);
})();

// =====================================================
// ML SMART WORKER SELECTION + STALE PC_ID PANEL v1
// Read-only recommendations for best worker and bad PC_ID targets.
// =====================================================

(function () {
    const PANEL_ID = "ml-smart-worker-panel-v1";

    function esc(value) {
        return String(value === undefined || value === null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function short(value, max = 170) {
        value = String(value || "");
        return value.length > max ? value.slice(0, max) + "..." : value;
    }

    function riskClass(value) {
        value = String(value || "").toLowerCase();
        if (value.includes("critical") || value.includes("avoid") || value.includes("invalid")) return "critical";
        if (value.includes("high") || value.includes("watch") || value.includes("limited")) return "high";
        if (value.includes("medium") || value.includes("usable")) return "medium";
        if (value.includes("low") || value.includes("ready") || value.includes("preferred")) return "low";
        return "unknown";
    }

    function setStatus(message, bad = false) {
        const el = document.getElementById("ml-smart-worker-status-v1");
        if (!el) return;
        el.textContent = message || "";
        el.className = bad ? "ml-smart-worker-status bad" : "ml-smart-worker-status";
    }

    function ensurePanel() {
        if (document.getElementById(PANEL_ID)) return true;

        const pc = document.getElementById("pc-control-section");
        if (!pc) return false;

        const panel = document.createElement("div");
        panel.id = PANEL_ID;
        panel.className = "ml-smart-worker-panel";
        panel.innerHTML = `
            <div class="ml-smart-worker-header">
                <div>
                    <h3>ML Smart Worker Selection + Stale PC_ID Detector v1</h3>
                    <div class="ml-smart-worker-subtitle">
                        Read-only recommendations for best worker devices and bad/stale target names.
                    </div>
                </div>
                <div class="ml-smart-worker-controls">
                    <button class="btn btn-primary" onclick="refreshMlSmartWorkerPanel()">REFRESH SMART WORKERS</button>
                </div>
            </div>

            <div id="ml-smart-worker-status-v1" class="ml-smart-worker-status">
                Waiting for smart worker data...
            </div>

            <div class="ml-smart-worker-summary-grid">
                <div class="ml-smart-worker-card">
                    <div class="ml-smart-worker-label">Overall</div>
                    <div id="smart-worker-overall-value" class="ml-smart-worker-value">—</div>
                </div>
                <div class="ml-smart-worker-card">
                    <div class="ml-smart-worker-label">Workers</div>
                    <div id="smart-worker-count-value" class="ml-smart-worker-value">—</div>
                </div>
                <div class="ml-smart-worker-card">
                    <div class="ml-smart-worker-label">Preferred</div>
                    <div id="smart-worker-preferred-value" class="ml-smart-worker-value">—</div>
                </div>
                <div class="ml-smart-worker-card">
                    <div class="ml-smart-worker-label">Stale Targets</div>
                    <div id="smart-worker-stale-value" class="ml-smart-worker-value">—</div>
                </div>
            </div>

            <div class="ml-smart-worker-section-title">Worker Selection Ranking</div>
            <div class="ml-smart-worker-table-wrap">
                <table class="ghost-table ml-smart-worker-table">
                    <thead>
                        <tr>
                            <th>Device</th>
                            <th>Selection Score</th>
                            <th>Recommendation</th>
                            <th>Role</th>
                            <th>Status</th>
                            <th>Risk</th>
                            <th>Prediction</th>
                            <th>Completed</th>
                            <th>Failed</th>
                            <th>Pending</th>
                            <th>Reason</th>
                        </tr>
                    </thead>
                    <tbody id="ml-smart-worker-body">
                        <tr><td colspan="11">No smart worker data loaded.</td></tr>
                    </tbody>
                </table>
            </div>

            <div class="ml-smart-worker-section-title">Stale / Bad PC_ID Targets</div>
            <div class="ml-smart-worker-table-wrap">
                <table class="ghost-table ml-smart-worker-table">
                    <thead>
                        <tr>
                            <th>Target PC_ID</th>
                            <th>Severity</th>
                            <th>Pending</th>
                            <th>Failed</th>
                            <th>Completed</th>
                            <th>Issues</th>
                            <th>Recommendation</th>
                        </tr>
                    </thead>
                    <tbody id="ml-stale-target-body">
                        <tr><td colspan="7">No stale target data loaded.</td></tr>
                    </tbody>
                </table>
            </div>
        `;

        pc.appendChild(panel);
        return true;
    }

    function value(id, text, cls) {
        const el = document.getElementById(id);
        if (!el) return;
        el.textContent = text;
        if (cls) el.className = "ml-smart-worker-value " + cls;
    }

    function renderSummary(data) {
        value("smart-worker-overall-value", String(data.overall || "unknown").toUpperCase(), riskClass(data.overall));
        value("smart-worker-count-value", String(data.worker_count || 0));
        value("smart-worker-preferred-value", String(data.preferred_count || 0), Number(data.preferred_count || 0) > 0 ? "low" : "medium");
        value("smart-worker-stale-value", String(data.stale_target_count || 0), Number(data.stale_target_count || 0) > 0 ? "high" : "low");
    }

    function renderWorkers(workers) {
        const body = document.getElementById("ml-smart-worker-body");
        if (!body) return;

        workers = Array.isArray(workers) ? workers : [];

        if (!workers.length) {
            body.innerHTML = `<tr><td colspan="11">No workers or scored devices found yet.</td></tr>`;
            return;
        }

        body.innerHTML = "";

        workers.forEach(row => {
            const rec = row.recommendation || "unknown";
            const risk = row.risk || "unknown";

            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td><strong>${esc(row.pc_id || "—")}</strong></td>
                <td><strong>${esc(row.selection_score || 0)}%</strong></td>
                <td><span class="ml-smart-worker-pill ${riskClass(rec)}">${esc(rec)}</span></td>
                <td>${esc(row.role || "—")}</td>
                <td>${esc(row.worker_status || "—")}</td>
                <td><span class="ml-smart-worker-pill ${riskClass(risk)}">${esc(risk)}</span></td>
                <td>${esc(row.prediction || "—")}%</td>
                <td>${esc(row.completed || 0)}</td>
                <td>${esc(row.failed || 0)}</td>
                <td>${esc(row.pending || 0)}</td>
                <td title="${esc(row.reason || "")}">${esc(short(row.reason || "—", 220))}</td>
            `;
            body.appendChild(tr);
        });
    }

    function renderStaleTargets(rows) {
        const body = document.getElementById("ml-stale-target-body");
        if (!body) return;

        rows = Array.isArray(rows) ? rows : [];

        if (!rows.length) {
            body.innerHTML = `<tr><td colspan="7">No stale or bad PC_ID targets detected.</td></tr>`;
            return;
        }

        body.innerHTML = "";

        rows.forEach(row => {
            const issues = Array.isArray(row.issues) ? row.issues.join("; ") : String(row.issues || "");

            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td><strong>${esc(row.target_pc_id || "—")}</strong></td>
                <td><span class="ml-smart-worker-pill ${riskClass(row.severity)}">${esc(row.severity || "—")}</span></td>
                <td>${esc(row.pending || 0)}</td>
                <td>${esc(row.failed || 0)}</td>
                <td>${esc(row.completed || 0)}</td>
                <td title="${esc(issues)}">${esc(short(issues || "—", 220))}</td>
                <td title="${esc(row.recommendation || "")}">${esc(short(row.recommendation || "—", 260))}</td>
            `;
            body.appendChild(tr);
        });
    }

    window.refreshMlSmartWorkerPanel = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_ml_smart_workers !== "function") {
            setStatus("Backend bridge missing: get_ml_smart_workers", true);
            return;
        }

        try {
            setStatus("Loading smart worker recommendations...");

            const data = await window.pywebview.api.get_ml_smart_workers();

            if (!data || data.ok === false) {
                setStatus(data && data.error ? data.error : "Could not load smart workers.", true);
                renderWorkers([]);
                renderStaleTargets([]);
                return;
            }

            renderSummary(data);
            renderWorkers(data.workers || []);
            renderStaleTargets(data.stale_targets || []);

            setStatus(`Smart worker data loaded. Overall: ${(data.overall || "unknown").toUpperCase()}.`);

        } catch (err) {
            setStatus(String(err), true);
        }
    };

    function setupPanelWhenVisible() {
        const pc = document.getElementById("pc-control-section");

        if (!pc || pc.style.display === "none") {
            return;
        }

        if (ensurePanel()) {
            const statusEl = document.getElementById("ml-smart-worker-status-v1");
            if (statusEl && statusEl.textContent.includes("Waiting")) {
                window.refreshMlSmartWorkerPanel();
            }
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        setTimeout(setupPanelWhenVisible, 8000);
    });

    setInterval(setupPanelWhenVisible, 10000);
})();

// =====================================================
// ML BACKUP GUARD + UPDATE READINESS GATE PANEL v1
// Safe backup-only protection before future updates.
// =====================================================

(function () {
    const PANEL_ID = "ml-backup-guard-panel-v1";

    function esc(value) {
        return String(value === undefined || value === null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function short(value, max = 180) {
        value = String(value || "");
        return value.length > max ? value.slice(0, max) + "..." : value;
    }

    function riskClass(value) {
        value = String(value || "").toLowerCase();
        if (value.includes("critical") || value.includes("blocked") || value.includes("high")) return "critical";
        if (value.includes("medium") || value.includes("caution") || value.includes("recommended")) return "high";
        if (value.includes("ready") || value.includes("ok") || value.includes("low") || value.includes("false")) return "low";
        return "unknown";
    }

    function sizeText(bytes) {
        bytes = Number(bytes || 0);
        if (bytes >= 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + " MB";
        if (bytes >= 1024) return Math.round(bytes / 1024) + " KB";
        return bytes + " B";
    }

    function ageText(seconds) {
        if (seconds === null || seconds === undefined) return "—";
        seconds = Number(seconds || 0);
        if (seconds < 60) return Math.round(seconds) + "s";
        if (seconds < 3600) return Math.round(seconds / 60) + "m";
        if (seconds < 86400) return Math.round(seconds / 3600) + "h";
        return Math.round(seconds / 86400) + "d";
    }

    function setStatus(message, bad = false) {
        const el = document.getElementById("ml-backup-guard-status-v1");
        if (!el) return;
        el.textContent = message || "";
        el.className = bad ? "ml-backup-guard-status bad" : "ml-backup-guard-status";
    }

    function ensurePanel() {
        if (document.getElementById(PANEL_ID)) return true;

        const pc = document.getElementById("pc-control-section");
        if (!pc) return false;

        const panel = document.createElement("div");
        panel.id = PANEL_ID;
        panel.className = "ml-backup-guard-panel";
        panel.innerHTML = `
            <div class="ml-backup-guard-header">
                <div>
                    <h3>ML Backup Guard + Update Readiness Gate v1</h3>
                    <div class="ml-backup-guard-subtitle">
                        Backup-only protection layer before future updates. No restore, no repair, no destructive action.
                    </div>
                </div>
                <div class="ml-backup-guard-controls">
                    <button class="btn btn-primary" onclick="refreshMlBackupGuardPanel()">REFRESH GUARD</button>
                    <button class="btn btn-primary" onclick="createMlBackupGuardBackupFromPanel()">CREATE ML BACKUP</button>
                    <button class="btn btn-primary" onclick="runMlBackupGuardAutoFromPanel()">AUTO-RUN GUARD</button>
                </div>
            </div>

            <div id="ml-backup-guard-status-v1" class="ml-backup-guard-status">
                Waiting for ML Backup Guard...
            </div>

            <div class="ml-backup-guard-summary-grid">
                <div class="ml-backup-guard-card">
                    <div class="ml-backup-guard-label">Recommendation</div>
                    <div id="ml-backup-recommendation-value" class="ml-backup-guard-value">—</div>
                </div>
                <div class="ml-backup-guard-card">
                    <div class="ml-backup-guard-label">Preflight</div>
                    <div id="ml-backup-preflight-value" class="ml-backup-guard-value">—</div>
                </div>
                <div class="ml-backup-guard-card">
                    <div class="ml-backup-guard-label">Backups</div>
                    <div id="ml-backup-count-value" class="ml-backup-guard-value">—</div>
                </div>
                <div class="ml-backup-guard-card">
                    <div class="ml-backup-guard-label">Latest Age</div>
                    <div id="ml-backup-age-value" class="ml-backup-guard-value">—</div>
                </div>
                <div class="ml-backup-guard-card">
                    <div class="ml-backup-guard-label">Candidate Files</div>
                    <div id="ml-backup-files-value" class="ml-backup-guard-value">—</div>
                </div>
                <div class="ml-backup-guard-card">
                    <div class="ml-backup-guard-label">Candidate Size</div>
                    <div id="ml-backup-size-value" class="ml-backup-guard-value">—</div>
                </div>
                <div class="ml-backup-guard-card">
                    <div class="ml-backup-guard-label">Backup Folder</div>
                    <div id="ml-backup-folder-value" class="ml-backup-guard-value small">—</div>
                </div>
                <div class="ml-backup-guard-card">
                    <div class="ml-backup-guard-label">Latest Backup</div>
                    <div id="ml-backup-latest-value" class="ml-backup-guard-value small">—</div>
                </div>
            </div>

            <div class="ml-backup-guard-note">
                This only creates ZIP backups inside the main project folder. It does not restore, delete, repair, apply updates, or change permissions.
            </div>

            <div class="ml-backup-guard-section-title">Backup Recommendation</div>
            <div id="ml-backup-reason-box" class="ml-backup-guard-reason">
                No recommendation loaded.
            </div>

            <div class="ml-backup-guard-section-title">Backup List</div>
            <div class="ml-backup-guard-table-wrap">
                <table class="ghost-table ml-backup-guard-table">
                    <thead>
                        <tr>
                            <th>Backup ID</th>
                            <th>Reason</th>
                            <th>Files</th>
                            <th>Size</th>
                            <th>Preflight</th>
                            <th>Path</th>
                        </tr>
                    </thead>
                    <tbody id="ml-backup-guard-body">
                        <tr><td colspan="6">No backup data loaded.</td></tr>
                    </tbody>
                </table>
            </div>
        `;

        pc.appendChild(panel);
        return true;
    }

    function value(id, text, cls) {
        const el = document.getElementById(id);
        if (!el) return;
        el.textContent = text;
        if (cls) el.className = "ml-backup-guard-value " + cls;
    }

    function renderStatus(status, rec) {
        rec = rec || {};

        value("ml-backup-recommendation-value", rec.should_backup ? "BACKUP NEEDED" : "OK", rec.should_backup ? riskClass(rec.severity) : "low");
        value("ml-backup-preflight-value", String(rec.preflight_readiness || "unknown").toUpperCase(), riskClass(rec.preflight_readiness));
        value("ml-backup-count-value", String(status.backup_count || 0));
        value("ml-backup-age-value", ageText(status.latest_age_seconds));
        value("ml-backup-files-value", String(status.candidate_file_count || 0));
        value("ml-backup-size-value", sizeText(status.candidate_total_size_bytes || 0));
        value("ml-backup-folder-value", status.backup_dir || "—");
        value("ml-backup-latest-value", status.latest_backup ? (status.latest_backup.zip_name || status.latest_backup.backup_id || "—") : "none");

        const reason = document.getElementById("ml-backup-reason-box");
        if (reason) {
            reason.innerHTML = `
                <strong>${esc(rec.reason || "No recommendation loaded.")}</strong><br>
                <span>Severity: ${esc(rec.severity || "unknown")} | Should Backup: ${esc(rec.should_backup)}</span>
            `;
        }

        renderBackups(status.backups || []);
    }

    function renderBackups(rows) {
        const body = document.getElementById("ml-backup-guard-body");
        if (!body) return;

        rows = Array.isArray(rows) ? rows : [];

        if (!rows.length) {
            body.innerHTML = `<tr><td colspan="6">No ML Backup Guard backups found yet.</td></tr>`;
            return;
        }

        body.innerHTML = "";

        rows.slice(0, 100).forEach(row => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td><strong>${esc(row.backup_id || "—")}</strong></td>
                <td>${esc(row.reason || "—")}</td>
                <td>${esc(row.file_count || 0)}</td>
                <td>${esc(sizeText(row.size_bytes || 0))}</td>
                <td><span class="ml-backup-guard-pill ${riskClass(row.preflight_readiness)}">${esc(row.preflight_readiness || "—")}</span></td>
                <td title="${esc(row.zip_path || "")}">${esc(short(row.zip_path || "—", 420))}</td>
            `;
            body.appendChild(tr);
        });
    }

    window.refreshMlBackupGuardPanel = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_ml_backup_guard_status !== "function") {
            setStatus("Backend bridge missing: get_ml_backup_guard_status", true);
            return;
        }

        try {
            setStatus("Loading ML Backup Guard status...");

            const status = await window.pywebview.api.get_ml_backup_guard_status();

            if (!status || status.ok === false) {
                setStatus(status && status.error ? status.error : "Could not load backup status.", true);
                return;
            }

            let rec = {};
            if (window.pywebview.api.get_ml_backup_guard_recommendation) {
                rec = await window.pywebview.api.get_ml_backup_guard_recommendation();
            }

            renderStatus(status, rec && rec.ok !== false ? rec : {});
            setStatus(`Backup Guard loaded. Backups: ${status.backup_count || 0}.`);

        } catch (err) {
            setStatus(String(err), true);
        }
    };

    window.createMlBackupGuardBackupFromPanel = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.create_ml_backup_guard_backup !== "function") {
            setStatus("Backend bridge missing: create_ml_backup_guard_backup", true);
            return;
        }

        try {
            setStatus("Creating ML Backup Guard backup...");

            const data = await window.pywebview.api.create_ml_backup_guard_backup("manual_dashboard");

            if (!data || data.ok === false) {
                setStatus(data && data.error ? data.error : "Backup creation failed.", true);
                return;
            }

            setStatus(`Backup created: ${data.zip_path || "done"}`);
            setTimeout(window.refreshMlBackupGuardPanel, 700);

        } catch (err) {
            setStatus(String(err), true);
        }
    };

    window.runMlBackupGuardAutoFromPanel = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.run_ml_backup_guard_auto !== "function") {
            setStatus("Backend bridge missing: run_ml_backup_guard_auto", true);
            return;
        }

        try {
            setStatus("Running ML Backup Guard auto check...");

            const data = await window.pywebview.api.run_ml_backup_guard_auto();

            if (!data || data.ok === false) {
                setStatus(data && data.error ? data.error : "Backup Guard auto-run failed.", true);
                return;
            }

            setStatus(data.created ? `Auto backup created: ${(data.backup || {}).zip_path || "done"}` : "Auto-run complete. Backup not needed.");
            setTimeout(window.refreshMlBackupGuardPanel, 700);

        } catch (err) {
            setStatus(String(err), true);
        }
    };

    function setupPanelWhenVisible() {
        const pc = document.getElementById("pc-control-section");

        if (!pc || pc.style.display === "none") {
            return;
        }

        if (ensurePanel()) {
            const statusEl = document.getElementById("ml-backup-guard-status-v1");
            if (statusEl && statusEl.textContent.includes("Waiting")) {
                window.refreshMlBackupGuardPanel();
            }
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        setTimeout(setupPanelWhenVisible, 9000);
    });

    setInterval(setupPanelWhenVisible, 12000);
})();

// =====================================================
// ML CAPACITY FORECAST + WORKER LOAD PLANNER PANEL v1
// Safe read-only capacity planning for worker devices.
// =====================================================

(function () {
    const PANEL_ID = "ml-capacity-forecast-panel-v1";

    function esc(value) {
        return String(value === undefined || value === null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function short(value, max = 180) {
        value = String(value || "");
        return value.length > max ? value.slice(0, max) + "..." : value;
    }

    function riskClass(value) {
        value = String(value || "").toLowerCase();
        if (value.includes("blocked") || value.includes("avoid") || value.includes("critical")) return "critical";
        if (value.includes("watch") || value.includes("limited") || value.includes("high")) return "high";
        if (value.includes("good") || value.includes("medium")) return "medium";
        if (value.includes("ready") || value.includes("excellent") || value.includes("strong") || value.includes("low")) return "low";
        return "unknown";
    }

    function sizeText(bytes) {
        bytes = Number(bytes || 0);
        if (bytes >= 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + " MB";
        if (bytes >= 1024) return Math.round(bytes / 1024) + " KB";
        return bytes + " B";
    }

    function setStatus(message, bad = false) {
        const el = document.getElementById("ml-capacity-status-v1");
        if (!el) return;
        el.textContent = message || "";
        el.className = bad ? "ml-capacity-status bad" : "ml-capacity-status";
    }

    function ensurePanel() {
        if (document.getElementById(PANEL_ID)) return true;

        const pc = document.getElementById("pc-control-section");
        if (!pc) return false;

        const panel = document.createElement("div");
        panel.id = PANEL_ID;
        panel.className = "ml-capacity-panel";
        panel.innerHTML = `
            <div class="ml-capacity-header">
                <div>
                    <h3>ML Capacity Forecast + Worker Load Planner v1</h3>
                    <div class="ml-capacity-subtitle">
                        Read-only forecast for worker readiness, safe load, and estimated headroom.
                    </div>
                </div>
                <div class="ml-capacity-controls">
                    <button class="btn btn-primary" onclick="refreshMlCapacityForecastPanel()">REFRESH FORECAST</button>
                    <button class="btn btn-primary" onclick="exportMlCapacityForecastFromPanel()">EXPORT FORECAST</button>
                </div>
            </div>

            <div id="ml-capacity-status-v1" class="ml-capacity-status">
                Waiting for capacity forecast...
            </div>

            <div class="ml-capacity-summary-grid">
                <div class="ml-capacity-card">
                    <div class="ml-capacity-label">Overall</div>
                    <div id="ml-capacity-overall-value" class="ml-capacity-value">—</div>
                </div>
                <div class="ml-capacity-card">
                    <div class="ml-capacity-label">Devices</div>
                    <div id="ml-capacity-devices-value" class="ml-capacity-value">—</div>
                </div>
                <div class="ml-capacity-card">
                    <div class="ml-capacity-label">Suggested Safe Load</div>
                    <div id="ml-capacity-safe-load-value" class="ml-capacity-value">—</div>
                </div>
                <div class="ml-capacity-card">
                    <div class="ml-capacity-label">Estimated Headroom</div>
                    <div id="ml-capacity-headroom-value" class="ml-capacity-value">—</div>
                </div>
                <div class="ml-capacity-card">
                    <div class="ml-capacity-label">Preferred</div>
                    <div id="ml-capacity-preferred-value" class="ml-capacity-value">—</div>
                </div>
                <div class="ml-capacity-card">
                    <div class="ml-capacity-label">Watch</div>
                    <div id="ml-capacity-watch-value" class="ml-capacity-value">—</div>
                </div>
                <div class="ml-capacity-card">
                    <div class="ml-capacity-label">Avoid</div>
                    <div id="ml-capacity-avoid-value" class="ml-capacity-value">—</div>
                </div>
                <div class="ml-capacity-card">
                    <div class="ml-capacity-label">Running Profiles</div>
                    <div id="ml-capacity-running-value" class="ml-capacity-value">—</div>
                </div>
            </div>

            <div class="ml-capacity-note">
                This forecast is advisory only. It does not launch profiles, stop profiles, execute commands, change permissions, or modify worker behavior.
            </div>

            <div class="ml-capacity-section-title">Worker Capacity Plan</div>
            <div class="ml-capacity-table-wrap">
                <table class="ghost-table ml-capacity-table">
                    <thead>
                        <tr>
                            <th>Device</th>
                            <th>Capacity Score</th>
                            <th>Tier</th>
                            <th>Suggested Safe Load</th>
                            <th>Running</th>
                            <th>Headroom</th>
                            <th>Risk</th>
                            <th>Role</th>
                            <th>Pending</th>
                            <th>Failed</th>
                            <th>Success Rate</th>
                            <th>Advice</th>
                        </tr>
                    </thead>
                    <tbody id="ml-capacity-plan-body">
                        <tr><td colspan="12">No capacity data loaded.</td></tr>
                    </tbody>
                </table>
            </div>

            <div class="ml-capacity-section-title">Capacity Recommendations</div>
            <div class="ml-capacity-table-wrap">
                <table class="ghost-table ml-capacity-table">
                    <thead>
                        <tr>
                            <th>Severity</th>
                            <th>Message</th>
                            <th>Recommendation</th>
                        </tr>
                    </thead>
                    <tbody id="ml-capacity-recommendation-body">
                        <tr><td colspan="3">No recommendations loaded.</td></tr>
                    </tbody>
                </table>
            </div>

            <div class="ml-capacity-section-title">Exported Capacity Reports</div>
            <div class="ml-capacity-table-wrap">
                <table class="ghost-table ml-capacity-table">
                    <thead>
                        <tr>
                            <th>Name</th>
                            <th>Size</th>
                            <th>Modified</th>
                            <th>Path</th>
                        </tr>
                    </thead>
                    <tbody id="ml-capacity-report-body">
                        <tr><td colspan="4">No capacity reports loaded.</td></tr>
                    </tbody>
                </table>
            </div>
        `;

        pc.appendChild(panel);
        return true;
    }

    function value(id, text, cls) {
        const el = document.getElementById(id);
        if (!el) return;
        el.textContent = text;
        if (cls) el.className = "ml-capacity-value " + cls;
    }

    function renderSummary(data) {
        value("ml-capacity-overall-value", String(data.overall || "unknown").toUpperCase(), riskClass(data.overall));
        value("ml-capacity-devices-value", String(data.device_count || 0));
        value("ml-capacity-safe-load-value", String(data.total_suggested_safe_load || 0));
        value("ml-capacity-headroom-value", String(data.total_estimated_headroom || 0), Number(data.total_estimated_headroom || 0) > 0 ? "low" : "high");
        value("ml-capacity-preferred-value", String(data.preferred_count || 0), Number(data.preferred_count || 0) > 0 ? "low" : "high");
        value("ml-capacity-watch-value", String(data.watch_count || 0), Number(data.watch_count || 0) > 0 ? "high" : "low");
        value("ml-capacity-avoid-value", String(data.avoid_count || 0), Number(data.avoid_count || 0) > 0 ? "critical" : "low");
        value("ml-capacity-running-value", String(data.total_running_profiles || 0));
    }

    function renderPlans(plans) {
        const body = document.getElementById("ml-capacity-plan-body");
        if (!body) return;

        plans = Array.isArray(plans) ? plans : [];

        if (!plans.length) {
            body.innerHTML = `<tr><td colspan="12">No capacity plans found yet.</td></tr>`;
            return;
        }

        body.innerHTML = "";

        plans.forEach(row => {
            const tier = row.load_tier || "unknown";
            const risk = row.risk || "unknown";

            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td><strong>${esc(row.pc_id || "—")}</strong></td>
                <td><strong>${esc(row.capacity_score || 0)}%</strong></td>
                <td><span class="ml-capacity-pill ${riskClass(tier)}">${esc(tier)}</span></td>
                <td>${esc(row.suggested_safe_load || 0)}</td>
                <td>${esc(row.running_profiles || 0)}</td>
                <td><strong>${esc(row.estimated_headroom || 0)}</strong></td>
                <td><span class="ml-capacity-pill ${riskClass(risk)}">${esc(risk)}</span></td>
                <td>${esc(row.role || "—")}</td>
                <td>${esc(row.pending_commands || 0)}</td>
                <td>${esc(row.failed_commands || 0)}</td>
                <td>${esc(row.command_success_rate || 0)}%</td>
                <td title="${esc(row.advice || "")}">${esc(short(row.advice || "—", 260))}</td>
            `;
            body.appendChild(tr);
        });
    }

    function renderRecommendations(rows) {
        const body = document.getElementById("ml-capacity-recommendation-body");
        if (!body) return;

        rows = Array.isArray(rows) ? rows : [];

        if (!rows.length) {
            body.innerHTML = `<tr><td colspan="3">No capacity recommendations.</td></tr>`;
            return;
        }

        body.innerHTML = "";

        rows.forEach(row => {
            const severity = row.severity || "info";
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td><span class="ml-capacity-pill ${riskClass(severity)}">${esc(severity)}</span></td>
                <td title="${esc(row.message || "")}">${esc(short(row.message || "—", 260))}</td>
                <td title="${esc(row.recommendation || "")}">${esc(short(row.recommendation || "—", 320))}</td>
            `;
            body.appendChild(tr);
        });
    }

    function renderReports(rows) {
        const body = document.getElementById("ml-capacity-report-body");
        if (!body) return;

        rows = Array.isArray(rows) ? rows : [];

        if (!rows.length) {
            body.innerHTML = `<tr><td colspan="4">No exported capacity forecasts yet.</td></tr>`;
            return;
        }

        body.innerHTML = "";

        rows.slice(0, 50).forEach(row => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td><strong>${esc(row.name || "—")}</strong></td>
                <td>${esc(sizeText(row.size_bytes || 0))}</td>
                <td>${esc(row.modified_at || "—")}</td>
                <td title="${esc(row.path || "")}">${esc(short(row.path || "—", 420))}</td>
            `;
            body.appendChild(tr);
        });
    }

    window.refreshMlCapacityForecastPanel = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_ml_capacity_forecast !== "function") {
            setStatus("Backend bridge missing: get_ml_capacity_forecast", true);
            return;
        }

        try {
            setStatus("Loading ML capacity forecast...");

            const data = await window.pywebview.api.get_ml_capacity_forecast();

            if (!data || data.ok === false) {
                setStatus(data && data.error ? data.error : "Could not load capacity forecast.", true);
                return;
            }

            renderSummary(data);
            renderPlans(data.plans || []);
            renderRecommendations(data.recommendations || []);

            if (window.pywebview.api.get_ml_capacity_forecast_reports) {
                const reports = await window.pywebview.api.get_ml_capacity_forecast_reports();
                if (reports && reports.ok !== false) {
                    renderReports(reports.reports || []);
                }
            }

            setStatus(`Capacity forecast loaded. Overall: ${(data.overall || "unknown").toUpperCase()}.`);

        } catch (err) {
            setStatus(String(err), true);
        }
    };

    window.exportMlCapacityForecastFromPanel = async function () {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.export_ml_capacity_forecast !== "function") {
            setStatus("Backend bridge missing: export_ml_capacity_forecast", true);
            return;
        }

        try {
            setStatus("Exporting capacity forecast...");

            const data = await window.pywebview.api.export_ml_capacity_forecast();

            if (!data || data.ok === false) {
                setStatus(data && data.error ? data.error : "Export failed.", true);
                return;
            }

            setStatus(`Capacity forecast exported: ${data.path || "done"}`);
            setTimeout(window.refreshMlCapacityForecastPanel, 700);

        } catch (err) {
            setStatus(String(err), true);
        }
    };

    function setupPanelWhenVisible() {
        const pc = document.getElementById("pc-control-section");

        if (!pc || pc.style.display === "none") {
            return;
        }

        if (ensurePanel()) {
            const statusEl = document.getElementById("ml-capacity-status-v1");
            if (statusEl && statusEl.textContent.includes("Waiting")) {
                window.refreshMlCapacityForecastPanel();
            }
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        setTimeout(setupPanelWhenVisible, 9500);
    });

    setInterval(setupPanelWhenVisible, 12000);
})();

// =====================================================
// ML/RL ARCHITECTURE v2 PANEL
// BaseBrowseEnv-style safe ML/RL architecture.
// =====================================================

(function () {
    const PANEL_ID = "ml-rl-architecture-panel-v2";

    function esc(value) {
        return String(value === undefined || value === null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function short(value, max = 180) {
        value = String(value || "");
        return value.length > max ? value.slice(0, max) + "..." : value;
    }

    function cls(value) {
        value = String(value || "").toLowerCase();
        if (value.includes("false") || value.includes("disabled") || value.includes("error")) return "critical";
        if (value.includes("learning") || value.includes("training")) return "medium";
        if (value.includes("true") || value.includes("enabled") || value.includes("ok")) return "low";
        return "unknown";
    }

    function setStatus(message, bad = false) {
        const el = document.getElementById("ml-rl-status-v2");
        if (!el) return;
        el.textContent = message || "";
        el.className = bad ? "ml-rl-status-v2 bad" : "ml-rl-status-v2";
    }

    function ensurePanel() {
        if (document.getElementById(PANEL_ID)) return true;

        const pc = document.getElementById("pc-control-section");
        if (!pc) return false;

        const panel = document.createElement("div");
        panel.id = PANEL_ID;
        panel.className = "ml-rl-panel-v2";
        panel.innerHTML = `
            <div class="ml-rl-header-v2">
                <div>
                    <h3>ML/RL Architecture v2 Compatible</h3>
                    <div class="ml-rl-subtitle-v2">
                        Recreated BaseBrowseEnv-style architecture: observation space, action space, policy memory, behavior logs, and imitation dataset conversion.
                    </div>
                </div>
                <div class="ml-rl-controls-v2">
                    <button class="btn btn-primary" onclick="refreshMlRlArchitecture()">REFRESH RL</button>
                    <button class="btn btn-primary" onclick="enableMlRlArchitecture()">ENABLE RL</button>
                    <button class="btn btn-primary" onclick="disableMlRlArchitecture()">DISABLE RL</button>
                    <button class="btn btn-primary" onclick="runMlRlEpisode()">RUN EPISODE</button>
                    <button class="btn btn-primary" onclick="trainMlRlQ()">TRAIN Q</button>
                    <button class="btn btn-primary" onclick="loadMlRlDataset()">LOAD DATASET</button>
                    <button class="btn btn-primary" onclick="exportMlRlReport()">EXPORT RL REPORT</button>
                </div>
            </div>

            <div id="ml-rl-status-v2" class="ml-rl-status-v2">Waiting for ML/RL status...</div>

            <div class="ml-rl-summary-grid-v2">
                <div class="ml-rl-card-v2"><div class="ml-rl-label-v2">Enabled</div><div id="ml-rl-enabled-v2" class="ml-rl-value-v2">—</div></div>
                <div class="ml-rl-card-v2"><div class="ml-rl-label-v2">Mode</div><div id="ml-rl-mode-v2" class="ml-rl-value-v2 small">—</div></div>
                <div class="ml-rl-card-v2"><div class="ml-rl-label-v2">Q States</div><div id="ml-rl-qstates-v2" class="ml-rl-value-v2">—</div></div>
                <div class="ml-rl-card-v2"><div class="ml-rl-label-v2">Episodes</div><div id="ml-rl-episodes-v2" class="ml-rl-value-v2">—</div></div>
                <div class="ml-rl-card-v2"><div class="ml-rl-label-v2">Visited URLs</div><div id="ml-rl-urls-v2" class="ml-rl-value-v2">—</div></div>
                <div class="ml-rl-card-v2"><div class="ml-rl-label-v2">Success Rate</div><div id="ml-rl-success-v2" class="ml-rl-value-v2">—</div></div>
                <div class="ml-rl-card-v2"><div class="ml-rl-label-v2">Total Reward</div><div id="ml-rl-reward-v2" class="ml-rl-value-v2">—</div></div>
                <div class="ml-rl-card-v2"><div class="ml-rl-label-v2">Last Action</div><div id="ml-rl-last-v2" class="ml-rl-value-v2 small">—</div></div>
            </div>

            <div class="ml-rl-note-v2">
                Safety locks: authorized allowlist only, GET-only, no public engagement, no public chat, no evasion, no POST/forms, no self-modifying execution.
            </div>

            <div class="ml-rl-section-title-v2">Latest Episode</div>
            <div id="ml-rl-episode-box-v2" class="ml-rl-box-v2">No episode run yet.</div>

            <div class="ml-rl-section-title-v2">Behavior Dataset Preview</div>
            <div class="ml-rl-table-wrap-v2">
                <table class="ghost-table ml-rl-table-v2">
                    <thead>
                        <tr><th>State</th><th>Action</th><th>Reward</th><th>Success</th><th>URL</th><th>Target</th></tr>
                    </thead>
                    <tbody id="ml-rl-dataset-body-v2"><tr><td colspan="6">No dataset loaded.</td></tr></tbody>
                </table>
            </div>
        `;
        pc.appendChild(panel);
        return true;
    }

    function val(id, text, c) {
        const el = document.getElementById(id);
        if (!el) return;
        el.textContent = text;
        if (c) el.className = "ml-rl-value-v2 " + c;
    }

    function renderStatus(data) {
        const mem = data.memory_summary || {};
        val("ml-rl-enabled-v2", String(data.enabled), cls(String(data.enabled)));
        val("ml-rl-mode-v2", String(data.mode || "—").toUpperCase(), "low");
        val("ml-rl-qstates-v2", String(mem.q_state_count || 0));
        val("ml-rl-episodes-v2", String(mem.episode_count || 0));
        val("ml-rl-urls-v2", String(mem.url_count || 0));
        val("ml-rl-success-v2", String(mem.success_rate || 0) + "%", Number(mem.success_rate || 0) >= 80 ? "low" : "medium");
        val("ml-rl-reward-v2", String(mem.total_reward || 0));
        val("ml-rl-last-v2", mem.last_action || "—");
    }

    function renderEpisode(data) {
        const box = document.getElementById("ml-rl-episode-box-v2");
        if (!box) return;

        const ep = data.episode || {};
        const steps = ep.steps || [];
        const last = steps.length ? steps[steps.length - 1] : {};

        box.innerHTML = `
            <strong>Episode:</strong> ${esc(ep.episode_id || "—")} |
            <strong>Steps:</strong> ${esc(steps.length)} |
            <strong>Total Reward:</strong> ${esc(ep.total_reward || 0)}<br>
            <strong>Last URL:</strong> ${esc(last.url || "—")}<br>
            <strong>Last Action:</strong> ${esc(((last.prediction || {}).action) || "—")} |
            <strong>Target:</strong> ${esc(((last.action_result || {}).target_url) || "—")} |
            <strong>Reward:</strong> ${esc(last.reward || 0)}
        `;
    }

    function renderDataset(rows) {
        const body = document.getElementById("ml-rl-dataset-body-v2");
        if (!body) return;

        rows = Array.isArray(rows) ? rows : [];
        if (!rows.length) {
            body.innerHTML = `<tr><td colspan="6">No behavior samples yet.</td></tr>`;
            return;
        }

        body.innerHTML = "";
        rows.slice(-100).reverse().forEach(row => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td>${esc(row.state_key || "—")}</td>
                <td><strong>${esc(row.action || "—")}</strong></td>
                <td>${esc(row.reward || 0)}</td>
                <td>${esc(row.success)}</td>
                <td title="${esc(row.url || "")}">${esc(short(row.url || "—", 240))}</td>
                <td title="${esc(row.target_url || "")}">${esc(short(row.target_url || "—", 240))}</td>
            `;
            body.appendChild(tr);
        });
    }

    window.refreshMlRlArchitecture = async function () {
        ensurePanel();
        try {
            const data = await window.pywebview.api.get_ml_rl_architecture_status();
            if (!data || data.ok === false) {
                setStatus((data && data.error) || "Could not load ML/RL status.", true);
                return;
            }
            renderStatus(data);
            setStatus(`ML/RL loaded. Enabled: ${data.enabled}.`);
        } catch (err) {
            setStatus(String(err), true);
        }
    };

    window.enableMlRlArchitecture = async function () {
        ensurePanel();
        try {
            const data = await window.pywebview.api.set_ml_rl_architecture_enabled(true);
            if (!data || data.ok === false) {
                setStatus((data && data.error) || "Enable failed.", true);
                return;
            }
            setStatus("ML/RL Architecture enabled.");
            setTimeout(window.refreshMlRlArchitecture, 500);
        } catch (err) {
            setStatus(String(err), true);
        }
    };

    window.disableMlRlArchitecture = async function () {
        ensurePanel();
        try {
            const data = await window.pywebview.api.set_ml_rl_architecture_enabled(false);
            if (!data || data.ok === false) {
                setStatus((data && data.error) || "Disable failed.", true);
                return;
            }
            setStatus("ML/RL Architecture disabled.");
            setTimeout(window.refreshMlRlArchitecture, 500);
        } catch (err) {
            setStatus(String(err), true);
        }
    };

    window.runMlRlEpisode = async function () {
        ensurePanel();
        try {
            setStatus("Running ML/RL episode...");
            const data = await window.pywebview.api.run_ml_rl_architecture_episode(5);
            if (!data || data.ok === false) {
                setStatus((data && data.error) || (data && data.reason) || "Episode failed.", true);
                return;
            }
            renderEpisode(data);
            setStatus("ML/RL episode completed.");
            setTimeout(window.refreshMlRlArchitecture, 500);
        } catch (err) {
            setStatus(String(err), true);
        }
    };

    window.trainMlRlQ = async function () {
        ensurePanel();
        try {
            setStatus("Training safe Q policy...");
            const data = await window.pywebview.api.train_ml_rl_architecture_q(5, 5);
            if (!data || data.ok === false) {
                setStatus((data && data.error) || "Training failed.", true);
                return;
            }
            setStatus(`Q training completed. Episodes: ${data.results ? data.results.length : 0}.`);
            setTimeout(window.refreshMlRlArchitecture, 500);
        } catch (err) {
            setStatus(String(err), true);
        }
    };

    window.loadMlRlDataset = async function () {
        ensurePanel();
        try {
            const data = await window.pywebview.api.get_ml_rl_architecture_behavior_dataset();
            if (!data || data.ok === false) {
                setStatus((data && data.error) || "Dataset load failed.", true);
                return;
            }
            renderDataset(data.samples || []);
            setStatus(`Dataset loaded. Samples: ${data.sample_count || 0}.`);
        } catch (err) {
            setStatus(String(err), true);
        }
    };

    window.exportMlRlReport = async function () {
        ensurePanel();
        try {
            const data = await window.pywebview.api.export_ml_rl_architecture_report();
            if (!data || data.ok === false) {
                setStatus((data && data.error) || "Export failed.", true);
                return;
            }
            setStatus(`ML/RL report exported: ${data.path || "done"}.`);
        } catch (err) {
            setStatus(String(err), true);
        }
    };

    function setupPanelWhenVisible() {
        const pc = document.getElementById("pc-control-section");
        if (!pc || pc.style.display === "none") return;

        if (ensurePanel()) {
            const statusEl = document.getElementById("ml-rl-status-v2");
            if (statusEl && statusEl.textContent.includes("Waiting")) {
                window.refreshMlRlArchitecture();
            }
        }
    }

    document.addEventListener("DOMContentLoaded", function () {
        setTimeout(setupPanelWhenVisible, 11500);
    });
    setInterval(setupPanelWhenVisible, 12000);
})();

// =====================================================
// PATCH 003/004 - LAPTOP CODING + AUTO SYNC STATUS PANEL
// Patch 004 adds minimize + restore/maximize controls.
// =====================================================
(function () {
    const PANEL_ID = "patch-003-laptop-sync-status-panel";
    const BODY_CLASS = "patch-003-laptop-sync-status-ready";
    const STORAGE_KEY = "cometLaptopSyncPanelMinimized";

    function isMinimizedSaved() {
        try { return window.localStorage.getItem(STORAGE_KEY) === "1"; }
        catch (err) { return false; }
    }

    function saveMinimized(value) {
        try { window.localStorage.setItem(STORAGE_KEY, value ? "1" : "0"); }
        catch (err) {}
    }

    function formatAge(seconds) {
        if (seconds === undefined || seconds === null || isNaN(Number(seconds))) return "never";
        seconds = Math.max(0, Number(seconds));
        if (seconds < 60) return `${Math.round(seconds)}s ago`;
        const minutes = Math.floor(seconds / 60);
        if (minutes < 60) return `${minutes}m ago`;
        const hours = Math.floor(minutes / 60);
        const remMinutes = minutes % 60;
        return `${hours}h ${remMinutes}m ago`;
    }

    function stateLabel(status) {
        const state = String(status && status.state ? status.state : "unknown");
        if (state === "offline_waiting") return "Waiting for Main PC";
        if (state === "synced" || state === "synced_restart_requested") return "Synced";
        if (state === "synced_restart_failed") return "Synced, restart pending";
        if (state === "preparing") return "Checking";
        if (state === "no_status") return "Not started";
        if (state === "error") return "Status error";
        return state.replace(/_/g, " ");
    }

    function stateClass(status) {
        const state = String(status && status.state ? status.state : "unknown");
        if (state === "offline_waiting") return "waiting";
        if (state === "synced" || state === "synced_restart_requested") return "synced";
        if (state === "synced_restart_failed") return "warning";
        if (state === "preparing") return "checking";
        if (state === "no_status") return "warning";
        if (state === "error") return "error";
        return "unknown";
    }

    function setPanelMinimized(minimized) {
        const panel = document.getElementById(PANEL_ID);
        if (!panel) return;

        panel.classList.toggle("minimized", !!minimized);
        saveMinimized(!!minimized);

        const minBtn = document.getElementById("patch-003-sync-minimize-btn");
        const maxBtn = document.getElementById("patch-003-sync-maximize-btn");

        if (minBtn) {
            minBtn.disabled = !!minimized;
            minBtn.title = minimized ? "Panel is already minimized" : "Minimize panel";
        }

        if (maxBtn) {
            maxBtn.disabled = !minimized;
            maxBtn.title = minimized ? "Restore panel to normal size" : "Panel is already normal size";
        }
    }

    function ensurePanel() {
        let panel = document.getElementById(PANEL_ID);
        if (panel) return panel;

        panel = document.createElement("div");
        panel.id = PANEL_ID;
        panel.className = "patch-003-sync-panel checking";

        panel.innerHTML = `
            <div class="patch-003-sync-header">
                <div class="patch-003-sync-title-wrap">
                    <div class="patch-003-sync-title">Laptop Coding Sync</div>
                    <div class="patch-003-sync-subtitle" id="patch-003-sync-subtitle">Checking local sync status...</div>
                </div>

                <div class="patch-003-sync-controls">
                    <button type="button" class="patch-003-sync-control-btn" id="patch-003-sync-minimize-btn" title="Minimize panel">−</button>
                    <button type="button" class="patch-003-sync-control-btn" id="patch-003-sync-maximize-btn" title="Restore panel to normal size">□</button>
                    <button type="button" class="patch-003-sync-refresh" id="patch-003-sync-refresh-btn">Refresh</button>
                </div>
            </div>

            <div class="patch-003-sync-content" id="patch-003-sync-content">
                <div class="patch-003-sync-grid">
                    <div class="patch-003-sync-row">
                        <span>Main PC</span>
                        <strong id="patch-003-main-pc">Checking</strong>
                    </div>
                    <div class="patch-003-sync-row">
                        <span>Sync</span>
                        <strong id="patch-003-sync-state">Checking</strong>
                    </div>
                    <div class="patch-003-sync-row">
                        <span>Files Ready</span>
                        <strong id="patch-003-files-ready">-</strong>
                    </div>
                    <div class="patch-003-sync-row">
                        <span>Last Check</span>
                        <strong id="patch-003-last-check">-</strong>
                    </div>
                    <div class="patch-003-sync-row">
                        <span>Last Success</span>
                        <strong id="patch-003-last-success">-</strong>
                    </div>
                </div>

                <div class="patch-003-sync-message" id="patch-003-sync-message">
                    Waiting for local status...
                </div>
            </div>
        `;

        document.body.appendChild(panel);
        document.body.classList.add(BODY_CLASS);

        const refreshBtn = document.getElementById("patch-003-sync-refresh-btn");
        if (refreshBtn) refreshBtn.addEventListener("click", function () { refreshLaptopSyncStatus(true); });

        const minBtn = document.getElementById("patch-003-sync-minimize-btn");
        if (minBtn) minBtn.addEventListener("click", function () { setPanelMinimized(true); });

        const maxBtn = document.getElementById("patch-003-sync-maximize-btn");
        if (maxBtn) maxBtn.addEventListener("click", function () { setPanelMinimized(false); });

        const title = panel.querySelector(".patch-003-sync-title");
        if (title) {
            title.addEventListener("dblclick", function () {
                setPanelMinimized(!panel.classList.contains("minimized"));
            });
        }

        setPanelMinimized(isMinimizedSaved());
        return panel;
    }

    function setText(id, value) {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    }

    function renderStatus(status) {
        const panel = ensurePanel();
        const minimized = isMinimizedSaved();

        if (!status || status.ok === false) {
            panel.className = `patch-003-sync-panel error${minimized ? " minimized" : ""}`;
            setText("patch-003-sync-subtitle", "Could not read local sync status");
            setText("patch-003-main-pc", "Unknown");
            setText("patch-003-sync-state", "Error");
            setText("patch-003-files-ready", "-");
            setText("patch-003-last-check", "-");
            setText("patch-003-last-success", "-");
            setText("patch-003-sync-message", status && status.last_error ? String(status.last_error) : "Dashboard backend did not return sync status.");
            setPanelMinimized(minimized);
            return;
        }

        const cls = stateClass(status);
        panel.className = `patch-003-sync-panel ${cls}${minimized ? " minimized" : ""}`;

        const mainPc = String(status.main_pc_state || "unknown");
        const mainPcLabel = mainPc === "online" ? "Online" :
            mainPc === "offline" ? "Offline" :
            mainPc === "checking" ? "Checking" : "Unknown";

        setText("patch-003-main-pc", mainPcLabel);
        setText("patch-003-sync-state", stateLabel(status));
        setText("patch-003-files-ready", String(status.files_ready || 0));
        setText("patch-003-last-check", formatAge(status.age_seconds));

        let lastSuccessText = "never";
        if (status.last_success_at) {
            const now = Math.floor(Date.now() / 1000);
            lastSuccessText = formatAge(Math.max(0, now - Number(status.last_success_at)));
        }
        setText("patch-003-last-success", lastSuccessText);

        const skippedCount = Number(status.skipped_count || (status.skipped_files ? status.skipped_files.length : 0) || 0);
        let subtitle = "Laptop can keep working locally.";
        if (status.state === "offline_waiting") subtitle = "Main PC offline. Auto-sync is waiting.";
        else if (status.state === "synced" || status.state === "synced_restart_requested") subtitle = "Main PC received latest laptop files.";
        else if (status.state === "no_status") subtitle = "Start Laptop Coding Mode to create sync status.";

        if (skippedCount > 0) subtitle += ` ${skippedCount} file(s) skipped.`;
        setText("patch-003-sync-subtitle", subtitle);

        const msg = status.message || "";
        const coord = status.coordinator ? `Main PC: ${status.coordinator}` : "";
        const err = status.last_error && status.state !== "offline_waiting" ? ` ${status.last_error}` : "";
        setText("patch-003-sync-message", `${msg}${coord ? " | " + coord : ""}${err ? " | " + err : ""}`);

        setPanelMinimized(minimized);
    }

    async function refreshLaptopSyncStatus(manual) {
        ensurePanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_laptop_sync_status !== "function") {
            renderStatus({ ok: false, last_error: "Dashboard backend method missing: get_laptop_sync_status" });
            return;
        }

        try {
            if (manual) setText("patch-003-sync-state", "Refreshing");
            const status = await window.pywebview.api.get_laptop_sync_status();
            renderStatus(status);
        } catch (err) {
            renderStatus({ ok: false, last_error: String(err) });
        }
    }

    window.refreshLaptopSyncStatus = refreshLaptopSyncStatus;
    window.minimizeLaptopSyncPanel = function () { setPanelMinimized(true); };
    window.maximizeLaptopSyncPanel = function () { setPanelMinimized(false); };

    document.addEventListener("DOMContentLoaded", function () {
        ensurePanel();
        setTimeout(function () { refreshLaptopSyncStatus(false); }, 1200);
    });

    setInterval(function () { refreshLaptopSyncStatus(false); }, 10000);
})();

// === COMET PATCH 008 ADAPTIVE ML REFRESH BRAIN START ===
(function () {
    "use strict";

    if (window.__patch008AdaptiveMlRefreshLoaded) {
        return;
    }
    window.__patch008AdaptiveMlRefreshLoaded = true;

    const PANEL_ID = "patch008-smart-refresh-panel";
    const REFRESH_BTN_ID = "patch008-refresh-all-btn";
    const AUTO_BTN_ID = "patch008-auto-refresh-btn";
    const LAST_STATUS_ID = "patch008-refresh-last-status";
    const LIST_ID = "patch008-refresh-list";
    const MODEL_ID = "patch008-model-table";
    const BRAIN_KEY = "patch008.adaptiveRefreshBrain.v1";
    const MODE_KEY = "patch008.autoMode";
    const INTERVAL_KEY = "patch008.intervalMs";

    const DEFAULT_INTERVAL = 15000;
    const MIN_INTERVAL = 5000;
    const MAX_INTERVAL = 120000;

    const AUTO_MODES = ["off", "safe", "active"];

    const SECTION_CATALOG = [
        {
            key: "profiles",
            label: "Profiles table",
            group: "core",
            weight: 10,
            kind: "directProfiles"
        },
        {
            key: "workers",
            label: "PC Control devices",
            group: "pc_control",
            weight: 9,
            fn: "refreshWorkerTable"
        },
        {
            key: "proton",
            label: "Proton Accounts",
            group: "pc_control",
            weight: 9,
            fn: "refreshProtonAccountPanel"
        },
        {
            key: "sync",
            label: "Laptop Sync",
            group: "pc_control",
            weight: 8,
            fn: "refreshLaptopSyncStatus"
        },
        {
            key: "identity",
            label: "Profile Identity",
            group: "pc_control",
            weight: 7,
            fn: "refreshProfileIdentityReport"
        },
        {
            key: "diagnostics",
            label: "System Diagnostics",
            group: "pc_control",
            weight: 7,
            fn: "refreshSystemDiagnostics"
        },
        {
            key: "command_center",
            label: "Command Center",
            group: "pc_control",
            weight: 6,
            fn: "refreshCommandCenterPanel"
        },
        {
            key: "mobile_tasks",
            label: "Mobile Task Queue",
            group: "pc_control",
            weight: 6,
            fn: "refreshMobileTaskPanel"
        },
        {
            key: "permissions",
            label: "Device Permissions",
            group: "pc_control",
            weight: 6,
            fn: "refreshDevicePermissionsPanel"
        },
        {
            key: "security",
            label: "Security Audit",
            group: "pc_control",
            weight: 6,
            fn: "refreshSecurityAuditPanel"
        },
        {
            key: "backup",
            label: "Backup Manager",
            group: "pc_control",
            weight: 5,
            fn: "refreshBackupManagerPanel"
        },
        {
            key: "version",
            label: "Version Status",
            group: "pc_control",
            weight: 5,
            fn: "refreshVersionStatusPanel"
        },
        {
            key: "analytics",
            label: "Analytics",
            group: "analytics",
            weight: 7,
            fn: "refreshAnalytics"
        },
        {
            key: "targets",
            label: "Platform Targets",
            group: "targets",
            weight: 6,
            fn: "refreshPlatformTargets"
        },
        {
            key: "ml_reliability",
            label: "ML Reliability",
            group: "ml",
            weight: 6,
            fn: "refreshMlReliabilityPanel"
        },
        {
            key: "ml_history",
            label: "ML History Trends",
            group: "ml",
            weight: 5,
            fn: "refreshMlHistoryTrendsPanel"
        },
        {
            key: "ml_actions",
            label: "ML Action Queue",
            group: "ml",
            weight: 6,
            fn: "refreshMlActionsPanel"
        },
        {
            key: "ml_auto_resolver",
            label: "ML Auto Resolver",
            group: "ml",
            weight: 5,
            fn: "refreshMlAutoResolverPanel"
        },
        {
            key: "ml_smart_worker",
            label: "ML Smart Worker",
            group: "ml",
            weight: 5,
            fn: "refreshMlSmartWorkerPanel"
        },
        {
            key: "ml_backup_guard",
            label: "ML Backup Guard",
            group: "ml",
            weight: 5,
            fn: "refreshMlBackupGuardPanel"
        },
        {
            key: "ml_capacity",
            label: "ML Capacity Forecast",
            group: "ml",
            weight: 5,
            fn: "refreshMlCapacityForecastPanel"
        },
        {
            key: "ml_feedback",
            label: "ML Feedback Loop",
            group: "ml",
            weight: 5,
            fn: "refreshMlFeedbackPanel"
        },
        {
            key: "ml_executor",
            label: "ML Auto Executor",
            group: "ml",
            weight: 4,
            fn: "refreshMlAutoExecutorPanel"
        },
        {
            key: "ml_rl_architecture",
            label: "ML/RL Architecture",
            group: "ml",
            weight: 4,
            fn: "refreshMlRlArchitecture"
        },
        {
            key: "unified_ml",
            label: "Unified ML Control",
            group: "ml",
            weight: 5,
            fn: "refreshUnifiedMlControlCenter"
        },
        {
            key: "unified_timeline",
            label: "Unified ML Timeline",
            group: "ml",
            weight: 4,
            fn: "refreshUnifiedMlTimeline"
        }
    ];

    const state = {
        running: false,
        mode: readMode(),
        intervalMs: clampInt(localStorage.getItem(INTERVAL_KEY), DEFAULT_INTERVAL, MIN_INTERVAL, MAX_INTERVAL),
        timer: null,
        lastStartedAt: null,
        lastFinishedAt: null,
        lastDurationMs: 0,
        results: [],
        brain: loadBrain()
    };

    function clampInt(value, fallback, min, max) {
        let n = parseInt(value, 10);
        if (Number.isNaN(n)) n = fallback;
        n = Math.max(min, Math.min(max, n));
        return n;
    }

    function readMode() {
        const raw = String(localStorage.getItem(MODE_KEY) || "off").toLowerCase();
        return AUTO_MODES.includes(raw) ? raw : "off";
    }

    function defaultBrain() {
        const now = Date.now();
        const brain = {
            createdAt: now,
            updatedAt: now,
            totalRuns: 0,
            sections: {}
        };

        SECTION_CATALOG.forEach(section => {
            brain.sections[section.key] = {
                key: section.key,
                label: section.label,
                group: section.group,
                weight: section.weight,
                seen: false,
                exists: false,
                success: 0,
                fail: 0,
                skip: 0,
                avgMs: 0,
                lastStatus: "never",
                lastMessage: "Never refreshed",
                lastRunAt: 0,
                cooldownUntil: 0,
                priority: section.weight,
                missingStreak: 0,
                slowStreak: 0
            };
        });

        return brain;
    }

    function loadBrain() {
        try {
            const raw = localStorage.getItem(BRAIN_KEY);
            if (!raw) return defaultBrain();

            const parsed = JSON.parse(raw);
            const merged = defaultBrain();
            if (parsed && parsed.sections) {
                Object.keys(parsed.sections).forEach(key => {
                    if (merged.sections[key]) {
                        merged.sections[key] = Object.assign(merged.sections[key], parsed.sections[key]);
                    }
                });
            }
            merged.createdAt = parsed.createdAt || merged.createdAt;
            merged.updatedAt = parsed.updatedAt || merged.updatedAt;
            merged.totalRuns = parsed.totalRuns || 0;
            return merged;
        } catch (e) {
            console.log("[Adaptive Refresh] Could not load brain, resetting:", e);
            return defaultBrain();
        }
    }

    function saveBrain() {
        try {
            state.brain.updatedAt = Date.now();
            localStorage.setItem(BRAIN_KEY, JSON.stringify(state.brain));
        } catch (e) {
            console.log("[Adaptive Refresh] Could not save brain:", e);
        }
    }

    function $(id) {
        return document.getElementById(id);
    }

    function escapeHtml(value) {
        return String(value === undefined || value === null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    function formatClock(ts) {
        if (!ts) return "Never";
        try {
            return new Date(ts).toLocaleTimeString();
        } catch (e) {
            return "Unknown";
        }
    }

    function formatDuration(ms) {
        if (!ms && ms !== 0) return "—";
        if (ms < 1000) return `${Math.round(ms)}ms`;
        return `${(ms / 1000).toFixed(1)}s`;
    }

    function activeTabName() {
        try {
            const active = document.querySelector(".nav-links li.active");
            return String(active ? active.textContent || "" : "").trim().toLowerCase();
        } catch (e) {
            return "";
        }
    }

    function getSectionMeta(key) {
        return SECTION_CATALOG.find(section => section.key === key) || null;
    }

    function getRefreshFunction(name) {
        const candidate = window[name];
        return typeof candidate === "function" ? candidate : null;
    }

    function functionExists(section) {
        if (section.kind === "directProfiles") {
            return !!(
                window.pywebview &&
                window.pywebview.api &&
                typeof window.pywebview.api.get_profile_data === "function" &&
                (typeof window.renderProfileTable === "function" || typeof renderProfileTable === "function")
            );
        }
        return !!getRefreshFunction(section.fn);
    }

    function updateBrainAfterRun(section, status, message, durationMs) {
        const item = state.brain.sections[section.key];
        if (!item) return;

        const now = Date.now();
        item.seen = true;
        item.lastRunAt = now;
        item.lastStatus = status;
        item.lastMessage = message || "";
        item.exists = status !== "missing";

        if (status === "ok") {
            item.success += 1;
            item.missingStreak = 0;
            item.slowStreak = durationMs > 2500 ? (item.slowStreak + 1) : 0;
            item.avgMs = item.avgMs ? Math.round((item.avgMs * 0.75) + (durationMs * 0.25)) : durationMs;
        } else if (status === "missing") {
            item.skip += 1;
            item.missingStreak += 1;
            item.cooldownUntil = now + Math.min(10 * 60 * 1000, (item.missingStreak + 1) * 60 * 1000);
        } else if (status === "skip") {
            item.skip += 1;
        } else {
            item.fail += 1;
            item.cooldownUntil = now + Math.min(5 * 60 * 1000, (item.fail + 1) * 20 * 1000);
        }

        // Small RL-style score:
        // success raises priority, missing/slow/failure lowers it temporarily.
        const total = item.success + item.fail + item.skip;
        const successRate = total ? (item.success / total) : 0;
        const speedPenalty = item.avgMs > 3000 ? 2 : (item.avgMs > 1500 ? 1 : 0);
        const missingPenalty = Math.min(4, item.missingStreak);
        const failPenalty = Math.min(3, item.fail);
        item.priority = Math.max(
            1,
            Math.round((section.weight * 0.65) + (successRate * 5) - speedPenalty - missingPenalty - (failPenalty * 0.25))
        );

        saveBrain();
    }

    function addResult(section, ok, status, message, ms) {
        state.results.push({
            time: new Date().toLocaleTimeString(),
            key: section.key,
            group: section.group,
            name: section.label,
            ok: !!ok,
            status,
            message: message || (ok ? "Refreshed" : "Skipped"),
            ms: ms || 0
        });

        if (state.results.length > 80) {
            state.results = state.results.slice(-80);
        }
    }

    async function refreshProfilesDirectly() {
        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_profile_data !== "function") {
            throw new Error("get_profile_data unavailable");
        }

        const profiles = await window.pywebview.api.get_profile_data();

        if (typeof window.renderProfileTable === "function") {
            window.renderProfileTable(Array.isArray(profiles) ? profiles : []);
        } else if (typeof renderProfileTable === "function") {
            renderProfileTable(Array.isArray(profiles) ? profiles : []);
        } else {
            throw new Error("renderProfileTable unavailable");
        }
    }

    async function runSection(section, reason) {
        const started = Date.now();

        try {
            if (!functionExists(section)) {
                const ms = Date.now() - started;
                updateBrainAfterRun(section, "missing", section.kind === "directProfiles" ? "profile refresh bridge missing" : `${section.fn} missing`, ms);
                addResult(section, false, "missing", section.kind === "directProfiles" ? "Profile refresh bridge missing" : `${section.fn} missing`, ms);
                return false;
            }

            if (section.kind === "directProfiles") {
                await refreshProfilesDirectly();
            } else {
                const fn = getRefreshFunction(section.fn);
                const result = fn();
                if (result && typeof result.then === "function") {
                    await result;
                }
            }

            // Give dynamic panels a tiny render window.
            await sleep(150);

            const ms = Date.now() - started;
            updateBrainAfterRun(section, "ok", reason || "Done", ms);
            addResult(section, true, "ok", reason || "Done", ms);
            return true;

        } catch (err) {
            const ms = Date.now() - started;
            const msg = String(err && err.message ? err.message : err || "Failed");
            console.log(`[Adaptive Refresh] ${section.label} failed:`, err);
            updateBrainAfterRun(section, "fail", msg, ms);
            addResult(section, false, "fail", msg, ms);
            return false;
        }
    }

    function shouldRefreshSection(section, source) {
        const item = state.brain.sections[section.key] || {};
        const now = Date.now();
        const tab = activeTabName();

        if (source === "manual-all" || source === "manual-button" || source === "manual-panel") {
            return true;
        }

        if (item.cooldownUntil && item.cooldownUntil > now) {
            return false;
        }

        if (!functionExists(section) && item.missingStreak >= 3) {
            return false;
        }

        // Safe mode refreshes critical/current-tab sections only.
        if (state.mode === "safe") {
            if (section.group === "core") return true;
            if (tab.includes("pc control") && section.group === "pc_control") return true;
            if (tab.includes("analytics") && section.group === "analytics") return true;
            if (tab.includes("targets") && section.group === "targets") return true;
            return section.priority >= 8;
        }

        // Active mode refreshes more, but still respects learned priority.
        if (state.mode === "active") {
            return section.priority >= 3 || section.group === "core";
        }

        return false;
    }

    function sortSectionsForRefresh(source) {
        const now = Date.now();
        const tab = activeTabName();

        function tabBoost(section) {
            if (tab.includes("pc control") && section.group === "pc_control") return 4;
            if (tab.includes("analytics") && section.group === "analytics") return 4;
            if (tab.includes("targets") && section.group === "targets") return 4;
            return 0;
        }

        return SECTION_CATALOG
            .filter(section => shouldRefreshSection(section, source))
            .sort((a, b) => {
                const ai = state.brain.sections[a.key] || {};
                const bi = state.brain.sections[b.key] || {};
                const ascore = (ai.priority || a.weight) + tabBoost(a) - ((now - (ai.lastRunAt || 0)) < 4000 ? 2 : 0);
                const bscore = (bi.priority || b.weight) + tabBoost(b) - ((now - (bi.lastRunAt || 0)) < 4000 ? 2 : 0);
                return bscore - ascore;
            });
    }

    async function refreshAllDashboard(source) {
        ensureAdaptiveRefreshControls();

        if (state.running) {
            renderStatus("Refresh already running. Waiting for current refresh to finish...", false);
            return;
        }

        state.running = true;
        state.lastStartedAt = Date.now();
        state.results = [];
        state.brain.totalRuns += 1;
        setButtonState();
        renderStatus(`Adaptive refresh running (${source || "manual"})...`, false);

        const selected = sortSectionsForRefresh(source || "manual-all");
        let okCount = 0;
        let skipCount = 0;

        if (!selected.length) {
            state.running = false;
            state.lastFinishedAt = Date.now();
            state.lastDurationMs = state.lastFinishedAt - state.lastStartedAt;
            renderStatus("No sections selected by adaptive refresh brain. Use manual REFRESH ALL to force refresh.", true);
            return;
        }

        for (const section of selected) {
            const ok = await runSection(section, source || "manual");
            if (ok) okCount += 1;
            else skipCount += 1;
            await sleep(120);
        }

        // Record cooled-down sections as skipped for user visibility on manual all.
        if ((source || "").startsWith("manual")) {
            SECTION_CATALOG.forEach(section => {
                if (!selected.some(item => item.key === section.key)) {
                    addResult(section, false, "skip", "Skipped by adaptive policy", 0);
                }
            });
        }

        state.lastFinishedAt = Date.now();
        state.lastDurationMs = state.lastFinishedAt - state.lastStartedAt;
        state.running = false;
        saveBrain();

        if (
            typeof window.getAdaptiveRefreshBrainState === "function" &&
            typeof window.recordAdaptiveRefreshRun === "function"
        ) {
            try {
                await window.recordAdaptiveRefreshRun({
                    force: true,
                    sourceOverride: source || "manual-all",
                    refreshSnapshot: true
                });
            } catch (e) {
                console.log("[Adaptive Refresh] backend history write failed:", e);
            }
        }

        const msg = `Adaptive refresh complete: ${okCount} updated, ${skipCount} skipped. Mode: ${state.mode.toUpperCase()}.`;
        renderStatus(msg, false);
        console.log("[Adaptive Refresh]", msg, state.results, state.brain);
    }

    function setMode(nextMode) {
        let mode = String(nextMode || "").toLowerCase();

        if (!AUTO_MODES.includes(mode)) {
            const currentIndex = AUTO_MODES.indexOf(state.mode);
            mode = AUTO_MODES[(currentIndex + 1) % AUTO_MODES.length];
        }

        state.mode = mode;
        localStorage.setItem(MODE_KEY, state.mode);

        if (state.timer) {
            clearInterval(state.timer);
            state.timer = null;
        }

        if (state.mode !== "off") {
            state.timer = setInterval(function () {
                if (!state.running) {
                    refreshAllDashboard("auto-" + state.mode);
                }
            }, state.intervalMs);
        }

        renderStatus(`Auto refresh mode: ${state.mode.toUpperCase()} · interval ${Math.round(state.intervalMs / 1000)}s.`, false);
        setButtonState();
    }

    function saveIntervalFromInput() {
        const input = $("patch008-refresh-interval");
        const seconds = clampInt(input ? input.value : 15, 15, 5, 120);
        state.intervalMs = seconds * 1000;
        localStorage.setItem(INTERVAL_KEY, String(state.intervalMs));

        if (state.mode !== "off") {
            setMode(state.mode);
        } else {
            renderStatus(`Refresh interval saved: ${seconds}s.`, false);
        }
    }

    function resetBrain() {
        state.brain = defaultBrain();
        saveBrain();
        state.results = [];
        renderStatus("Adaptive refresh brain reset.", false);
    }

    function setButtonState() {
        const refreshBtn = $(REFRESH_BTN_ID);
        const autoBtn = $(AUTO_BTN_ID);
        const intervalInput = $("patch008-refresh-interval");

        if (refreshBtn) {
            refreshBtn.disabled = !!state.running;
            refreshBtn.textContent = state.running ? "REFRESHING..." : "REFRESH ALL";
        }

        if (autoBtn) {
            autoBtn.textContent = `AUTO: ${state.mode.toUpperCase()}`;
            autoBtn.classList.toggle("patch008-auto-on", state.mode !== "off");
            autoBtn.classList.toggle("patch008-auto-off", state.mode === "off");
            autoBtn.classList.toggle("patch008-auto-active", state.mode === "active");
        }

        if (intervalInput) {
            intervalInput.value = String(Math.round(state.intervalMs / 1000));
        }
    }

    function renderStatus(message, bad) {
        ensureAdaptiveRefreshControls();

        const status = $(LAST_STATUS_ID);
        if (status) {
            status.textContent = message || "Ready.";
            status.className = bad ? "patch008-refresh-status bad" : "patch008-refresh-status";
        }

        const last = $("patch008-last-run");
        if (last) {
            last.textContent = `Last run: ${formatClock(state.lastFinishedAt)} · Duration: ${formatDuration(state.lastDurationMs)} · Mode: ${state.mode.toUpperCase()}`;
        }

        renderResultsTable();
        renderModelTable();
        setButtonState();
    }

    function renderResultsTable() {
        const list = $(LIST_ID);
        if (!list) return;

        const rows = state.results.slice(-22).reverse();
        if (!rows.length) {
            list.innerHTML = `<tr><td colspan="5">No refresh run yet.</td></tr>`;
            return;
        }

        list.innerHTML = rows.map(item => `
            <tr>
                <td>${escapeHtml(item.time || "")}</td>
                <td>${escapeHtml(item.name || "")}</td>
                <td>${escapeHtml(item.group || "")}</td>
                <td><span class="patch008-pill ${item.status || (item.ok ? "ok" : "skip")}">${escapeHtml((item.status || (item.ok ? "ok" : "skip")).toUpperCase())}</span></td>
                <td>${escapeHtml(item.message || "")} <span class="patch008-muted">(${formatDuration(item.ms || 0)})</span></td>
            </tr>
        `).join("");
    }

    function renderModelTable() {
        const table = $(MODEL_ID);
        if (!table) return;

        const rows = Object.values(state.brain.sections || {})
            .sort((a, b) => (b.priority || 0) - (a.priority || 0))
            .slice(0, 12);

        table.innerHTML = rows.map(item => `
            <tr>
                <td>${escapeHtml(item.label || item.key)}</td>
                <td>${escapeHtml(item.group || "")}</td>
                <td>${escapeHtml(String(item.priority || 0))}</td>
                <td>${escapeHtml(String(item.success || 0))}/${escapeHtml(String(item.fail || 0))}/${escapeHtml(String(item.skip || 0))}</td>
                <td>${escapeHtml(item.lastStatus || "never")}</td>
            </tr>
        `).join("");
    }

    function ensureTopBarButton() {
        const controls = document.querySelector(".session-controls") || document.querySelector(".top-bar");
        if (!controls) return;

        if (!$(REFRESH_BTN_ID)) {
            const refreshBtn = document.createElement("button");
            refreshBtn.id = REFRESH_BTN_ID;
            refreshBtn.type = "button";
            refreshBtn.className = "btn btn-secondary patch008-refresh-all-btn";
            refreshBtn.textContent = "REFRESH ALL";
            refreshBtn.onclick = function () {
                refreshAllDashboard("manual-button");
            };
            controls.appendChild(refreshBtn);
        }

        if (!$(AUTO_BTN_ID)) {
            const autoBtn = document.createElement("button");
            autoBtn.id = AUTO_BTN_ID;
            autoBtn.type = "button";
            autoBtn.className = "btn btn-secondary patch008-auto-refresh-btn";
            autoBtn.onclick = function () {
                setMode();
            };
            controls.appendChild(autoBtn);
        }
    }

    function ensurePanel() {
        const pc = $("pc-control-section");
        if (!pc || $(PANEL_ID)) return;

        const panel = document.createElement("div");
        panel.id = PANEL_ID;
        panel.className = "patch008-smart-refresh-panel";

        panel.innerHTML = `
            <div class="patch008-refresh-header">
                <div>
                    <h3>Adaptive ML/RL Refresh Brain</h3>
                    <div class="patch008-refresh-subtitle">
                        Learns which dashboard sections exist, tracks refresh health, and prioritizes panels without touching automation.
                    </div>
                </div>
                <div class="patch008-refresh-actions">
                    <button type="button" class="btn btn-primary" onclick="window.refreshAllDashboardNow()">REFRESH ALL</button>
                    <button type="button" class="btn btn-secondary" onclick="window.toggleAdaptiveRefreshMode()">AUTO MODE</button>
                    <button type="button" class="btn btn-secondary" onclick="window.resetAdaptiveRefreshBrain()">RESET BRAIN</button>
                </div>
            </div>

            <div class="patch008-refresh-control-row">
                <label>
                    Auto interval seconds
                    <input id="patch008-refresh-interval" class="patch008-refresh-input" type="number" min="5" max="120" value="${Math.round(state.intervalMs / 1000)}">
                </label>
                <button type="button" class="btn btn-secondary" onclick="window.saveAdaptiveRefreshInterval()">SAVE INTERVAL</button>
                <span id="patch008-last-run" class="patch008-last-run">Last run: Never</span>
            </div>

            <div class="patch008-mode-help">
                <strong>OFF</strong> manual only · <strong>SAFE</strong> current tab + critical panels · <strong>ACTIVE</strong> broader adaptive refresh
            </div>

            <div id="${LAST_STATUS_ID}" class="patch008-refresh-status">Ready.</div>

            <div class="patch008-grid">
                <div>
                    <div class="patch008-table-title">Latest Refresh Run</div>
                    <div class="patch008-refresh-table-wrap">
                        <table class="ghost-table patch008-refresh-table">
                            <thead>
                                <tr>
                                    <th>Time</th>
                                    <th>Section</th>
                                    <th>Group</th>
                                    <th>Status</th>
                                    <th>Message</th>
                                </tr>
                            </thead>
                            <tbody id="${LIST_ID}">
                                <tr><td colspan="5">No refresh run yet.</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <div>
                    <div class="patch008-table-title">Learned Section Priority</div>
                    <div class="patch008-refresh-table-wrap">
                        <table class="ghost-table patch008-model-table">
                            <thead>
                                <tr>
                                    <th>Section</th>
                                    <th>Group</th>
                                    <th>Score</th>
                                    <th>OK/F/S</th>
                                    <th>Last</th>
                                </tr>
                            </thead>
                            <tbody id="${MODEL_ID}">
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        `;

        const firstChild = pc.firstElementChild;
        if (firstChild) {
            pc.insertBefore(panel, firstChild.nextSibling);
        } else {
            pc.appendChild(panel);
        }

        renderModelTable();
    }

    function ensureAdaptiveRefreshControls() {
        ensureTopBarButton();
        ensurePanel();
        setButtonState();
    }

    window.refreshAllDashboardNow = function () {
        return refreshAllDashboard("manual-panel");
    };

    window.toggleAdaptiveRefreshMode = function () {
        setMode();
    };

    window.saveAdaptiveRefreshInterval = saveIntervalFromInput;

    window.resetAdaptiveRefreshBrain = resetBrain;

    window.getAdaptiveRefreshBrainState = function () {
        return {
            running: state.running,
            mode: state.mode,
            intervalMs: state.intervalMs,
            lastFinishedAt: state.lastFinishedAt,
            lastDurationMs: state.lastDurationMs,
            results: state.results.slice(),
            brain: JSON.parse(JSON.stringify(state.brain || {}))
        };
    };

    // Backward-compatible names from Patch 007, so older buttons remain harmless if cached.
    window.toggleSmartAutoRefresh = window.toggleAdaptiveRefreshMode;
    window.saveSmartRefreshInterval = window.saveAdaptiveRefreshInterval;
    window.getSmartRefreshState = window.getAdaptiveRefreshBrainState;

    document.addEventListener("DOMContentLoaded", function () {
        setTimeout(function () {
            ensureAdaptiveRefreshControls();
            renderStatus(`Ready. Auto mode: ${state.mode.toUpperCase()}.`, false);
            if (state.mode !== "off") {
                setMode(state.mode);
            }
        }, 1200);
    });

    setInterval(function () {
        ensureAdaptiveRefreshControls();
    }, 5000);

})();
// === COMET PATCH 008 ADAPTIVE ML REFRESH BRAIN END ===

// === COMET PATCH 009 BACKEND REFRESH SNAPSHOT UI START ===
(function () {
    "use strict";

    if (window.__patch009BackendSnapshotLoaded) return;
    window.__patch009BackendSnapshotLoaded = true;

    const PANEL_ID = "patch009-backend-snapshot-panel";
    const STATUS_ID = "patch009-snapshot-status";
    const CARDS_ID = "patch009-snapshot-cards";
    const RECS_ID = "patch009-snapshot-recommendations";
    const HISTORY_ID = "patch009-refresh-history-body";
    let lastRecordedRefreshAt = 0;

    function $(id) { return document.getElementById(id); }

    function esc(value) {
        return String(value === undefined || value === null ? "" : value)
            .replace(/&/g, "&amp;").replace(/</g, "&lt;")
            .replace(/>/g, "&gt;").replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function setStatus(message, bad) {
        ensureBackendSnapshotPanel();
        const status = $(STATUS_ID);
        if (!status) return;
        status.textContent = message || "Ready.";
        status.className = bad ? "patch009-status bad" : "patch009-status";
    }

    function renderCards(snapshot) {
        const cards = $(CARDS_ID);
        if (!cards) return;

        const p = snapshot.profiles || {};
        const proton = snapshot.proton || {};
        const refresh = snapshot.refresh || {};
        const pc = snapshot.pc || {};
        const sync = snapshot.laptop_sync || {};
        const runtime = snapshot.runtime || {};
        const syncState = sync.state || sync.main_pc_state || (sync.ok ? "ok" : "unknown");

        cards.innerHTML = `
            <div class="patch009-card"><div class="patch009-card-label">Profiles</div><div class="patch009-card-value">${esc(p.total || 0)}</div><div class="patch009-card-sub">Running ${esc(p.running || 0)} · Offline ${esc(p.offline || 0)}</div></div>
            <div class="patch009-card"><div class="patch009-card-label">Proton Assigned</div><div class="patch009-card-value">${esc(proton.assigned_profiles || 0)}</div><div class="patch009-card-sub">Unassigned ${esc(proton.unassigned_profiles || 0)} · Accounts ${esc(proton.account_count || 0)}</div></div>
            <div class="patch009-card"><div class="patch009-card-label">Coordinator</div><div class="patch009-card-value small ${pc.coordinator_online ? "good" : "warn"}">${pc.coordinator_online ? "ONLINE" : "LOCAL"}</div><div class="patch009-card-sub">${esc(pc.device_type || "auto")} · ${esc(pc.pc_id || "")}</div></div>
            <div class="patch009-card"><div class="patch009-card-label">Laptop Sync</div><div class="patch009-card-value small">${esc(syncState)}</div><div class="patch009-card-sub">${esc(sync.message || sync.last_error || "")}</div></div>
            <div class="patch009-card"><div class="patch009-card-label">Refresh History</div><div class="patch009-card-value">${esc(refresh.history_count || 0)}</div><div class="patch009-card-sub">Fail ${esc(refresh.recent_failures || 0)} · Missing ${esc(refresh.recent_missing || 0)} · Slow ${esc(refresh.recent_slow || 0)}</div></div>
            <div class="patch009-card"><div class="patch009-card-label">Runtime</div><div class="patch009-card-value">${esc(runtime.active_session_count || 0)}</div><div class="patch009-card-sub">Active profile sessions</div></div>
        `;
    }

    function renderRecommendations(snapshot) {
        const recs = $(RECS_ID);
        if (!recs) return;
        const items = Array.isArray(snapshot.recommendations) ? snapshot.recommendations : [];
        if (!items.length) {
            recs.innerHTML = `<div class="patch009-empty">No recommendations yet.</div>`;
            return;
        }

        recs.innerHTML = items.map(item => `
            <div class="patch009-rec ${esc(item.level || "info")}">
                <span class="patch009-rec-pill">${esc(String(item.level || "info").toUpperCase())}</span>
                <div><strong>${esc(item.title || "Recommendation")}</strong><p>${esc(item.detail || "")}</p>${item.action ? `<small>${esc(item.action)}</small>` : ""}</div>
            </div>
        `).join("");
    }

    function renderHistory(snapshot) {
        const body = $(HISTORY_ID);
        if (!body) return;
        const history = Array.isArray(snapshot.refresh_history) ? snapshot.refresh_history : [];

        if (!history.length) {
            body.innerHTML = `<tr><td colspan="7">No backend refresh history yet. Click REFRESH ALL once.</td></tr>`;
            return;
        }

        body.innerHTML = history.slice(0, 12).map(row => `
            <tr>
                <td>${esc(row.created_at || "")}</td>
                <td>${esc(row.mode || "")}</td>
                <td>${esc(row.duration_ms || 0)}ms</td>
                <td>${esc(row.updated_count || 0)}</td>
                <td>${esc(row.skipped_count || 0)}</td>
                <td>${esc(row.failed_count || 0)}</td>
                <td>${esc(row.missing_count || 0)}</td>
            </tr>
        `).join("");
    }

    function renderSnapshot(snapshot) {
        ensureBackendSnapshotPanel();
        if (!snapshot || snapshot.ok === false) {
            setStatus(`Snapshot failed: ${(snapshot && snapshot.error) || "unknown error"}`, true);
            return;
        }
        renderCards(snapshot);
        renderRecommendations(snapshot);
        renderHistory(snapshot);
        setStatus(`Snapshot updated: ${snapshot.snapshot_at || new Date().toLocaleTimeString()}`, false);
    }

    async function refreshBackendSnapshot() {
        ensureBackendSnapshotPanel();
        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.get_dashboard_snapshot !== "function") {
            setStatus("Backend snapshot API unavailable. Restart dashboard after Patch 009.", true);
            return null;
        }

        try {
            setStatus("Loading backend snapshot...", false);
            const snapshot = await window.pywebview.api.get_dashboard_snapshot();
            renderSnapshot(snapshot || {});
            return snapshot;
        } catch (err) {
            console.log("[Patch009] snapshot failed:", err);
            setStatus(`Backend snapshot failed: ${err}`, true);
            return null;
        }
    }

    async function recordAdaptiveRefreshRun(options) {
        options = options && typeof options === "object" ? options : {};
        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.record_dashboard_refresh_history !== "function") return;
        if (typeof window.getAdaptiveRefreshBrainState !== "function") return;

        let state = null;
        try { state = window.getAdaptiveRefreshBrainState(); } catch (e) { return; }

        if (!state || !state.lastFinishedAt) return;
        if (!options.force && state.lastFinishedAt === lastRecordedRefreshAt) return;
        lastRecordedRefreshAt = state.lastFinishedAt;

        const payload = {
            source: options.sourceOverride || "patch008_adaptive_refresh",
            mode: state.mode || "",
            duration_ms: state.lastDurationMs || 0,
            finished_at: state.lastFinishedAt,
            results: Array.isArray(state.results) ? state.results : [],
            brain: state.brain || {}
        };

        try {
            const result = await window.pywebview.api.record_dashboard_refresh_history(payload);
            console.log("[Patch009] refresh history recorded:", result);
            if (options.refreshSnapshot === false) {
                return result;
            }
            setTimeout(refreshBackendSnapshot, 700);
            return result;
        } catch (e) {
            console.log("[Patch009] history record failed:", e);
            return { ok: false, error: String(e) };
        }
    }

    async function backendWriteTest() {
        ensureBackendSnapshotPanel();

        if (!window.pywebview || !window.pywebview.api || typeof window.pywebview.api.record_dashboard_refresh_history !== "function") {
            setStatus("Backend write test failed: record_dashboard_refresh_history API unavailable.", true);
            return { ok: false, error: "record_dashboard_refresh_history API unavailable" };
        }

        const startedAt = Date.now();
        const payload = {
            source: "backend_write_test_button",
            mode: "manual_test",
            duration_ms: 1,
            finished_at: startedAt,
            results: [
                {
                    key: "backend_write_test",
                    name: "Backend Write Test",
                    group: "pc_control",
                    ok: true,
                    status: "ok",
                    ms: 1,
                    message: "Manual backend write test row"
                }
            ],
            brain: {
                test: true,
                requested_at: new Date(startedAt).toISOString()
            }
        };

        try {
            setStatus("Running backend write test...", false);
            const result = await window.pywebview.api.record_dashboard_refresh_history(payload);
            if (!result || result.ok === false) {
                const error = result && result.error ? result.error : "unknown write failure";
                setStatus(`Backend write test failed: ${error}`, true);
                return result || { ok: false, error };
            }

            setStatus(`Backend write test wrote row #${result.id || "?"}. Refreshing snapshot...`, false);
            await refreshBackendSnapshot();
            return result;
        } catch (e) {
            console.log("[Patch009] backend write test failed:", e);
            setStatus(`Backend write test failed: ${e}`, true);
            return { ok: false, error: String(e) };
        }
    }

    function ensureBackendSnapshotPanel() {
        const pc = $("pc-control-section");
        if (!pc || $(PANEL_ID)) return;

        const panel = document.createElement("div");
        panel.id = PANEL_ID;
        panel.className = "patch009-backend-snapshot-panel";
        panel.innerHTML = `
            <div class="patch009-header">
                <div><h3>Backend Snapshot + Persistent ML History</h3><div class="patch009-subtitle">Stores refresh runs in SQLite and gives the refresh brain real backend status.</div></div>
                <div class="patch009-actions">
                    <button type="button" class="btn btn-primary" onclick="window.refreshBackendSnapshot()">SNAPSHOT</button>
                    <button type="button" class="btn btn-secondary" onclick="window.recordAdaptiveRefreshRun()">SAVE LAST REFRESH</button>
                    <button type="button" class="btn btn-secondary patch009-write-test-btn" onclick="window.backendWriteTest()">BACKEND WRITE TEST</button>
                </div>
            </div>
            <div id="${STATUS_ID}" class="patch009-status">Ready.</div>
            <div id="${CARDS_ID}" class="patch009-card-grid"><div class="patch009-empty">Snapshot not loaded yet.</div></div>
            <div class="patch009-grid">
                <div><div class="patch009-section-title">ML/RL Recommendations</div><div id="${RECS_ID}" class="patch009-recommendations"><div class="patch009-empty">No recommendations yet.</div></div></div>
                <div><div class="patch009-section-title">Backend Refresh History</div><div class="patch009-history-wrap"><table class="ghost-table patch009-history-table"><thead><tr><th>Time</th><th>Mode</th><th>Duration</th><th>OK</th><th>Skip</th><th>Fail</th><th>Missing</th></tr></thead><tbody id="${HISTORY_ID}"><tr><td colspan="7">No backend refresh history yet.</td></tr></tbody></table></div></div>
            </div>
        `;

        const refreshPanel = $("patch008-smart-refresh-panel");
        if (refreshPanel && refreshPanel.parentNode === pc) refreshPanel.insertAdjacentElement("afterend", panel);
        else if (pc.firstElementChild) pc.insertBefore(panel, pc.firstElementChild.nextSibling);
        else pc.appendChild(panel);
    }

    window.refreshBackendSnapshot = refreshBackendSnapshot;
    window.recordAdaptiveRefreshRun = recordAdaptiveRefreshRun;
    window.backendWriteTest = backendWriteTest;

    document.addEventListener("DOMContentLoaded", function () {
        setTimeout(function () {
            ensureBackendSnapshotPanel();
            refreshBackendSnapshot();
        }, 1800);
    });

    setInterval(recordAdaptiveRefreshRun, 3000);
    setInterval(function () { ensureBackendSnapshotPanel(); }, 5000);
    setInterval(function () { if ($(PANEL_ID)) refreshBackendSnapshot(); }, 60000);

})();
// === COMET PATCH 009 BACKEND REFRESH SNAPSHOT UI END ===

// === COMET SECTION INFO HELP START ===
(function () {
    "use strict";

    if (window.__cometSectionInfoHelpLoaded) return;
    window.__cometSectionInfoHelpLoaded = true;

    function esc(value) {
        return String(value === undefined || value === null ? "" : value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function normalizeTitle(value) {
        return String(value || "")
            .toLowerCase()
            .replace(/\+/g, " plus ")
            .replace(/\//g, " ")
            .replace(/&/g, " and ")
            .replace(/[^a-z0-9]+/g, " ")
            .replace(/\s+/g, " ")
            .trim();
    }

    const HELP_ITEMS = [
        {
            title: "Platform Revenue Model",
            aliases: ["platform revenue model"],
            summary: "Shows the local projection constants used by the dashboard when estimating potential platform value. These are only estimates and should be compared against official platform reports.",
            controls: ["No direct action buttons in this table. Use REFRESH ANALYTICS to reload it."],
            columns: ["Platform: service the model belongs to.", "Metric: event type the projection is based on.", "Min / Avg / Max: low, middle, and high local projection values.", "Condition: rule the event must satisfy before the estimate should be trusted."]
        },
        {
            title: "Profile Performance",
            aliases: ["profile performance"],
            summary: "Summarizes each profile's recent dashboard activity, status, platform, IP, event counts, and estimated value.",
            columns: ["Profile: local profile name or ID.", "Status: current dashboard status.", "Platform: most recent platform recorded.", "Last IP: latest known IP label.", "Events / Ads / Units: recorded activity counts.", "Est. Min / Avg / Max: projected value ranges.", "Last Event: most recent event timestamp."]
        },
        {
            title: "IP Reputation",
            aliases: ["ip reputation"],
            summary: "Tracks IP addresses seen by profiles and whether they appear useful, risky, blocked, or manually blacklisted.",
            controls: ["BLACKLIST IP marks an IP as blocked for future sessions.", "Action buttons let you blacklist or review a row when available."],
            columns: ["IP: detected IP address.", "Location / Provider: geo and network owner when known.", "Status: current reputation result.", "Blacklisted / Reason: whether it is blocked and why.", "Ads / Failures: local history counters.", "Good For / Bad For: platform-specific reputation notes."]
        },
        {
            title: "Platform Performance",
            aliases: ["platform performance"],
            summary: "Compares activity totals by platform so you can see where sessions, IPs, events, and estimates are concentrated.",
            columns: ["Platform: service name.", "Profiles Used: number of profiles that touched that platform.", "Unique IPs: distinct IPs recorded for that platform.", "Total Events / Ads / Units: activity counters.", "Est. Min / Avg / Max: projected value ranges.", "Last Event: most recent event time."]
        },
        {
            title: "Session Timeline",
            aliases: ["session timeline"],
            summary: "Shows the event-by-event timeline for a selected profile session so you can inspect launch, IP, platform, error, and close events.",
            controls: ["Profile and Session filters choose which run to inspect.", "LATEST resets the view to the newest known session."],
            columns: ["Timeline cards show event order, event type, platform/IP context, and event details."]
        },
        {
            title: "Profile Reliability Score",
            aliases: ["profile reliability score", "profile health ranking"],
            summary: "Ranks profiles by local reliability using launch history, errors, short sessions, IP failures, and repeated problems.",
            controls: ["Filters show reliable, watch, weak, bad, or error-only profiles.", "SORT SCORE / ERRORS / RECENT changes the ranking.", "SCAN QUARANTINE runs the advisory quarantine scan."],
            columns: ["Score / Grade: local reliability rating.", "Status / Last Platform / Last IP: current and recent context.", "Sessions / Events / Errors: history counters.", "Main Issue: strongest detected reliability problem.", "Action: quarantine or unquarantine where available."]
        },
        {
            title: "Recent Events",
            aliases: ["recent events"],
            summary: "Lists the newest analytics events recorded by the dashboard and backend.",
            columns: ["Time: event timestamp.", "PC: device that recorded it.", "Profile: related profile.", "Platform: related platform.", "IP / IP Status: network context.", "Event: event type.", "Units / Est. Avg: counted units and projected value.", "Details: raw event notes."]
        },
        {
            title: "Device Reliability + Coordinator Health",
            aliases: ["device reliability coordinator health", "device reliability and coordinator health"],
            summary: "Shows connected PCs, laptops, phones, tablets, and whether they are healthy, blocked, or allowed to launch work.",
            controls: ["REFRESH DEVICES reloads connected worker/device status."],
            columns: ["Device ID / Type / Role: local identity and assigned role.", "Status / Last Seen: whether it is currently reporting.", "Running Profiles: current load.", "Can Launch Profiles: permission to launch local profiles.", "Score / Main Issue: reliability grade and strongest problem.", "Blocked / Action: coordinator-level block status and controls."]
        },
        {
            title: "Run Control Center",
            aliases: ["run control center"],
            summary: "Live read-only view of profile runtime state, lifecycle stage, browser process tracking, and watchdog warnings.",
            controls: ["WATCHDOG SCAN checks for profiles stuck too long in transitional states.", "REFRESH STATUS reloads this panel."],
            columns: ["Status: dashboard state.", "Stage: plain-English runtime stage.", "Lifecycle: normalized state machine label.", "Age: time spent in current state.", "Watchdog: warning reason or OK.", "Session / Debug Port / Process: browser tracking details."]
        },
        {
            title: "Autoscale + Learning Center",
            aliases: ["autoscale learning center"],
            summary: "Resource-aware local autoscaling panel. It can dry-run or run one manual-mode scale cycle based on CPU, RAM, GPU, and profile limits.",
            controls: ["DRY RUN predicts the action without opening or closing browsers.", "RUN ONCE performs one autoscale cycle.", "SAVE + ENABLE turns on the background autoscale loop.", "DISABLE AUTOSCALE stops background autoscaling."],
            columns: ["Recent Autoscale Events: action, reason, active count, desired count, reward.", "Learning Observations: saved local feedback rows used for later tuning."]
        },
        {
            title: "Comet Fleet Profile Identity Report",
            aliases: ["comet fleet profile identity report", "profile identity report"],
            summary: "Audits generated profile identities for uniqueness, desktop/mobile mix, model duplication, and fingerprint-signature overlap.",
            controls: ["Refresh reloads the identity audit when available."],
            columns: ["Type / Device / OS / Viewport / Language / Platform: browser identity fields.", "Hashes: short identity fingerprints used to spot duplicates.", "Result: uniqueness or warning summary."]
        },
        {
            title: "Proton VPN Accounts",
            aliases: ["proton vpn accounts", "proton accounts"],
            summary: "Stores local Proton account assignments and manual readiness status for profiles. It does not automatically log into VPN accounts.",
            controls: ["IMPORT ACCOUNTS stores provided account rows locally.", "REBALANCE redistributes accounts across profiles.", "READY / NEEDS LOGIN flags setup status after manual review."],
            columns: ["Profile: assigned profile.", "Account: mapped Proton account.", "Readiness: whether manual setup is complete.", "Action: open/setup or mark status."]
        },
        {
            title: "Safe Automation Route Plan",
            aliases: ["safe automation route plan", "safe route plan"],
            summary: "Builds a local planning view for launch order, platform selection, warmup, and session-window expectations without changing platform runners.",
            controls: ["Refresh or build plan buttons create a new local route preview when available."],
            columns: ["Close/Launch Order: randomized order.", "Profile: profile to run.", "Planned Platforms: selected platform plan.", "Warmup / Session Window: timing plan.", "Target Policy / Notes: routing notes."]
        },
        {
            title: "Backend Snapshot + Persistent ML History",
            aliases: ["backend snapshot persistent ml history", "backend snapshot plus persistent ml history", "backend snapshot personal ml history"],
            summary: "Reads backend status, stores dashboard refresh history in SQLite, and gives the adaptive refresh brain persistent context.",
            controls: ["SNAPSHOT reloads backend status.", "SAVE LAST REFRESH writes the latest refresh run.", "BACKEND WRITE TEST writes a test row to prove persistence works."],
            columns: ["Snapshot cards show profile, Proton, coordinator, sync, refresh, and runtime counts.", "ML/RL Recommendations show backend-derived advice.", "Backend Refresh History lists saved refresh runs."]
        },
        {
            title: "Mobile Task Queue",
            aliases: ["mobile task queue", "mobile tax queue"],
            summary: "Tracks commands/tasks intended for mobile or remote workers connected to the fleet.",
            controls: ["Refresh/retry controls reload or update queued work when available."],
            columns: ["Task / Target / Status: what should run and where.", "Created / Updated: timing.", "Result / Error: worker response."]
        },
        {
            title: "Backup + Rollback Manager",
            aliases: ["backup rollback manager", "backup plus rollback manager"],
            summary: "Creates and manages local code backups so updates can be reviewed and rolled back if a patch breaks something.",
            controls: ["CREATE BACKUP makes a local backup.", "RESTORE SELECTED / RESTORE LATEST restores files from a backup.", "DELETE SELECTED removes a backup entry."],
            columns: ["Backup ID: backup folder/archive identifier.", "Label / Created: when and why it was made.", "Files / Size: backup contents summary."]
        },
        {
            title: "System Diagnostics + Log Viewer",
            aliases: ["system diagnostics log viewer", "system diagnostic plus log viewer"],
            summary: "Checks required paths, coordinator routes, Python compilation, local files, and recent safe log summaries.",
            controls: ["Refresh/check buttons rerun diagnostics.", "Log controls read or clear allowed local logs."],
            columns: ["Coordinator Routes: main PC/API checks.", "Python Compile Check: syntax health.", "Local Files: required file presence.", "Logs: recent diagnostic output."]
        },
        {
            title: "Version Status + Sync History",
            aliases: ["version status sync history", "version status plus sync history"],
            summary: "Shows local version/sync state so the laptop and main PC can stay aligned when the coordinator is available.",
            controls: ["Refresh reloads sync status and compare data."],
            columns: ["File Compare: changed/missing file status.", "Sync History: recent sync attempts, results, and errors."]
        },
        {
            title: "Device Groups + Permissions",
            aliases: ["device groups permissions", "device groups plus permissions"],
            summary: "Assigns connected devices to roles and controls whether they can launch profiles, receive mobile tasks, edit targets, or manage the fleet.",
            controls: ["Save/apply controls update device permission rows when available."],
            columns: ["Role: device permission group.", "Blocked: whether the device is prevented from acting.", "Launch / Mobile Tasks / Control Fleet / Edit Targets / Delete Profiles: permission flags."]
        },
        {
            title: "Permission Audit Log + Security Events",
            aliases: ["permission audit log security events", "permissions audit log security events", "permission audit log plus security events"],
            summary: "Records permission changes, security events, blocked actions, and coordinator audit rows.",
            controls: ["Filters narrow by event type/status.", "Refresh reloads recent audit rows."],
            columns: ["Time: event timestamp.", "Device/User: source.", "Event/Status: what happened.", "Details: raw audit context."]
        },
        {
            title: "Main PC / Laptop Command Center",
            aliases: ["main pc laptop command center"],
            summary: "Sends command requests between the laptop and main PC coordinator when remote command workers are online.",
            controls: ["Command buttons queue actions for a selected target PC_ID.", "Refresh reloads command state."],
            columns: ["Target PC: command destination.", "Command: requested action.", "Status: queued/running/done/failed.", "Result: worker response."]
        },
        {
            title: "ML Reliability + Anomaly Detection v1",
            aliases: ["ml reliability anomaly detection v1", "ml reliability plus anomaly detection v1"],
            summary: "Scores device reliability and flags unusual failures, missing heartbeats, blocked workers, or unstable runtime patterns.",
            columns: ["Device Reliability Scores: local device grade.", "Anomaly Alerts: detected problems and recommended fixes.", "Recent ML Events: latest scoring inputs."]
        },
        {
            title: "ML History + Trend Learning v1",
            aliases: ["ml history trend learning v1", "ml history plus trend learning v1"],
            summary: "Looks across historical device and runtime events to identify trends, repeated failures, and worsening/improving devices.",
            columns: ["Device Trend Learning: score movement.", "Trend Recommendations: suggested review items.", "Anomaly Frequency: repeated issue counts."]
        },
        {
            title: "ML Auto-Recommendation Action Queue v1",
            aliases: ["ml auto recommendation action queue v1", "ml auto recommendation action queue"],
            summary: "Queues recommended actions from ML panels for review before anything is applied.",
            controls: ["Approve/skip/refresh controls manage the recommendation queue when available."],
            columns: ["Action: suggested task.", "Severity: importance.", "Status: queued/approved/skipped.", "Reason: why it was suggested."]
        },
        {
            title: "ML Safe Auto-Executor v1",
            aliases: ["ml safe auto executor v1", "ml safe auto executioner v1"],
            summary: "Runs approved safe maintenance actions and records what happened. It is meant for local maintenance, not platform automation.",
            controls: ["Refresh reloads executor status.", "Run controls execute approved safe actions when available."],
            columns: ["Action: task being executed.", "Safety: allowed/blocked result.", "Status: progress.", "Result: outcome."]
        },
        {
            title: "ML Auto-Executor Result Feedback Loop v1",
            aliases: ["ml auto executor result feedback loop v1", "ml auto execution results feedback loop v1"],
            summary: "Stores results from auto-executed safe actions so later recommendations can learn what helped and what failed.",
            columns: ["Result: action outcome.", "Reward/Score: usefulness signal.", "Error: failure detail.", "Next Recommendation: follow-up when available."]
        },
        {
            title: "ML Auto-Resolve + Device Score Adjustment v1",
            aliases: ["ml auto resolve device score adjustment v1", "ml auto resolve plus device score adjustment v1"],
            summary: "Uses safe resolver outcomes to adjust device reliability scores and explain why a device score changed.",
            columns: ["Adjusted Device Reliability: new score and reason.", "Resolver Events: adjustment history and evidence."]
        },
        {
            title: "Unified ML Control Center + Device Timeline v1",
            aliases: ["unified ml control center device timeline v1", "unified ml control center plus device timeline v1"],
            summary: "Combines ML device health, command state, timeline events, and recommendations into one control view.",
            columns: ["Unified Device Table: current device health summary.", "Device Health Timeline: ordered history of device events."]
        },
        {
            title: "ML Smart Worker Selection + Stale PC_ID Detector v1",
            aliases: ["ml smart worker selection stale pc id detector v1", "ml smart workers selection state pc id detector v1", "ml smart worker selection plus stale pc id detector v1"],
            summary: "Ranks workers for local tasks and flags stale or incorrect PC_ID targets that may cause commands to go nowhere.",
            columns: ["Worker Selection Ranking: best available workers.", "Stale / Bad PC_ID Targets: IDs that need correction or cleanup."]
        },
        {
            title: "ML Backup Guard + Update Readiness Gate v1",
            aliases: ["ml backup guard update readiness gate v1", "ml backup guard plus update readiness gate v1"],
            summary: "Checks whether a backup should be created before updates and blocks risky update attempts until the project is protected.",
            controls: ["REFRESH GUARD reloads status.", "CREATE ML BACKUP creates a guard backup.", "AUTO-RUN GUARD checks and backs up if needed."],
            columns: ["Backup Recommendation: whether backup is required.", "Backup List: available guard backups."]
        },
        {
            title: "ML Capacity Forecast + Worker Load Planner v1",
            aliases: ["ml capacity forecast workload planner v1", "ml capacity forecast worker load planner v1"],
            summary: "Forecasts safe worker capacity based on recent load, profile counts, device health, and resource history.",
            columns: ["Worker Capacity Plan: recommended load per worker.", "Capacity Recommendations: suggested profile limits.", "Exported Reports: saved forecast files."]
        },
        {
            title: "ML/RL Architecture v2 Compatible",
            aliases: ["ml rl architecture v2 compatible", "ml rl architect v1 compatible"],
            summary: "Local experimental architecture panel for reinforcement-learning style state/action/reward experiments and behavior dataset previews.",
            controls: ["Enable/disable toggles the local experiment state.", "Episode/train/export buttons run or export local learning experiments when available."],
            columns: ["Latest Episode: most recent simulated run.", "Behavior Dataset Preview: sample state/action/reward rows."]
        },
        {
            title: "Adaptive ML/RL Refresh Brain",
            aliases: ["adaptive ml rl refresh brain"],
            summary: "Learns which dashboard sections refresh successfully and prioritizes future refreshes without touching browser automation.",
            controls: ["REFRESH ALL updates dashboard panels.", "AUTO MODE cycles auto-refresh modes.", "RESET BRAIN clears learned refresh priorities."],
            columns: ["Latest Refresh Run: recent panel refresh results.", "Learned Section Priority: current priority scores and success/failure counts."]
        }
    ];

    const HELP_BY_KEY = new Map();
    HELP_ITEMS.forEach(item => {
        const keys = [item.title].concat(item.aliases || []);
        keys.forEach(key => HELP_BY_KEY.set(normalizeTitle(key), item));
    });

    function cleanHeadingText(el) {
        const clone = el.cloneNode(true);
        clone.querySelectorAll(".section-info-btn").forEach(btn => btn.remove());
        return normalizeTitle(clone.textContent || "");
    }

    function findHelpForHeading(el) {
        const key = cleanHeadingText(el);
        if (HELP_BY_KEY.has(key)) return HELP_BY_KEY.get(key);
        for (const [candidate, item] of HELP_BY_KEY.entries()) {
            if (key === candidate || key.includes(candidate) || candidate.includes(key)) {
                return item;
            }
        }
        return null;
    }

    function ensureModal() {
        let overlay = document.getElementById("section-info-overlay");
        if (overlay) return overlay;

        overlay = document.createElement("div");
        overlay.id = "section-info-overlay";
        overlay.className = "section-info-overlay";
        overlay.innerHTML = `
            <div class="section-info-dialog" role="dialog" aria-modal="true" aria-labelledby="section-info-title">
                <div class="section-info-dialog-header">
                    <div>
                        <div class="section-info-kicker">Section Info</div>
                        <h2 id="section-info-title">Section Info</h2>
                    </div>
                    <button type="button" class="section-info-close" aria-label="Close section information">&times;</button>
                </div>
                <div id="section-info-body" class="section-info-body"></div>
            </div>
        `;
        document.body.appendChild(overlay);

        overlay.addEventListener("click", function (event) {
            if (event.target === overlay) closeInfoModal();
        });

        const closeBtn = overlay.querySelector(".section-info-close");
        if (closeBtn) closeBtn.addEventListener("click", closeInfoModal);

        return overlay;
    }

    function renderList(title, rows) {
        if (!Array.isArray(rows) || !rows.length) return "";
        return `
            <div class="section-info-block">
                <h3>${esc(title)}</h3>
                <ul>${rows.map(row => `<li>${esc(row)}</li>`).join("")}</ul>
            </div>
        `;
    }

    function openInfoModal(item) {
        const overlay = ensureModal();
        const title = overlay.querySelector("#section-info-title");
        const body = overlay.querySelector("#section-info-body");
        if (!title || !body) return;

        title.textContent = item.title || "Section Info";
        body.innerHTML = `
            <div class="section-info-summary">${esc(item.summary || "No description available yet.")}</div>
            ${renderList("Controls", item.controls)}
            ${renderList("Columns / Fields", item.columns)}
            ${renderList("Notes", item.notes)}
        `;

        overlay.classList.add("open");
        document.body.classList.add("section-info-modal-open");
        const closeBtn = overlay.querySelector(".section-info-close");
        if (closeBtn) closeBtn.focus();
    }

    function closeInfoModal() {
        const overlay = document.getElementById("section-info-overlay");
        if (!overlay) return;
        overlay.classList.remove("open");
        document.body.classList.remove("section-info-modal-open");
    }

    function decorateHeading(el) {
        if (!el || el.dataset.sectionInfoDecorated === "1") return;
        if (el.closest("#section-info-overlay")) return;

        const item = findHelpForHeading(el);
        if (!item) return;

        el.dataset.sectionInfoDecorated = "1";
        el.classList.add("section-info-heading");

        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "section-info-btn";
        btn.textContent = "i";
        btn.title = `What does ${item.title} do?`;
        btn.setAttribute("aria-label", `What does ${item.title} do?`);
        btn.addEventListener("click", function (event) {
            event.preventDefault();
            event.stopPropagation();
            openInfoModal(item);
        });

        el.appendChild(btn);
    }

    function ensureSectionInfoButtons() {
        const selectors = [
            "#analytics-section h2",
            "#analytics-section h3",
            "#analytics-section h4",
            "#analytics-section [class*='section-title']",
            "#analytics-section .profile-reliability-title",
            "#pc-control-section h2",
            "#pc-control-section h3",
            "#pc-control-section h4",
            "#pc-control-section [class*='section-title']",
            "#pc-control-section [class*='table-title']"
        ];

        document.querySelectorAll(selectors.join(",")).forEach(decorateHeading);
    }

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") closeInfoModal();
    });

    document.addEventListener("DOMContentLoaded", function () {
        ensureModal();
        setTimeout(ensureSectionInfoButtons, 400);
        setTimeout(ensureSectionInfoButtons, 1600);
    });

    const observer = new MutationObserver(function () {
        ensureSectionInfoButtons();
    });

    function startObserver() {
        if (!document.body) return;
        observer.observe(document.body, { childList: true, subtree: true });
        ensureSectionInfoButtons();
    }

    if (document.body) startObserver();
    else document.addEventListener("DOMContentLoaded", startObserver);

    setInterval(ensureSectionInfoButtons, 5000);

    window.openCometSectionInfo = openInfoModal;
    window.refreshCometSectionInfoButtons = ensureSectionInfoButtons;
})();
// === COMET SECTION INFO HELP END ===

// ================================================================
// WEB AGENT — JavaScript controller
// ================================================================

let _waAutoOn = false;
let _waStatusInterval = null;

function waInit() {
    waLoadModels();
    waRefreshStatus();
    if (!_waStatusInterval) {
        _waStatusInterval = setInterval(waRefreshStatus, 3000);
    }
}

function waLog(msg, type = 'info') {
    const log = document.getElementById('wa-log');
    if (!log) return;
    const entry = document.createElement('div');
    entry.className = `wa-log-entry wa-log-${type}`;
    const ts = new Date().toLocaleTimeString();
    entry.textContent = `[${ts}] ${msg}`;
    log.prepend(entry);
    // Trim log to 200 entries
    while (log.children.length > 200) log.removeChild(log.lastChild);
}

async function waCall(method, ...args) {
    try {
        const raw = await window.pywebview.api[method](...args);
        return typeof raw === 'string' ? JSON.parse(raw) : raw;
    } catch (e) {
        waLog(`API error (${method}): ${e}`, 'fail');
        return { ok: false, error: String(e) };
    }
}

async function waLoadModels() {
    const sel = document.getElementById('wa-model-select');
    if (!sel) return;
    const res = await waCall('wa_ollama_models');
    sel.innerHTML = '<option value="">Rule-based (no AI)</option>';
    if (res.ok && res.models && res.models.length) {
        res.models.forEach(m => {
            const opt = document.createElement('option');
            opt.value = m; opt.textContent = m;
            sel.appendChild(opt);
        });
        waLog(`Ollama models loaded: ${res.models.join(', ')}`, 'info');
    } else {
        waLog('Ollama not detected — using rule-based suggestions', 'info');
    }
}

async function waRefreshStatus() {
    const res = await waCall('wa_get_status');
    const browserPill = document.getElementById('wa-browser-status');
    const autoPill    = document.getElementById('wa-auto-status');
    const urlEl       = document.getElementById('wa-current-url');
    const titleEl     = document.getElementById('wa-page-title');
    const autoBtn     = document.getElementById('wa-auto-btn');
    const approvalBar = document.getElementById('wa-approval-bar');
    const approvalMsg = document.getElementById('wa-approval-msg');

    if (browserPill) {
        if (res.browser_running) {
            browserPill.textContent = '🟢 Browser On';
            browserPill.style.color = 'var(--accent-green)';
        } else {
            browserPill.textContent = '⚫ Browser Off';
            browserPill.style.color = 'var(--text-muted)';
        }
    }
    if (autoPill) {
        autoPill.textContent = res.auto_mode ? 'Auto: ON' : 'Auto: OFF';
        autoPill.style.color = res.auto_mode ? 'var(--accent-green)' : 'var(--text-muted)';
    }
    if (autoBtn) {
        autoBtn.textContent = res.auto_mode ? '⚡ Auto ON' : '⚡ Auto OFF';
        _waAutoOn = res.auto_mode;
    }
    if (urlEl && res.current_url)   urlEl.textContent   = `URL: ${res.current_url}`;
    if (titleEl && res.current_title) titleEl.textContent = `Title: ${res.current_title}`;

    if (approvalBar && approvalMsg) {
        if (res.pending_approval) {
            const a = res.pending_approval;
            approvalMsg.textContent = `Approval needed: ${a.action} "${a.target_text}" (${a.safety_level})`;
            approvalBar.style.display = 'flex';
        } else {
            approvalBar.style.display = 'none';
        }
    }
}

async function waStartBrowser() {
    waLog('Starting browser…', 'info');
    const res = await waCall('wa_start_browser');
    waLog(res.ok ? `Browser started on port ${res.port}` : `Failed: ${res.error}`, res.ok ? 'ok' : 'fail');
    waRefreshStatus();
}

async function waStopBrowser() {
    const res = await waCall('wa_stop_browser');
    waLog(res.ok ? 'Browser stopped' : `Stop failed: ${res.error}`, res.ok ? 'ok' : 'fail');
    waRefreshStatus();
}

async function waEmergencyStop() {
    const res = await waCall('wa_emergency_stop');
    waLog('🛑 EMERGENCY STOP', 'fail');
    waRefreshStatus();
}

async function waNavigate() {
    const url = document.getElementById('wa-url-input')?.value?.trim();
    if (!url) return waLog('Enter a URL first', 'fail');
    waLog(`Navigating to ${url}…`, 'info');
    const res = await waCall('wa_navigate', url);
    waLog(res.ok ? `Navigated: ${res.title}` : `Failed: ${res.error}`, res.ok ? 'ok' : 'fail');
    if (res.ok) waRefreshStatus();
}

async function waAnalyzePage() {
    waLog('Analyzing page…', 'info');
    const res = await waCall('wa_analyze_page');
    if (!res.ok) return waLog(`Analysis failed: ${res.error}`, 'fail');
    const data = res.data;
    waLog(`Analyzed: ${data.title} | ${data.buttons?.length||0} buttons, ${data.links?.length||0} links, ${data.inputs?.length||0} inputs`, 'ok');
    waRenderElements(data);
    if (data.screenshot) waShowScreenshot(data.screenshot);
    waRefreshStatus();
}

function waRenderElements(data) {
    const container = document.getElementById('wa-elements');
    if (!container) return;
    container.innerHTML = '';

    const groups = [
        { label: `Buttons (${(data.buttons||[]).length})`,    items: (data.buttons||[]).map(b => b.text || b.aria_label || '—') },
        { label: `Links (${(data.links||[]).length})`,        items: (data.links||[]).map(l => l.text || l.href || '—') },
        { label: `Inputs (${(data.inputs||[]).length})`,      items: (data.inputs||[]).map(i => i.placeholder || i.name || i.type || '—') },
        { label: `Dropdowns (${(data.selects||[]).length})`,  items: (data.selects||[]).map(s => s.name || '(dropdown)') },
        { label: `Checkboxes (${(data.checkboxes||[]).length})`, items: (data.checkboxes||[]).map(c => `[${c.checked?'✓':' '}] ${c.name||c.type}`) },
        { label: `Forms (${(data.forms||[]).length})`,        items: (data.forms||[]).map(f => f.action || f.id || '(form)') },
        { label: `Text (${(data.text_blocks||[]).length})`,   items: (data.text_blocks||[]).map(t => `<${t.tag}> ${t.text}`) },
        { label: `ARIA (${(data.aria_roles||[]).length})`,    items: (data.aria_roles||[]).map(a => `[${a.role}] ${a.text}`) },
    ];

    groups.forEach(g => {
        if (!g.items.length) return;
        const grp = document.createElement('div'); grp.className = 'wa-el-group';
        const lbl = document.createElement('div'); lbl.className = 'wa-el-label'; lbl.textContent = g.label;
        grp.appendChild(lbl);
        g.items.slice(0, 20).forEach(text => {
            const item = document.createElement('div'); item.className = 'wa-el-item';
            item.textContent = text; item.title = text;
            grp.appendChild(item);
        });
        container.appendChild(grp);
    });
}

function waShowScreenshot(path) {
    const box = document.getElementById('wa-screenshot-box');
    if (!box) return;
    box.innerHTML = `<img src="file:///${path.replace(/\\/g,'/')}" onerror="this.alt='Screenshot not available'" alt="screenshot" />`;
}

async function waSuggestAction() {
    const task  = document.getElementById('wa-task-input')?.value?.trim() || '';
    const model = document.getElementById('wa-model-select')?.value || '';
    waLog(`Suggesting action for: "${task || 'navigate the page'}"…`, 'info');
    const res = await waCall('wa_suggest_action', task, !!model, model);
    if (!res.ok) return waLog(`Suggest failed: ${res.error}`, 'fail');
    const s = res.suggestion;
    waRenderSuggestion(s);
    waLog(`Suggestion: ${s.action} "${s.target_text}" (${Math.round((s.confidence||0)*100)}% confidence, ${s.safety_level})`, 'ok');
}

function waRenderSuggestion(s) {
    const box = document.getElementById('wa-suggestion-box');
    if (!box || !s) return;
    const safetyClass = s.safety_level === 'safe' ? 'wa-safe' : s.safety_level === 'dangerous' ? 'wa-dangerous' : 'wa-caution';
    const confIcon = s.confidence >= 0.7 ? '🟢' : s.confidence >= 0.4 ? '🟡' : '🔴';

    box.innerHTML = `
        <div class="wa-sug-action">${s.action?.toUpperCase() || '?'} → "${s.target_text || s.selector || '—'}"</div>
        <div class="wa-sug-reason">${s.reason || ''}</div>
        <div class="wa-sug-safety">
            <span class="${safetyClass}">⚑ ${s.safety_level || '—'}</span>
            &nbsp;|&nbsp; ${confIcon} ${Math.round((s.confidence||0)*100)}% confidence
            &nbsp;|&nbsp; Source: ${s.source || 'rule'}
            ${s.requires_approval ? '&nbsp;|&nbsp; <span class="wa-caution">⚠ Needs approval</span>' : ''}
        </div>
    `;

    const safetyPill = document.getElementById('wa-safety-status');
    const confEl     = document.getElementById('wa-confidence');
    if (safetyPill) { safetyPill.textContent = `Safety: ${s.safety_level}`; safetyPill.className = `wa-status-pill ${safetyClass}`; }
    if (confEl)     confEl.textContent = `Confidence: ${Math.round((s.confidence||0)*100)}%`;
}

async function waExecuteAction() {
    waLog('Executing suggested action…', 'info');
    const res = await waCall('wa_execute_action', false, null);
    if (res.result?.error === 'APPROVAL_REQUIRED') {
        waLog('Action requires approval — click Approve to proceed', 'fail');
        document.getElementById('wa-approval-bar').style.display = 'flex';
        document.getElementById('wa-approval-msg').textContent = 'This action requires your approval before executing.';
        return;
    }
    waLog(res.ok ? `Done: ${res.result?.message}` : `Failed: ${res.result?.error || res.error}`, res.ok ? 'ok' : 'fail');
    if (res.result?.screenshot_after) waShowScreenshot(res.result.screenshot_after);
}

async function waApprovePending() {
    waLog('Approving pending action…', 'info');
    const res = await waCall('wa_approve_pending');
    waLog(res.ok ? `Approved & executed: ${res.result?.message}` : `Failed: ${res.error}`, res.ok ? 'ok' : 'fail');
    document.getElementById('wa-approval-bar').style.display = 'none';
    if (res.result?.screenshot_after) waShowScreenshot(res.result.screenshot_after);
}

async function waToggleAuto() {
    if (_waAutoOn) {
        const res = await waCall('wa_stop_auto_mode');
        waLog('Auto mode stopped', 'info');
    } else {
        const task  = document.getElementById('wa-task-input')?.value?.trim() || '';
        const model = document.getElementById('wa-model-select')?.value || '';
        const res = await waCall('wa_start_auto_mode', task, 5.0, model);
        waLog(res.ok ? 'Auto mode started' : `Failed: ${res.error}`, res.ok ? 'ok' : 'fail');
    }
    waRefreshStatus();
}

async function waPause()  { const r = await waCall('wa_pause');  waLog('Paused', 'info'); }
async function waResume() { const r = await waCall('wa_resume'); waLog('Resumed', 'info'); document.getElementById('wa-approval-bar').style.display = 'none'; }

async function waScreenshot() {
    const res = await waCall('wa_take_screenshot');
    waLog(res.ok ? `Screenshot saved: ${res.path}` : `Failed: ${res.error}`, res.ok ? 'ok' : 'fail');
    if (res.ok) waShowScreenshot(res.path);
}

async function waRunOCR() {
    waLog('Running OCR on current screenshot…', 'info');
    const res = await waCall('wa_run_ocr', '');
    const el = document.getElementById('wa-ocr');
    if (res.ok) {
        waLog(`OCR complete — ${res.text?.length||0} chars extracted`, 'ok');
        if (el) el.textContent = res.text || '(no text found)';
    } else {
        waLog(`OCR: ${res.error}`, 'fail');
        if (el) el.textContent = res.error;
    }
}

async function waDiagnostics() {
    waLog('Running diagnostics…', 'info');
    const res = await waCall('wa_diagnostics');
    const container = document.getElementById('wa-elements');
    if (!container) return;
    container.innerHTML = '<div class="wa-el-label">Diagnostics</div>';
    Object.entries(res).forEach(([key, val]) => {
        const item = document.createElement('div');
        item.className = `wa-diag-item ${val.ok ? 'wa-diag-ok' : 'wa-diag-fail'}`;
        item.textContent = `${val.ok ? '✅' : '❌'} ${key}: ${val.error || val.version || val.path || (val.ok ? 'OK' : 'FAIL')}`;
        if (val.models) item.textContent += ` [${val.models.join(', ')}]`;
        container.appendChild(item);
    });
}

async function waClearLogs() {
    if (!confirm('Clear all Web Agent logs?')) return;
    const res = await waCall('wa_clear_logs');
    waLog('Logs cleared', 'info');
    document.getElementById('wa-log').innerHTML = '';
}

// ================================================================
// WEB AGENT END
// ================================================================
