/* =====================================================
   Zodovia — Compatibility Page (compatibility.js)
   ===================================================== */

const API = '';

function getToken() { return localStorage.getItem('zodovia_token'); }
function getUser()  { return JSON.parse(localStorage.getItem('zodovia_user') || 'null'); }

const SIGN_SYMBOLS = {
    Aries:'♈', Taurus:'♉', Gemini:'♊', Cancer:'♋',
    Leo:'♌', Virgo:'♍', Libra:'♎', Scorpio:'♏',
    Sagittarius:'♐', Capricorn:'♑', Aquarius:'♒', Pisces:'♓'
};

const REL_LABELS = {
    romantic: 'Romantic Partner', friend: 'Close Friend',
    mother: 'Mother', father: 'Father',
    sibling: 'Brother / Sister', cousin: 'Cousin',
    colleague: 'Colleague', other: 'Important Person'
};

document.addEventListener('DOMContentLoaded', async () => {
    const token = getToken();
    const user  = getUser();

    if (!token || !user) {
        window.location.href = '/';
        return;
    }

    try {
        const freshUser = await apiFetch('/api/users/me', 'GET', null, token);
        // Apply sign theme
        if (freshUser.sun_sign) document.body.setAttribute('data-sign', freshUser.sun_sign);
        // Show admin link for superusers
        if (freshUser.is_superuser) {
            document.getElementById('adminLink')?.classList.remove('hidden');
        }
        // Show user's details
        renderYourDetails(freshUser);
        // Show free tier usage banner for non-paid, non-superuser users
        if (!freshUser.is_paid && !freshUser.is_superuser) {
            showUsageBanner(freshUser.free_uses);
        }
    } catch {
        window.location.href = '/';
        return;
    }

    document.getElementById('logoutBtn')?.addEventListener('click', (e) => {
        e.preventDefault();
        localStorage.clear();
        window.location.href = '/';
    });

    setupRelPills();
    setupForm(token);
    setupLocationAutocomplete('p2City', 'p2Lat', 'p2Lon');
    setupCoordToggle('p2CoordToggleBtn', 'p2CoordInputs', 'p2City', null);
});

function renderYourDetails(user) {
    const el = document.getElementById('yourDetails');
    if (!el) return;
    const sym = SIGN_SYMBOLS[user.sun_sign] || '';
    el.innerHTML = `
        <strong style="color:var(--text)">${user.name}</strong>
        &nbsp;·&nbsp; ${sym} ${user.sun_sign || '—'} Sun
        &nbsp;·&nbsp; ${user.moon_sign || '—'} Moon
        &nbsp;·&nbsp; ${user.rising_sign || '—'} Rising
        &nbsp;·&nbsp; <span style="color:var(--text-muted);font-size:0.83rem">${user.birth_city || ''}</span>
    `;
}

function setupRelPills() {
    const pills     = document.querySelectorAll('.rel-pill');
    const hiddenInput = document.getElementById('relType');

    pills.forEach(pill => {
        pill.addEventListener('click', () => {
            pills.forEach(p => p.classList.remove('active'));
            pill.classList.add('active');
            hiddenInput.value = pill.dataset.value;
        });
    });
}

