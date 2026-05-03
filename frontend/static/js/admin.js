/* =====================================================
   Zodovia — Admin Panel (admin.js)
   ===================================================== */

const API = '';

function getToken() { return localStorage.getItem('zodovia_token'); }
function getUser()  { return JSON.parse(localStorage.getItem('zodovia_user') || 'null'); }

let allUsers = [];
let currentFilter = 'all';
let expandedUserId = null;

let currentPaymentFilter = 'pending';

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

    // Verify superuser server-side by trying to load stats
    try {
        const [stats, users] = await Promise.all([
            apiFetch('/api/admin/stats', 'GET', null, token),
            apiFetch('/api/admin/users', 'GET', null, token),
        ]);

        document.getElementById('adminContent').classList.remove('hidden');

        document.getElementById('statTotal').textContent  = stats.total_users;
        document.getElementById('statPaid').textContent   = stats.paid_users;
        document.getElementById('statFree').textContent   = stats.free_users;
        document.getElementById('statCharts').textContent = stats.charts_generated;
        document.getElementById('statCompat').textContent = stats.compatibility_reports;

        allUsers = users;
        renderTable(allUsers);
        setupFilters();

        // Load pending payment count for stat card
        loadPendingCount(token);

    } catch (err) {
        document.getElementById('accessDenied').classList.remove('hidden');
    }
});

async function loadPendingCount(token) {
    try {
        const records = await apiFetch('/api/admin/payments?status=pending', 'GET', null, token);
        document.getElementById('statPendingPayments').textContent = records.length;
    } catch { /* non-critical */ }
}

// ── Admin tab switching ────────────────────────────────────────

function switchAdminTab(tab) {
    ['users', 'payments'].forEach(t => {
        document.getElementById('section-' + t).classList.toggle('visible', t === tab);
        document.getElementById('tab-' + t).classList.toggle('active', t === tab);
    });
    if (tab === 'payments') loadPayments(currentPaymentFilter);
}

// ── Payments section ──────────────────────────────────────────

async function loadPayments(status) {
    currentPaymentFilter = status;
    ['pending','approved','rejected','all'].forEach(s => {
        const el = document.getElementById('pf-' + s);
        if (el) el.classList.toggle('active', s === status);
    });

    const tbody = document.getElementById('paymentTableBody');
    tbody.innerHTML = '<tr class="loading-row"><td colspan="13">Loading…</td></tr>';

    const token = getToken();
    try {
        const records = await apiFetch('/api/admin/payments?status=' + status, 'GET', null, token);
        renderPayments(records);
    } catch (err) {
        tbody.innerHTML = `<tr class="loading-row"><td colspan="13" style="color:#f87171;">${esc(err.message)}</td></tr>`;
    }
}

function renderPayments(records) {
    const tbody = document.getElementById('paymentTableBody');
    if (!records.length) {
        tbody.innerHTML = '<tr class="loading-row"><td colspan="13" class="no-data">No records.</td></tr>';
        return;
    }
    tbody.innerHTML = records.map(r => {
        const statusClass = { pending: 'badge-pending', approved: 'badge-approved', rejected: 'badge-rejected' }[r.status] || '';
        const planLabel   = { one_time: 'One-Time', monthly: 'Monthly', yearly: 'Yearly' }[r.plan] || r.plan || '—';
        const slipLink    = r.slip_view_url
            ? `<a class="slip-link" href="${esc(r.slip_view_url)}" target="_blank" rel="noopener">View 🔗</a>`
            : '—';
        const actions = r.status === 'pending'
            ? `<button class="btn-sm btn-approve" onclick="approvePayment(${r.id})">✅ Approve</button>
               <button class="btn-sm btn-reject"  onclick="rejectPayment(${r.id})" style="margin-left:4px;">❌ Reject</button>`
            : (r.admin_notes ? `<span style="font-size:0.78rem;color:#9985b0;">${esc(r.admin_notes)}</span>` : '—');
        return `<tr>
            <td class="text-muted">${r.id}</td>
            <td style="font-size:0.82rem;">${esc(r.user_email || '—')}</td>
            <td>${planLabel}</td>
            <td style="color:var(--gold);">LKR ${r.amount_lkr || '—'}</td>
            <td>${esc(r.extracted_name || '—')}</td>
            <td style="font-size:0.8rem;">${esc(r.extracted_bank || '—')}</td>
            <td style="font-size:0.8rem;">${esc(r.extracted_reference || '—')}</td>
            <td style="font-size:0.8rem;">${esc(r.extracted_amount || '—')} ${esc(r.extracted_currency || '')}</td>
            <td style="font-size:0.8rem;">${esc(r.extracted_date || '—')}</td>
            <td>${slipLink}</td>
            <td><span class="badge ${statusClass}">${r.status}</span></td>
            <td class="text-muted" style="font-size:0.78rem;">${esc((r.created_at || '').slice(0, 16))}</td>
            <td>${actions}</td>
        </tr>`;
    }).join('');
}

