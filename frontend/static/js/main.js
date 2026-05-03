/* =====================================================
   Zodovia — Landing Page (main.js)
   ===================================================== */

const API = '';  // same origin

// --- Auth state ---
function getToken() { return localStorage.getItem('zodovia_token'); }
function getUser()  { return JSON.parse(localStorage.getItem('zodovia_user') || 'null'); }
function setAuth(token, user) {
    localStorage.setItem('zodovia_token', token);
    localStorage.setItem('zodovia_user', JSON.stringify(user));
}
function clearAuth() {
    localStorage.removeItem('zodovia_token');
    localStorage.removeItem('zodovia_user');
}

// --- On load ---
document.addEventListener('DOMContentLoaded', () => {
    const user  = getUser();
    const token = getToken();
    const planParam = new URLSearchParams(window.location.search).get('plan');
    // Persist plan intent in sessionStorage so it survives page reloads within the same tab
    if (planParam === 'monthly' || planParam === 'yearly') {
        sessionStorage.setItem('zodovia_plan', planParam);
    }
    const validPlan = (planParam === 'monthly' || planParam === 'yearly')
        ? planParam
        : (sessionStorage.getItem('zodovia_plan') || null);

    // If already logged in, hide auth fields and prefill form
    if (user && token) {
        const authSection = document.getElementById('authSection');
        if (authSection) authSection.classList.add('hidden');
        updateNavForUser(user);
        if (user.is_superuser) {
            document.getElementById('adminLink')?.classList.remove('hidden');
        }
        // Fetch fresh profile and prefill the form with saved birth details
        apiFetch('/api/users/me', 'GET', null, token)
            .then(freshUser => {
                localStorage.setItem('zodovia_user', JSON.stringify(freshUser));
                // If came from pricing with a plan param and already has birth data,
                // skip the form and go straight to PayPal checkout
                if (validPlan && freshUser.sun_sign) {
                    return apiFetch(`/api/payments/checkout-url?plan=${validPlan}`, 'GET', null, token)
                        .then(data => { window.location.href = data.checkout_url; })
                        .catch(() => { window.location.href = '/pricing'; });
                }
                prefillForm(freshUser);
                if (validPlan) showPlanBanner(validPlan);
                // Re-evaluate admin link with fresh server data
                if (freshUser.is_superuser) {
                    document.getElementById('adminLink')?.classList.remove('hidden');
                }
            })
            .catch(() => {});
    } else if (validPlan) {
        // Not logged in but came from pricing — show intent banner above the form
        showPlanBanner(validPlan);
    }

    setupBirthForm();
    setupLoginModal();
    setupContextToggle();
    setupFocusPills();
    setupPillGroup('wellnessPills', 'wellnessGoal');
    setupPillGroup('lifePhasePills', 'lifePhase');
    setupOtherEventToggle();
    setupTimeUnknown();
    setupDemoToggle();
    setupSensitiveFlags();
    setupLocationAutocomplete('birthCity', 'birthLat', 'birthLon');
    setupLocationAutocomplete('demoLocation', null, null);
    setupCoordToggle('coordToggleBtn', 'coordInputs', 'birthCity', null);
});

function showPlanBanner(plan) {
    const anchor = document.getElementById('birth-form');
    if (!anchor) return;
    const label = plan === 'yearly' ? window.t('plan_banner_yearly_label') : window.t('plan_banner_monthly_label');
    const banner = document.createElement('div');
    banner.style.cssText = 'background:rgba(212,175,55,0.12);border:1px solid var(--gold);border-radius:10px;padding:14px 20px;text-align:center;margin-bottom:0;font-size:0.92rem;';
    banner.innerHTML = window.t('plan_banner_html').replace('{label}', label);
    anchor.parentNode.insertBefore(banner, anchor);
}

function updateNavForUser(user) {
    const loginBtn = document.getElementById('navLoginBtn');
    if (loginBtn) {
        loginBtn.textContent = window.t('nav_dashboard');
        loginBtn.href = '/dashboard';
        loginBtn.id = '';
    }
}