function setupForm(token) {
    const btn       = document.getElementById('checkCompatBtn');
    const errorEl   = document.getElementById('compatError');
    const formSect  = document.getElementById('formSection');
    const loadingSt = document.getElementById('loadingState');
    const resultEl  = document.getElementById('compatResult');
    const newCheckBtn = document.getElementById('newCheckBtn');

    btn?.addEventListener('click', async () => {
        if (btn.disabled) return;
        errorEl.classList.add('hidden');

        const p2Name = document.getElementById('p2Name').value.trim();
        const p2Date = document.getElementById('p2Date').value;
        const p2Time = document.getElementById('p2Time').value;
        const p2City = document.getElementById('p2City').value.trim();
        const relType = document.getElementById('relType').value;

        if (!p2Name || !p2Date || !p2Time || !p2City) {
            errorEl.textContent = 'Please fill in all their birth details.';
            errorEl.classList.remove('hidden');
            return;
        }

        // Show loading, hide form, lock button
        btn.disabled = true;
        formSect.classList.add('hidden');
        loadingSt.classList.remove('hidden');
        document.getElementById('loadingMsg').textContent =
            `Comparing your charts with ${p2Name}'s…`;

        // Collect optional exact coordinates for person 2
        const p2Lat = parseFloat(document.getElementById('p2Lat')?.value);
        const p2Lon = parseFloat(document.getElementById('p2Lon')?.value);
        const hasCoords2 = !isNaN(p2Lat) && !isNaN(p2Lon);

        try {
            const res = await apiFetch('/api/compatibility', 'POST', {
                person2_name: p2Name,
                person2_birth_date: p2Date,
                person2_birth_time: p2Time,
                person2_birth_city: p2City,
                relationship_type: relType,
                ...(hasCoords2 ? { person2_birth_lat: p2Lat, person2_birth_lon: p2Lon } : {}),
            }, token);

            renderResult(res);
            // Update usage banner after successful use
            if (res.free_uses_remaining !== null && res.free_uses_remaining !== undefined) {
                const used = 10 - res.free_uses_remaining;
                showUsageBanner(used);
            }
        } catch (err) {
            loadingSt.classList.add('hidden');
            formSect.classList.remove('hidden');
            if (err.status === 402) {
                showUpgradeModal();
            } else if (err.status === 429) {
                errorEl.textContent = "You've reached today's limit for compatibility checks. Come back tomorrow for more.";
                errorEl.classList.remove('hidden');
            } else {
                errorEl.textContent = err.message || 'Something went wrong. Please try again.';
                errorEl.classList.remove('hidden');
            }
        } finally {
            loadingSt.classList.add('hidden');
            btn.disabled = false;
        }
    });

    newCheckBtn?.addEventListener('click', () => {
        resultEl.classList.add('hidden');
        formSect.classList.remove('hidden');
        // Clear form
        document.getElementById('p2Name').value = '';
        document.getElementById('p2Date').value = '';
        document.getElementById('p2Time').value = '12:00';
        document.getElementById('p2City').value = '';
        window.scrollTo({ top: 0, behavior: 'smooth' });
    });
}

function renderResult(res) {
    const user = getUser();
    const formSect = document.getElementById('formSection');
    const resultEl = document.getElementById('compatResult');

    const sym2 = SIGN_SYMBOLS[res.person2_sun_sign] || '';
    const relLabel = REL_LABELS[res.relationship_type] || res.relationship_type;

    document.getElementById('resultNames').textContent =
        `${user?.name || 'You'} & ${res.person2_name}`;
    document.getElementById('resultSub').textContent =
        `${sym2} ${res.person2_sun_sign} · ${relLabel}`;

    const readingEl = document.getElementById('compatReading');
    readingEl.innerHTML = formatReading(res.report);

    formSect.classList.add('hidden');
    resultEl.classList.remove('hidden');
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function formatReading(text) {
    if (!text) return '';
    return text.trim().split(/\n\n+/).map(block => {
        const b = block.trim();
        if (!b || /^-{2,}$/.test(b)) return '';
        // Escape HTML entities before any injection can happen
        const safe = b.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        if (safe.startsWith('### ')) {
            const content = safe.slice(4).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
            return `<h3>${content}</h3>`;
        }
        if (safe.startsWith('## ')) {
            const content = safe.slice(3).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
            return `<h2>${content}</h2>`;
        }
        const clean = safe
            .replace(/\n/g, ' ')
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.+?)\*/g, '<em>$1</em>')
            .trim();
        if (!clean) return '';
        return `<p>${clean}</p>`;
    }).filter(Boolean).join('');
}