async function approvePayment(id) {
    if (!confirm('Approve this payment and activate the user?')) return;
    const token = getToken();
    try {
        await apiFetch(`/api/admin/payments/${id}/approve`, 'POST', null, token);
        loadPayments(currentPaymentFilter);
        loadPendingCount(token);
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

async function rejectPayment(id) {
    const notes = prompt('Rejection reason (optional):') ?? '';
    const token = getToken();
    try {
        await apiFetch(`/api/admin/payments/${id}/reject`, 'POST', { notes }, token);
        loadPayments(currentPaymentFilter);
        loadPendingCount(token);
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

// --- Table rendering ---

function renderTable(users) {
    const tbody = document.getElementById('userTableBody');
    if (!users.length) {
        tbody.innerHTML = '<tr class="loading-row"><td colspan="9">No users found.</td></tr>';
        return;
    }

    tbody.innerHTML = users.map(u => `
        <tr data-id="${u.id}" onclick="toggleDetail(${u.id})">
            <td class="text-muted">${u.id}</td>
            <td><strong>${esc(u.name)}</strong></td>
            <td class="text-muted">${esc(u.email)}</td>
            <td>
                <span class="badge ${u.is_paid ? 'badge-paid' : 'badge-free'}">
                    ${u.is_paid ? '★ Paid' : 'Free'}
                </span>
            </td>
            <td class="signs">${signs(u)}</td>
            <td class="text-muted">${esc(u.birth_city || '—')}</td>
            <td class="text-muted">${esc(u.reading_focus || '—')}</td>
            <td class="text-muted">${esc(u.created_at || '—')}</td>
            <td class="text-muted">${esc(u.last_login || '—')}</td>
        </tr>
    `).join('');
}

function signs(u) {
    const parts = [u.sun_sign, u.moon_sign, u.rising_sign].filter(Boolean);
    return parts.length ? parts.join(' · ') : '—';
}

// --- Filters ---

function setupFilters() {
    document.getElementById('searchInput').addEventListener('input', applyFilters);
    document.querySelectorAll('#section-users .filter-tab').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#section-users .filter-tab').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentFilter = btn.dataset.filter;
            applyFilters();
        });
    });
}

function applyFilters() {
    const q = document.getElementById('searchInput').value.toLowerCase();
    let filtered = allUsers;

    if (currentFilter === 'paid')  filtered = filtered.filter(u => u.is_paid);
    if (currentFilter === 'free')  filtered = filtered.filter(u => !u.is_paid);
    if (currentFilter === 'chart') filtered = filtered.filter(u => u.has_chart);

    if (q) {
        filtered = filtered.filter(u =>
            (u.name || '').toLowerCase().includes(q) ||
            (u.email || '').toLowerCase().includes(q)
        );
    }

    renderTable(filtered);
}

// --- Detail panel ---

async function toggleDetail(userId) {
    const panel = document.getElementById('detailPanel');

    if (expandedUserId === userId) {
        panel.classList.remove('open');
        expandedUserId = null;
        return;
    }

    expandedUserId = userId;
    panel.classList.add('open');
    document.getElementById('detailTitle').textContent = 'Loading…';
    document.getElementById('detailGrid').innerHTML = '';
    document.getElementById('readingBlocks').innerHTML = '';

    const token = getToken();
    try {
        const u = await apiFetch(`/api/admin/users/${userId}`, 'GET', null, token);

        document.getElementById('detailTitle').textContent = `${u.name} — ${u.email}`;

        const fields = [
            ['ID', u.id],
            ['Email', u.email],
            ['Plan', u.is_paid ? '★ Paid' : 'Free'],
            ['Subscription Status', u.subscription_status],
            ['Birth Date', u.birth_date || '—'],
            ['Birth City', u.birth_city || '—'],
            ['Sun Sign', u.sun_sign || '—'],
            ['Moon Sign', u.moon_sign || '—'],
            ['Rising Sign', u.rising_sign || '—'],
            ['Reading Focus', u.reading_focus || '—'],
            ['Life Event', u.life_event || '—'],
            ['Joined', u.created_at || '—'],
            ['Last Login', u.last_login || '—'],
            // Demographics
            ['Gender', u.gender || '—'],
            ['Marital Status', u.marital_status || '—'],
            ['Occupation', u.occupation || '—'],
            ['Job Type', u.job_type || '—'],
            ['Education', u.education_level || '—'],
            ['Current Location', u.current_location || '—'],
        ];

        document.getElementById('detailGrid').innerHTML = fields.map(([label, val]) => `
            <div class="detail-field">
                <label>${label}</label>
                <span>${esc(String(val))}</span>
            </div>
        `).join('');

        let blocks = '';

        if (u.life_context) {
            blocks += `<div class="reading-block">
                <h4>Life Context</h4>
                <div class="reading-text">${esc(u.life_context)}</div>
            </div>`;
        }

        if (u.full_reading) {
            blocks += `<div class="reading-block">
                <h4>Full Reading (Paid)</h4>
                <div class="reading-text">${esc(u.full_reading)}</div>
            </div>`;
        } else if (u.free_reading) {
            blocks += `<div class="reading-block">
                <h4>Free Reading</h4>
                <div class="reading-text">${esc(u.free_reading)}</div>
            </div>`;
        } else {
            blocks += '<p class="no-data" style="margin-top:1rem;">No chart reading generated yet.</p>';
        }

        document.getElementById('readingBlocks').innerHTML = blocks;

    } catch (err) {
        document.getElementById('detailTitle').textContent = 'Error loading user';
        document.getElementById('detailGrid').innerHTML = `<p style="color:#ff8080">${esc(err.message)}</p>`;
    }
}

document.getElementById('closeDetail')?.addEventListener('click', () => {
    document.getElementById('detailPanel').classList.remove('open');
    expandedUserId = null;
});

// --- Helpers ---

function esc(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
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