// --- Prefill form for returning users ---
function prefillForm(user) {
    const nameInput = document.getElementById('name');
    const dateInput = document.getElementById('birthDate');
    const timeInput = document.getElementById('birthTime');
    const cityInput = document.getElementById('birthCity');

    if (nameInput && user.name)        nameInput.value = user.name;
    if (dateInput && user.birth_date)  dateInput.value = user.birth_date;
    if (timeInput && user.birth_time)  timeInput.value = user.birth_time;
    if (cityInput && user.birth_city)  cityInput.value = user.birth_city;

    // Activate the saved reading-focus pill
    if (user.reading_focus) {
        restorePillGroup('focusPills', 'readingFocus', 'readingFocusCustom', user.reading_focus);
    }

    // Restore wellness goal pills
    if (user.wellness_goal) {
        restorePillGroup('wellnessPills', 'wellnessGoal', 'wellnessGoalCustom', user.wellness_goal);
    }

    // Restore sensitive flags
    if (user.sensitive_flags && user.sensitive_flags.length) {
        document.querySelectorAll('.sensitive-flag-cb').forEach(cb => {
            cb.checked = user.sensitive_flags.includes(cb.value);
        });
        document.getElementById('sensitiveContextBox')?.classList.remove('hidden');
    }

    // Restore life phase pills
    if (user.life_phase) {
        restorePillGroup('lifePhasePills', 'lifePhase', 'lifePhaseCustom', user.life_phase);
    }

    // Restore primary intention
    const intentionEl = document.getElementById('primaryIntention');
    if (intentionEl && user.primary_intention) intentionEl.value = user.primary_intention;

    // Prefill demographics
    const setSelect = (id, val) => { const el = document.getElementById(id); if (el && val) el.value = val; };
    setSelect('demoGender',    user.gender);
    setSelect('demoMarital',   user.marital_status);
    setSelect('demoJobType',   user.job_type);
    setSelect('demoEducation', user.education_level);
    const occEl = document.getElementById('demoOccupation');
    if (occEl && user.occupation) occEl.value = user.occupation;
    const locEl = document.getElementById('demoLocation');
    if (locEl && user.current_location) locEl.value = user.current_location;

    // Show a subtle "update" note if they already have a chart
    if (user.sun_sign) {
        const submitBtn = document.getElementById('submitBtn');
        if (submitBtn) submitBtn.textContent = window.t('btn_update_chart');
        const cardSub = document.querySelector('.card-sub');
        if (cardSub) cardSub.textContent = window.t('btn_chart_saved_note');
        // Quick-link to their existing chart
        const chartLink = document.createElement('a');
        chartLink.href = '/chart';
        chartLink.className = 'btn btn-outline btn-full';
        chartLink.style.marginTop = '8px';
        chartLink.textContent = window.t('btn_view_existing_chart');
        submitBtn?.parentNode?.insertBefore(chartLink, submitBtn.nextSibling);
    }
}

// --- Context section toggle ---
function setupContextToggle() {
    const toggle = document.getElementById('contextToggle');
    const body   = document.getElementById('contextBody');
    const arrow  = document.getElementById('contextArrow');
    if (!toggle) return;

    toggle.addEventListener('click', () => {
        const isOpen = !body.classList.contains('hidden');
        body.classList.toggle('hidden', isOpen);
        arrow.classList.toggle('open', !isOpen);
    });
}

// Restore a pill group from a saved value — handles custom (non-preset) values
function restorePillGroup(containerId, hiddenInputId, customInputId, savedValue) {
    const container  = document.getElementById(containerId);
    const hiddenInput = document.getElementById(hiddenInputId);
    const customInput = document.getElementById(customInputId);
    if (!container || !hiddenInput || !savedValue) return;

    container.querySelectorAll('.focus-pill').forEach(p => p.classList.remove('active'));
    const match = container.querySelector(`.focus-pill[data-value="${savedValue}"]`);
    if (match) {
        match.classList.add('active');
        hiddenInput.value = savedValue;
    } else if (customInput) {
        // Custom value — activate the "Other" pill and pre-fill the input
        const otherPill = container.querySelector('.focus-pill-other');
        if (otherPill) otherPill.classList.add('active');
        customInput.value = savedValue;
        customInput.classList.remove('hidden');
        hiddenInput.value = savedValue;
    }
}

// --- Focus area pills (reading focus inside the optional section) ---
function setupFocusPills() {
    setupPillGroup('focusPills', 'readingFocus');
}