function showUsageBanner(freeUses) {
    const FREE_LIMIT = 10;
    const FREE_NUDGE_AT = 5;
    let banner = document.getElementById('freeTierBanner');
    if (!banner) {
        banner = document.createElement('div');
        banner.id = 'freeTierBanner';
        banner.style.cssText = 'padding:12px 20px;border-radius:10px;margin-bottom:20px;font-size:0.9rem;text-align:center;';
        const formSection = document.getElementById('formSection');
        formSection?.parentNode?.insertBefore(banner, formSection);
    }
    const remaining = FREE_LIMIT - freeUses;
    if (freeUses < FREE_NUDGE_AT) {
        banner.style.display = 'none';
    } else if (remaining > 0) {
        banner.style.display = 'block';
        banner.style.background = 'rgba(var(--accent-rgb,139,92,246),0.12)';
        banner.style.border = '1px solid rgba(var(--accent-rgb,139,92,246),0.3)';
        banner.innerHTML = `You've used <strong>${freeUses} of ${FREE_LIMIT}</strong> free readings. <a href="/pricing" style="color:var(--accent)">Upgrade for unlimited access →</a>`;
    } else {
        banner.style.display = 'block';
        banner.style.background = 'rgba(239,68,68,0.12)';
        banner.style.border = '1px solid rgba(239,68,68,0.3)';
        banner.innerHTML = `You've used all ${FREE_LIMIT} free readings. <a href="/pricing" style="color:#ef4444;font-weight:600">Upgrade to continue →</a>`;
    }
}

function showUpgradeModal() {
    let modal = document.getElementById('upgradeModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'upgradeModal';
        modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.7);display:flex;align-items:center;justify-content:center;z-index:1000;padding:20px;';
        modal.innerHTML = `
            <div style="background:var(--card-bg,#1a1a2e);border-radius:16px;padding:40px;max-width:420px;width:100%;text-align:center;border:1px solid rgba(255,255,255,0.1);">
                <div style="font-size:2.5rem;margin-bottom:16px;">✨</div>
                <h2 style="margin-bottom:12px;color:var(--text)">You've used all 10 free readings</h2>
                <p style="color:var(--text-muted);margin-bottom:28px;line-height:1.6">Upgrade to Premium for unlimited compatibility checks, daily horoscopes, and deeper readings — all for $3.99/month.</p>
                <a href="/pricing" style="display:block;background:var(--accent,#8b5cf6);color:#fff;padding:14px 24px;border-radius:10px;text-decoration:none;font-weight:600;margin-bottom:12px;">See Pricing →</a>
                <button onclick="document.getElementById('upgradeModal').remove()" style="background:none;border:none;color:var(--text-muted);cursor:pointer;font-size:0.9rem;">Maybe later</button>
            </div>
        `;
        document.body.appendChild(modal);
    }
    modal.style.display = 'flex';
}

// --- Location autocomplete dropdown (Nominatim-based) ---
const _locationAC = new Map();

