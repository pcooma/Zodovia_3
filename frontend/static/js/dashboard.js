/* =====================================================
   Zodovia — Dashboard Page (dashboard.js)
   ===================================================== */

const API = '';
const TRIAL_LIMIT = 5;

function getToken() { return localStorage.getItem('zodovia_token'); }
function getUser()  { return JSON.parse(localStorage.getItem('zodovia_user') || 'null'); }

document.addEventListener('DOMContentLoaded', async () => {
    const token = getToken();
    const user  = getUser();

    if (!token || !user) {
        window.location.href = '/';
        return;
    }

    document.getElementById('logoutBtn')?.addEventListener('click', (e) => {
        e.preventDefault();
        localStorage.clear();
        window.location.href = '/';
    });

    document.getElementById('navUserName').textContent = user.name || '';

    // Check if user just returned from PayPal checkout
    const urlParams = new URLSearchParams(window.location.search);
    const justActivated = urlParams.has('activated');

    // Fetch fresh user profile to check paid status
    try {
        const freshUser = await apiFetch('/api/users/me', 'GET', null, token);
        localStorage.setItem('zodovia_user', JSON.stringify(freshUser));

        // If returning from PayPal but subscription not yet active, poll until IPN arrives
        if (justActivated && !freshUser.is_paid && !freshUser.is_superuser) {
            document.getElementById('loadingState').classList.add('hidden');
            await pollForActivation(token);
            return;
        }

        // Clean ?activated=1 from URL without reload
        if (justActivated) {
            history.replaceState(null, '', '/dashboard');
        }

        document.getElementById('loadingState').classList.add('hidden');

        if (freshUser.is_superuser) {
            document.getElementById('adminLink')?.classList.remove('hidden');
        }

        const isFull  = freshUser.is_paid || freshUser.is_superuser;
        const trialLeft = isFull ? null : Math.max(0, TRIAL_LIMIT - (freshUser.trial_uses || 0));

        if (!isFull && trialLeft <= 0) {
            showUpgradePrompt();
            return;
        }

        renderDashboard(freshUser);
        if (!isFull && trialLeft > 0) showTrialBanner(trialLeft);
        // Load intention only after horoscope completes — they share the same DB record
        loadHoroscope(token).then(() => loadIntention(token)).catch(() => loadIntention(token));
        setupForecasts(token);
        setupAskStars(token);

    } catch (err) {
        window.location.href = '/';
    }
});

async function pollForActivation(token) {
    const banner  = document.getElementById('activationBanner');
    const msgEl   = document.getElementById('activationMsg');
    if (banner) banner.classList.remove('hidden');

    const MAX_ATTEMPTS = 10;
    const INTERVAL_MS  = 3000;

    for (let i = 0; i < MAX_ATTEMPTS; i++) {
        await new Promise(r => setTimeout(r, INTERVAL_MS));
        try {
            const u = await apiFetch('/api/users/me', 'GET', null, token);
            localStorage.setItem('zodovia_user', JSON.stringify(u));
            if (u.is_paid || u.is_superuser) {
                if (msgEl) msgEl.textContent = window.t('dash_premium_activated');
                await new Promise(r => setTimeout(r, 1200));
                history.replaceState(null, '', '/dashboard');
                window.location.reload();
                return;
            }
        } catch { /* ignore transient errors */ }
    }

    // IPN still hasn't arrived after ~30s — show fallback message
    if (msgEl) {
        msgEl.textContent = window.t('dash_activation_delayed');
        const sub = banner.querySelector('p:last-child');
        if (sub) sub.innerHTML = window.t('dash_activation_fallback_html');
    }
}

function showUpgradePrompt() {
    document.getElementById('upgradePrompt').classList.remove('hidden');
    // Both plan buttons are plain <a href="/pricing"> — no JS needed
}

function showTrialBanner(usesLeft) {
    const banner = document.getElementById('trialBanner');
    if (!banner) return;
    const label = usesLeft === 1
        ? window.t('dash_trial_preview_1')
        : window.t('dash_trial_previews_n').replace('{n}', usesLeft);
    banner.innerHTML = `✨ ${label} — <a href="/pricing" style="color:var(--gold);font-weight:600">${window.t('dash_trial_upgrade')}</a>`;
    banner.classList.remove('hidden');
}

function renderDashboard(user) {
    // Apply sign theme
    if (user.sun_sign) document.body.setAttribute('data-sign', user.sun_sign);

    // Greeting
    const now = new Date();
    const hour = now.getHours();
    const greeting = hour < 12 ? window.t('dash_greeting_morning') : hour < 18 ? window.t('dash_greeting_afternoon') : window.t('dash_greeting_evening');
    const dateStr = now.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });

    document.getElementById('greetingDate').textContent = dateStr;
    document.getElementById('greetingHeadline').textContent = `${greeting}, ${user.name || window.t('dash_greeting_fallback')} ✨`;
    document.getElementById('greetingSign').textContent =
        `${user.sun_sign || ''} Sun · ${user.moon_sign || ''} Moon · ${user.rising_sign || ''} Rising`;

    // Stats
    document.getElementById('statSun').textContent    = user.sun_sign    || '—';
    document.getElementById('statMoon').textContent   = user.moon_sign   || '—';
    document.getElementById('statRising').textContent = user.rising_sign || '—';

    // Streak
    const streak = user.current_streak || 0;
    if (streak >= 2) {
        const streakLine = document.getElementById('streakLine');
        if (streakLine) {
            streakLine.textContent = window.t('dash_streak').replace('{n}', streak);
            streakLine.classList.remove('hidden');
        }
    }

    document.getElementById('dashboardContent').classList.remove('hidden');
}