// --- Generic pill group with optional "Other" custom input ---
function setupPillGroup(containerId, hiddenInputId) {
    const container = document.getElementById(containerId);
    const hiddenInput = document.getElementById(hiddenInputId);
    if (!container || !hiddenInput) return;

    // Custom text input — sibling immediately after the container
    const customInput = container.parentElement?.querySelector('.pill-custom-input');

    function activatePill(pill) {
        container.querySelectorAll('.focus-pill').forEach(p => p.classList.remove('active'));
        pill.classList.add('active');
    }

    container.querySelectorAll('.focus-pill').forEach(pill => {
        pill.addEventListener('click', () => {
            if (pill.dataset.value === '__other__') {
                activatePill(pill);
                if (customInput) {
                    customInput.classList.remove('hidden');
                    customInput.focus();
                    hiddenInput.value = customInput.value.trim();
                }
            } else {
                activatePill(pill);
                hiddenInput.value = pill.dataset.value;
                if (customInput) {
                    customInput.classList.add('hidden');
                    customInput.value = '';
                }
            }
        });
    });

    if (customInput) {
        customInput.addEventListener('input', () => {
            hiddenInput.value = customInput.value.trim();
        });
        customInput.addEventListener('blur', () => {
            if (!customInput.value.trim()) {
                // Revert to first non-other pill
                const firstPill = container.querySelector('.focus-pill:not(.focus-pill-other)');
                if (firstPill) { activatePill(firstPill); hiddenInput.value = firstPill.dataset.value; }
                customInput.classList.add('hidden');
            }
        });
    }
}

// --- Other event description toggle ---
function setupOtherEventToggle() {
    const select = document.getElementById('lifeEvent');
    const group  = document.getElementById('otherEventGroup');
    if (!select || !group) return;

    select.addEventListener('change', () => {
        group.style.display = select.value === 'other' ? '' : 'none';
        if (select.value !== 'other') {
            document.getElementById('otherEventDesc').value = '';
        }
    });
}

// --- Birth Data Form ---
function setupBirthForm() {
    const form = document.getElementById('birthForm');
    if (!form) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn      = document.getElementById('submitBtn');
        const errorEl  = document.getElementById('formError');
        errorEl.classList.add('hidden');

        const birthDate = form.birth_date.value;
        const birthTime = form.birth_time.value;
        const birthCity = form.birth_city.value.trim();
        const name      = form.name.value.trim();

        // Collect optional context
        const readingFocus   = document.getElementById('readingFocus')?.value || null;
        const rawEvent       = document.getElementById('lifeEvent')?.value || null;
        const otherEventDesc = document.getElementById('otherEventDesc')?.value?.trim() || null;
        const rawContext     = document.getElementById('lifeContext')?.value?.trim() || null;

        // If "other" was chosen with a description, fold that description into life_context
        // and skip the generic "other" event tag so Claude reads the real situation.
        // If no description was given, keep "other" as the event tag (generic fallback).
        const hasOtherDesc = rawEvent === 'other' && otherEventDesc;
        const lifeEvent  = hasOtherDesc ? null : (rawEvent || null);
        const baseContext = hasOtherDesc
            ? (rawContext ? `Upcoming event: ${otherEventDesc}\n\n${rawContext}` : `Upcoming event: ${otherEventDesc}`)
            : rawContext;
        const sensitiveCtx = document.getElementById('sensitiveContext')?.value?.trim() || null;
        const lifeContext = sensitiveCtx
            ? (baseContext ? `${baseContext}\n\nSensitive context shared by user: ${sensitiveCtx}` : `Sensitive context shared by user: ${sensitiveCtx}`)
            : baseContext;

        const originalBtnText = btn.textContent;
        btn.disabled = true;
        btn.textContent = window.t('btn_reading_cosmos');

        try {
            let token = getToken();

            // If not logged in, register first
            if (!token) {
                const email    = form.email?.value?.trim();
                const password = form.password?.value;

                if (!email || !password) {
                    showError(errorEl, window.t('form_err_enter_credentials'));
                    return;
                }
                if (password.length < 8) {
                    showError(errorEl, window.t('form_err_password_min'));
                    return;
                }

                let authRes;
                try {
                    authRes = await apiFetch('/api/users/register', 'POST', { email, password, name });
                } catch (regErr) {
                    if (regErr.message === 'Email already registered') {
                        authRes = await apiFetch('/api/users/login', 'POST', { email, password });
                    } else {
                        throw regErr;
                    }
                }
                setAuth(authRes.access_token, authRes.user);
                token = authRes.access_token;
            }

            // Collect optional exact coordinates
            const birthLat = parseFloat(document.getElementById('birthLat')?.value);
            const birthLon = parseFloat(document.getElementById('birthLon')?.value);
            const hasCoords = !isNaN(birthLat) && !isNaN(birthLon);

            // Collect optional demographics
            const gender        = document.getElementById('demoGender')?.value    || undefined;
            const maritalStatus = document.getElementById('demoMarital')?.value   || undefined;
            const jobType       = document.getElementById('demoJobType')?.value   || undefined;
            const education     = document.getElementById('demoEducation')?.value || undefined;
            const occupation    = document.getElementById('demoOccupation')?.value?.trim() || undefined;
            const currentLoc    = document.getElementById('demoLocation')?.value?.trim()  || undefined;

            // Collect wellness profile
            const wellnessGoal       = document.getElementById('wellnessGoal')?.value    || undefined;
            const lifePhaseVal       = document.getElementById('lifePhase')?.value       || undefined;
            const primaryIntention   = document.getElementById('primaryIntention')?.value?.trim() || undefined;
            const sensitiveFlags     = Array.from(document.querySelectorAll('.sensitive-flag-cb:checked')).map(cb => cb.value);


            // Submit birth data
            await apiFetch('/api/users/birth-data', 'POST', {
                birth_date: birthDate,
                birth_time: birthTime,
                birth_city: birthCity,
                name,
                ...(hasCoords ? { birth_lat: birthLat, birth_lon: birthLon } : {}),
                reading_focus:      readingFocus      || undefined,
                life_context:       lifeContext       || undefined,
                life_event:         lifeEvent         || undefined,
                gender,
                marital_status:     maritalStatus,
                job_type:           jobType,
                education_level:    education,
                occupation,
                current_location:   currentLoc,
                wellness_goal:      wellnessGoal,
                life_phase:         lifePhaseVal,
                primary_intention:  primaryIntention,
                sensitive_flags:    sensitiveFlags.length ? sensitiveFlags : undefined,
            }, token);

            // If user came from pricing with a plan param, go straight to checkout
            const submitPlan = new URLSearchParams(window.location.search).get('plan')
                || sessionStorage.getItem('zodovia_plan');
            if (submitPlan === 'monthly' || submitPlan === 'yearly') {
                sessionStorage.removeItem('zodovia_plan');
                try {
                    const checkout = await apiFetch(`/api/payments/checkout-url?plan=${submitPlan}`, 'GET', null, token);
                    window.location.href = checkout.checkout_url;
                } catch {
                    window.location.href = '/chart';
                }
            } else {
                window.location.href = '/chart';
            }

        } catch (err) {
            showError(errorEl, err.message || 'Something went wrong. Please try again.');
        } finally {
            btn.disabled = false;
            btn.textContent = originalBtnText;
        }
    });
}