function setupLocationAutocomplete(inputId, latId, lonId) {
    const inputEl = document.getElementById(inputId);
    if (!inputEl) return;

    // Append dropdown to <body> so overflow:hidden on any ancestor cannot clip it
    const dropdown = document.createElement('ul');
    dropdown.className = 'location-dropdown hidden';
    document.body.appendChild(dropdown);

    let timer = null;
    let suggestions = [];
    let activeIdx = -1;
    let destroyed = false;

    function positionDropdown() {
        const r = inputEl.getBoundingClientRect();
        dropdown.style.top   = (r.bottom - 1) + 'px';
        dropdown.style.left  = r.left + 'px';
        dropdown.style.width = r.width + 'px';
    }

    function clearLatLon() {
        if (latId) { const e = document.getElementById(latId); if (e) e.value = ''; }
        if (lonId) { const e = document.getElementById(lonId); if (e) e.value = ''; }
    }

    function renderDropdown(items) {
        suggestions = items;
        activeIdx = -1;
        dropdown.innerHTML = '';
        items.forEach((item, i) => {
            const li = document.createElement('li');
            li.className = 'location-dropdown-item';
            li.textContent = item.display_name;
            li.addEventListener('mousedown', e => { e.preventDefault(); select(i); });
            dropdown.appendChild(li);
        });
        if (items.length > 0) {
            positionDropdown();
            dropdown.classList.remove('hidden');
        } else {
            dropdown.classList.add('hidden');
        }
    }

    function select(i) {
        const item = suggestions[i];
        if (!item) return;
        inputEl.value = item.display_name;
        if (latId) { const e = document.getElementById(latId); if (e) e.value = item.lat; }
        if (lonId) { const e = document.getElementById(lonId); if (e) e.value = item.lon; }
        dropdown.classList.add('hidden');
        suggestions = [];
    }

    function highlightActive() {
        const items = dropdown.querySelectorAll('.location-dropdown-item');
        items.forEach((el, i) => el.classList.toggle('active', i === activeIdx));
        if (activeIdx >= 0) items[activeIdx]?.scrollIntoView({ block: 'nearest' });
    }

    inputEl.addEventListener('input', () => {
        if (destroyed) return;
        clearLatLon();
        clearTimeout(timer);
        const q = inputEl.value.trim();
        if (q.length < 2) { dropdown.classList.add('hidden'); return; }
        timer = setTimeout(async () => {
            try {
                const res = await fetch(`/api/users/city-suggestions?q=${encodeURIComponent(q)}`);
                if (res.ok) renderDropdown(await res.json());
            } catch {}
        }, 280);
    });

    inputEl.addEventListener('keydown', e => {
        if (destroyed || dropdown.classList.contains('hidden')) return;
        const count = suggestions.length;
        if (e.key === 'ArrowDown')      { e.preventDefault(); activeIdx = Math.min(activeIdx + 1, count - 1); highlightActive(); }
        else if (e.key === 'ArrowUp')   { e.preventDefault(); activeIdx = Math.max(activeIdx - 1, 0); highlightActive(); }
        else if (e.key === 'Enter' && activeIdx >= 0) { e.preventDefault(); select(activeIdx); }
        else if (e.key === 'Escape')    { dropdown.classList.add('hidden'); }
    });

    inputEl.addEventListener('blur', () => {
        setTimeout(() => { if (!destroyed) dropdown.classList.add('hidden'); }, 180);
    });

    const onScroll = () => { if (!dropdown.classList.contains('hidden')) positionDropdown(); };
    window.addEventListener('scroll', onScroll, true);
    window.addEventListener('resize', onScroll);

    const destroy = () => {
        destroyed = true;
        clearTimeout(timer);
        dropdown.remove();
        window.removeEventListener('scroll', onScroll, true);
        window.removeEventListener('resize', onScroll);
    };
    _locationAC.set(inputId, destroy);
}

// --- Google Places Autocomplete (overrides Nominatim when API key is configured) ---
window.initGooglePlaces = function() {
    const inputEl = document.getElementById('p2City');
    if (!inputEl) return;
    _locationAC.get('p2City')?.();
    _locationAC.delete('p2City');

    const ac = new google.maps.places.Autocomplete(inputEl, {
        types: ['(cities)'],
        fields: ['name', 'formatted_address', 'geometry']
    });
    document.getElementById('p2CoordToggleBtn')?.classList.add('hidden');

    ac.addListener('place_changed', () => {
        const place = ac.getPlace();
        if (!place.geometry) return;
        const lat = place.geometry.location.lat();
        const lng = place.geometry.location.lng();
        const latEl = document.getElementById('p2Lat');
        const lonEl = document.getElementById('p2Lon');
        if (latEl) latEl.value = lat;
        if (lonEl) lonEl.value = lng;
    });
};

// --- Coordinates toggle ---
function setupCoordToggle(toggleBtnId, coordInputsId, cityInputId, previewId) {
    const toggleBtn  = document.getElementById(toggleBtnId);
    const coordPanel = document.getElementById(coordInputsId);
    const cityInput  = document.getElementById(cityInputId);
    const previewEl  = document.getElementById(previewId);
    if (!toggleBtn || !coordPanel) return;

    toggleBtn.addEventListener('click', () => {
        const isOpen = !coordPanel.classList.contains('hidden');
        if (isOpen) {
            coordPanel.classList.add('hidden');
            toggleBtn.textContent = '📍 Use exact coordinates instead';
            if (cityInput) cityInput.required = true;
            const latEl = document.getElementById('p2Lat');
            const lonEl = document.getElementById('p2Lon');
            if (latEl) latEl.value = '';
            if (lonEl) lonEl.value = '';
        } else {
            coordPanel.classList.remove('hidden');
            toggleBtn.textContent = '✏️ Use city name instead';
            if (previewEl) previewEl.className = 'geocode-preview hidden';
        }
    });
}

async function apiFetch(path, method = 'GET', body = null, token = null) {
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const res = await fetch(API + path, {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined
    });

    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        const err = new Error(data.detail || `Error ${res.status}`);
        err.status = res.status;
        throw err;
    }
    return data;
}