async function loadHoroscope(token) {
    const dateLabel = document.getElementById('horoscopeDate');
    const loading   = document.getElementById('horoscopeLoading');
    const content   = document.getElementById('horoscopeContent');

    const today = new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });
    dateLabel.textContent = today;

    try {
        const res = await apiFetch('/api/charts/horoscope/today', 'GET', null, token);
        loading.classList.add('hidden');
        content.innerHTML = formatText(res.content);
        content.classList.remove('hidden');
    } catch (err) {
        if (err.status === 402) {
            window.location.reload(); // trial just ran out — reload to show upgrade prompt
            return;
        }
        loading.textContent = window.t('dash_err_horoscope');
    }
}

function setupForecasts(token) {
    _setupForecastCard({
        btnId: 'weekForecastBtn',
        loadingId: 'weekForecastLoading',
        contentId: 'weekForecastContent',
        endpoint: '/api/charts/forecast/week',
        token,
    });
    _setupForecastCard({
        btnId: 'monthForecastBtn',
        loadingId: 'monthForecastLoading',
        contentId: 'monthForecastContent',
        endpoint: '/api/charts/forecast/month',
        token,
    });
}

function _setupForecastCard({ btnId, loadingId, contentId, endpoint, token }) {
    const btn     = document.getElementById(btnId);
    const loading = document.getElementById(loadingId);
    const content = document.getElementById(contentId);
    if (!btn) return;

    let loaded = false;

    btn.addEventListener('click', async () => {
        if (loaded) {
            // Toggle visibility
            content.classList.toggle('hidden');
            btn.textContent = content.classList.contains('hidden') ? window.t('dash_forecast_view') : window.t('dash_forecast_hide');
            return;
        }

        btn.disabled = true;
        btn.textContent = window.t('dash_forecast_loading_btn');
        loading.classList.remove('hidden');

        try {
            const res = await apiFetch(endpoint, 'GET', null, token);
            loading.classList.add('hidden');
            content.innerHTML = formatText(res.content);
            content.classList.remove('hidden');
            btn.textContent = window.t('dash_forecast_hide');
            btn.disabled = false;
            loaded = true;
        } catch (err) {
            loading.textContent = err.message || window.t('dash_err_forecast');
            btn.textContent = window.t('dash_forecast_view');
            btn.disabled = false;
        }
    });
}

async function loadIntention(token) {
    const loading = document.getElementById('intentionLoading');
    const content = document.getElementById('intentionContent');

    try {
        const res = await apiFetch('/api/charts/intention/today', 'GET', null, token);
        loading.classList.add('hidden');
        if (res.intention) {
            content.textContent = res.intention;
            content.classList.remove('hidden');
        } else {
            loading.textContent = window.t('dash_intention_locked');
        }
    } catch (err) {
        if (loading) loading.textContent = window.t('dash_err_intention');
    }
}

const ASK_MAX = 600;

function setupAskStars(token) {
    const toggleBtn  = document.getElementById('askToggleBtn');
    const form       = document.getElementById('dashAskForm');
    const askBtn     = document.getElementById('dashAskBtn');
    const textarea   = document.getElementById('dashQuestion');
    const loadingEl  = document.getElementById('dashAskLoading');
    const resultEl   = document.getElementById('dashAskResult');
    const counterEl  = document.getElementById('dashAskCounter');

    if (textarea) {
        textarea.maxLength = ASK_MAX;
        textarea.addEventListener('input', () => {
            const left = ASK_MAX - textarea.value.length;
            if (counterEl) {
                counterEl.textContent = window.t('chars_left').replace('{n}', left);
                counterEl.classList.toggle('counter-warn', left < 80);
            }
        });
    }

    toggleBtn?.addEventListener('click', () => {
        form.classList.toggle('hidden');
        toggleBtn.textContent = form.classList.contains('hidden') ? window.t('dash_ask_open') : window.t('dash_ask_close');
        if (!form.classList.contains('hidden')) textarea?.focus();
    });

    askBtn?.addEventListener('click', async () => {
        const question = textarea.value.trim();
        if (!question) { textarea?.focus(); return; }
        if (question.length > ASK_MAX) {
            resultEl.textContent = window.t('dash_err_question_long').replace('{n}', ASK_MAX);
            resultEl.style.color = '#ff8080';
            resultEl.classList.remove('hidden');
            return;
        }

        askBtn.disabled = true;
        askBtn.textContent = window.t('dash_ask_consulting');
        loadingEl.classList.remove('hidden');
        resultEl.classList.add('hidden');
        resultEl.style.color = '';

        try {
            const res = await apiFetch('/api/charts/ask-stars', 'POST', { question }, token);
            resultEl.innerHTML = formatText(res.answer);
            resultEl.classList.remove('hidden');
            // Clear textarea after a successful answer
            textarea.value = '';
            if (counterEl) counterEl.textContent = window.t('chars_left').replace('{n}', ASK_MAX);
        } catch (err) {
            if (err.status === 429) {
                resultEl.textContent = window.t('dash_err_daily_limit');
            } else {
                resultEl.textContent = err.message || window.t('dash_err_answer');
            }
            resultEl.style.color = '#ff8080';
            resultEl.classList.remove('hidden');
        } finally {
            askBtn.disabled = false;
            askBtn.textContent = window.t('dash_ask_submit');
            loadingEl.classList.add('hidden');
        }
    });
}

function formatText(text) {
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