// --- Login Modal ---
function setupLoginModal() {
    const navLoginBtn  = document.getElementById('navLoginBtn');
    const modal        = document.getElementById('loginModal');
    const overlay      = document.getElementById('modalOverlay');
    const closeBtn     = document.getElementById('modalClose');
    const loginForm    = document.getElementById('loginForm');
    const loginError   = document.getElementById('loginError');

    if (!modal) return;

    navLoginBtn?.addEventListener('click', (e) => {
        e.preventDefault();
        modal.classList.remove('hidden');
    });
    overlay?.addEventListener('click', () => modal.classList.add('hidden'));
    closeBtn?.addEventListener('click', () => modal.classList.add('hidden'));

    loginForm?.addEventListener('submit', async (e) => {
        e.preventDefault();
        loginError.classList.add('hidden');

        const email    = document.getElementById('loginEmail').value.trim();
        const password = document.getElementById('loginPassword').value;

        try {
            const res = await apiFetch('/api/users/login', 'POST', { email, password });
            setAuth(res.access_token, res.user);
            // If user came from pricing, redirect to PayPal checkout
            const loginPlan = new URLSearchParams(window.location.search).get('plan')
                || sessionStorage.getItem('zodovia_plan');
            if (loginPlan === 'monthly' || loginPlan === 'yearly') {
                sessionStorage.removeItem('zodovia_plan');
                try {
                    const checkout = await apiFetch(`/api/payments/checkout-url?plan=${loginPlan}`, 'GET', null, res.access_token);
                    window.location.href = checkout.checkout_url;
                    return;
                } catch { /* fall through to normal redirect */ }
            }
            if (res.user.is_paid || res.user.is_superuser) {
                window.location.href = '/dashboard';
            } else if (res.user.sun_sign) {
                window.location.href = '/chart';
            } else {
                window.location.href = '/';
            }
        } catch (err) {
            showError(loginError, err.message || window.t('form_err_login'));
        }
    });
}

// --- Helpers ---
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

function showError(el, msg) {
    el.textContent = msg;
    el.classList.remove('hidden');
}

// --- Birth time unknown toggle ---
function setupTimeUnknown() {
    const checkbox = document.getElementById('timeUnknown');
    const timeInput = document.getElementById('birthTime');
    const note = document.getElementById('timeUnknownNote');
    if (!checkbox || !timeInput) return;

    checkbox.addEventListener('change', () => {
        if (checkbox.checked) {
            timeInput.value = '12:00';
            timeInput.disabled = true;
            note?.classList.remove('hidden');
        } else {
            timeInput.disabled = false;
            note?.classList.add('hidden');
        }
    });
}

// --- Demographics toggle ---
function setupDemoToggle() {
    const toggle = document.getElementById('demoToggle');
    const body   = document.getElementById('demoBody');
    const arrow  = document.getElementById('demoArrow');
    if (!toggle) return;

    toggle.addEventListener('click', () => {
        const isOpen = !body.classList.contains('hidden');
        body.classList.toggle('hidden', isOpen);
        arrow.classList.toggle('open', !isOpen);
    });
}

// --- Sensitive flags: show/hide context textarea ---
function setupSensitiveFlags() {
    const cbs  = document.querySelectorAll('.sensitive-flag-cb');
    const box  = document.getElementById('sensitiveContextBox');
    if (!cbs.length || !box) return;

    function syncBox() {
        const anyChecked = Array.from(cbs).some(cb => cb.checked);
        box.classList.toggle('hidden', !anyChecked);
    }
    cbs.forEach(cb => cb.addEventListener('change', syncBox));
}

// --- Location autocomplete dropdown (Nominatim-based, works without any API key) ---
const _locationAC = new Map(); // inputId → destroy()

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
    let controller = null;

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

    function setLatLon(lat, lon) {
        if (latId) { const e = document.getElementById(latId); if (e) e.value = lat; }
        if (lonId) { const e = document.getElementById(lonId); if (e) e.value = lon; }
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
        setLatLon(item.lat, item.lon);
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
        controller?.abort();
        const q = inputEl.value.trim();
        if (q.length < 2) { dropdown.classList.add('hidden'); return; }
        timer = setTimeout(async () => {
            controller = new AbortController();
            try {
                const res = await fetch(`/api/users/city-suggestions?q=${encodeURIComponent(q)}`, { signal: controller.signal });
                if (res.ok) renderDropdown(await res.json());
            } catch (e) {
                if (e.name !== 'AbortError') renderDropdown([]);
            }
        }, 280);
    });

    inputEl.addEventListener('keydown', e => {
        if (destroyed || dropdown.classList.contains('hidden')) return;
        const count = suggestions.length;
        if (e.key === 'ArrowDown')  { e.preventDefault(); activeIdx = Math.min(activeIdx + 1, count - 1); highlightActive(); }
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
    const AC = google.maps.places.Autocomplete;
    const FIELDS = ['name', 'formatted_address', 'geometry'];

    function setupGP(inputId, latId, lonId, coordToggleId) {
        const inputEl = document.getElementById(inputId);
        if (!inputEl) return;
        // Destroy Nominatim autocomplete if it was set up first
        _locationAC.get(inputId)?.();
        _locationAC.delete(inputId);

        const ac = new AC(inputEl, { types: ['(cities)'], fields: FIELDS });
        if (coordToggleId) document.getElementById(coordToggleId)?.classList.add('hidden');

        ac.addListener('place_changed', () => {
            const place = ac.getPlace();
            if (!place.geometry) return;
            const lat = place.geometry.location.lat();
            const lng = place.geometry.location.lng();
            if (latId) { const e = document.getElementById(latId); if (e) e.value = lat; }
            if (lonId) { const e = document.getElementById(lonId); if (e) e.value = lng; }
        });
    }

    setupGP('birthCity',   'birthLat', 'birthLon', 'coordToggleBtn');
    setupGP('demoLocation', null,       null,       null);
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
            // Close: back to city-only mode
            coordPanel.classList.add('hidden');
            toggleBtn.textContent = window.t('coord_use_coords');
            if (cityInput) cityInput.required = true;
            // Clear coords
            const latEl = document.getElementById('birthLat');
            const lonEl = document.getElementById('birthLon');
            if (latEl) latEl.value = '';
            if (lonEl) lonEl.value = '';
        } else {
            // Open: show coord inputs, hide geocode preview
            coordPanel.classList.remove('hidden');
            toggleBtn.textContent = window.t('coord_use_city');
            if (previewEl) previewEl.className = 'geocode-preview hidden';
        }
    });
}
