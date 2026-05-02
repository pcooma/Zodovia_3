/* =====================================================
   Zodovia — Chart Page (chart.js)
   ===================================================== */

const API = '';

function getToken() { return localStorage.getItem('zodovia_token'); }
function getUser()  { return JSON.parse(localStorage.getItem('zodovia_user') || 'null'); }

const SIGN_SYMBOLS = {
    Aries:'♈', Taurus:'♉', Gemini:'♊', Cancer:'♋',
    Leo:'♌', Virgo:'♍', Libra:'♎', Scorpio:'♏',
    Sagittarius:'♐', Capricorn:'♑', Aquarius:'♒', Pisces:'♓'
};

document.addEventListener('DOMContentLoaded', async () => {
    const token = getToken();
    if (!token) {
        window.location.href = '/';
        return;
    }

    document.getElementById('logoutBtn')?.addEventListener('click', (e) => {
        e.preventDefault();
        localStorage.clear();
        window.location.href = '/';
    });

    try {
        const chart = await apiFetch('/api/charts/my-chart', 'GET', null, token);
        renderChart(chart);
    } catch (err) {
        const msg = err.message || '';
        if (msg.includes('birth data') || msg.includes('401') || msg.includes('Unauthorized')) {
            window.location.href = '/';
        } else {
            document.getElementById('loadingState').classList.add('hidden');
            document.getElementById('errorMessage').textContent =
                msg || 'Could not load your chart. Please try again later.';
            document.getElementById('errorState').classList.remove('hidden');
        }
    }
});

function renderChart(chart) {
    const user = getUser();

    // Apply sign-specific theme to body
    document.body.setAttribute('data-sign', chart.sun_sign);

    // Show dashboard + compatibility links for paid users and superusers
    if (chart.is_paid || user?.is_superuser) {
        document.getElementById('dashboardLink')?.classList.remove('hidden');
        document.getElementById('compatibilityLink')?.classList.remove('hidden');
    }

    // Show admin link for superusers
    if (user?.is_superuser) {
        document.getElementById('adminLink')?.classList.remove('hidden');
    }

    // Big Three
    const nameLabel = user?.name ? `${user.name}'s Chart` : 'Your Chart';
    document.getElementById('chartUserName').textContent = nameLabel;
    document.getElementById('sunSign').textContent =
        `${SIGN_SYMBOLS[chart.sun_sign] || ''} ${chart.sun_sign}`;
    document.getElementById('moonSign').textContent =
        `${SIGN_SYMBOLS[chart.moon_sign] || ''} ${chart.moon_sign}`;
    document.getElementById('risingSign').textContent =
        `${SIGN_SYMBOLS[chart.rising_sign] || ''} ${chart.rising_sign}`;

    if (chart.is_paid) {
        document.getElementById('readingTitle').textContent = '✨ Your Full Reading';
    }

    // Reading body
    const readingBody = document.getElementById('readingBody');
    readingBody.innerHTML = formatReading(chart.free_reading);

    // Planet Grid
    const grid = document.getElementById('planetGrid');
    const planetEmojis = {
        Sun:'☀️', Moon:'🌙', Mercury:'☿', Venus:'♀️',
        Mars:'♂️', Jupiter:'♃', Saturn:'♄',
        Uranus:'⛢', Neptune:'♆', Pluto:'♇'
    };
    for (const [name, info] of Object.entries(chart.planets)) {
        const item = document.createElement('div');
        item.className = 'planet-item';
        const emoji = planetEmojis[name] || '🌟';
        const retro = info.retrograde ? '<span class="planet-retro">℞ Retrograde</span>' : '';
        item.innerHTML = `
            <div class="planet-name">${emoji} ${name}</div>
            <div class="planet-sign">${info.emoji} ${info.sign}</div>
            <div class="planet-meta">House ${info.house} · ${info.degree}° ${retro}</div>
        `;
        grid.appendChild(item);
    }

    // Show/hide Ask the Stars and paywall based on paid status
    if (chart.is_paid) {
        document.getElementById('askStarsSection').style.display = '';
        document.getElementById('askStarsTeaser').style.display = 'none';
        document.getElementById('paywallSection')?.classList.add('hidden');
        setupAskStars();
    } else {
        document.getElementById('askStarsSection').style.display = 'none';
        document.getElementById('askStarsTeaser').style.display = '';
        setupPaywall();
    }

    // Draw natal chart wheel and rising sign section
    drawChartWheel(chart);
    renderRisingSpotlight(chart);

    // Show content, hide loader
    document.getElementById('loadingState').classList.add('hidden');
    document.getElementById('chartContent').classList.remove('hidden');
}

// ─── Chart Wheel ───────────────────────────────────────────────────────────

const SIGNS_ORDER = [
    'Aries','Taurus','Gemini','Cancer','Leo','Virgo',
    'Libra','Scorpio','Sagittarius','Capricorn','Aquarius','Pisces'
];

const SIGN_ELEMENTS = {
    Aries:'fire', Leo:'fire', Sagittarius:'fire',
    Taurus:'earth', Virgo:'earth', Capricorn:'earth',
    Gemini:'air', Libra:'air', Aquarius:'air',
    Cancer:'water', Scorpio:'water', Pisces:'water'
};

const ELEM_COLOR = { fire:'#ff6040', earth:'#7ab648', air:'#e8c040', water:'#4a9ecc' };
const ELEM_PALE  = {
    fire:'rgba(255,96,64,0.14)', earth:'rgba(122,182,72,0.14)',
    air:'rgba(232,192,64,0.14)', water:'rgba(74,158,204,0.14)'
};

// Separate glyph map for SVG use (avoid clash with SIGN_SYMBOLS already defined above)
const SIGN_GLYPHS = {
    Aries:'♈', Taurus:'♉', Gemini:'♊', Cancer:'♋', Leo:'♌', Virgo:'♍',
    Libra:'♎', Scorpio:'♏', Sagittarius:'♐', Capricorn:'♑', Aquarius:'♒', Pisces:'♓'
};

const PLANET_GLYPHS_SVG = {
    Sun:'☉', Moon:'☽', Mercury:'☿', Venus:'♀', Mars:'♂',
    Jupiter:'♃', Saturn:'♄', Uranus:'⛢', Neptune:'♆', Pluto:'♇'
};

const SIGN_MODALITIES = {
    Aries:'Cardinal', Cancer:'Cardinal', Libra:'Cardinal', Capricorn:'Cardinal',
    Taurus:'Fixed', Leo:'Fixed', Scorpio:'Fixed', Aquarius:'Fixed',
    Gemini:'Mutable', Virgo:'Mutable', Sagittarius:'Mutable', Pisces:'Mutable'
};

const RISING_DATA = {
    Aries: {
        intro: 'With Aries rising, you stride into every room as if you own it — energetic, direct, and impossible to ignore. People sense your drive and readiness for action before you say a word.',
        firstImpression: 'Confident, assertive, and full of fire. Your bold energy is felt immediately.',
        presence: 'High-energy and magnetic — you radiate urgency and excitement everywhere you go.',
        lifeApproach: 'Head-first and fearless — you jump in and figure it out as you go, always pioneering.'
    },
    Taurus: {
        intro: 'With Taurus rising, you carry yourself with a quiet, grounded strength that immediately puts others at ease. Your calm and reliability make people want to stay in your orbit.',
        firstImpression: 'Warm, composed, and utterly trustworthy. People relax around you before you\'ve said much.',
        presence: 'Unhurried and sensual — you have a natural elegance and deep appreciation for beauty.',
        lifeApproach: 'Patient and methodical — you build things that last and resist being rushed into anything.'
    },
    Gemini: {
        intro: 'With Gemini rising, your wit and curiosity light up every conversation. You appear versatile, youthful, and endlessly interesting — as if you contain multitudes.',
        firstImpression: 'Quick, clever, and communicative. People are drawn into your lively, questioning energy.',
        presence: 'Animated and changeable — your expressions and ideas shift fluidly, keeping others engaged.',
        lifeApproach: 'Curious and adaptable — life is an experiment to collect ideas, stories, and experiences.'
    },
    Cancer: {
        intro: 'With Cancer rising, you project a nurturing warmth that makes people feel instantly at home. Your emotional intelligence reads the room before anyone else does.',
        firstImpression: 'Warm, caring, and intuitively empathetic. Others feel seen and understood in your presence.',
        presence: 'Soft yet powerful — like a safe harbour. You absorb and reflect the emotional energy around you.',
        lifeApproach: 'Feeling-guided and protective — you navigate life by caring deeply for what matters most.'
    },
    Leo: {
        intro: 'With Leo rising, you enter every space with an unmistakable radiance. Charismatic, warm, and magnetic — people notice you without you trying.',
        firstImpression: 'Commanding and generous. You light up rooms and make everyone feel like they matter.',
        presence: 'Regal and warm — there is a natural drama and theatricality to how you carry yourself.',
        lifeApproach: 'With flair and heart — you live fully and expect your unique gifts to be seen and celebrated.'
    },
    Virgo: {
        intro: 'With Virgo rising, you project an aura of precision, intelligence, and quiet competence. People sense that you notice everything — because you do.',
        firstImpression: 'Thoughtful, composed, and discerning. Others trust your analysis and judgment quickly.',
        presence: 'Clean and purposeful — you carry yourself with understated confidence and careful intention.',
        lifeApproach: 'Analytical and improvement-oriented — life is a series of problems worth solving beautifully.'
    },
    Libra: {
        intro: 'With Libra rising, you move through the world with grace and natural charm. You are the diplomat, the peacemaker, the one who makes every interaction feel effortlessly elegant.',
        firstImpression: 'Charming, balanced, and beautiful. Your harmony and fairness draw people in immediately.',
        presence: 'Refined and aesthetic — you bring a sense of ease and beauty to every space you enter.',
        lifeApproach: 'Relational and fair-minded — you seek beauty, balance, and genuine connection in everything.'
    },
    Scorpio: {
        intro: 'With Scorpio rising, you carry an intense, magnetic energy that others sense even before you speak. There is a depth to you that people find both compelling and slightly mysterious.',
        firstImpression: 'Piercing and magnetic — people sense layers beneath the surface and are drawn to discover them.',
        presence: 'Powerful and still, like a deep current under calm water. Your gaze alone communicates volumes.',
        lifeApproach: 'Penetrating and transformative — you seek truth, reject the superficial, and go all the way in.'
    },
    Sagittarius: {
        intro: 'With Sagittarius rising, you project infectious enthusiasm and a freedom-loving energy. People feel uplifted in your presence — as if anything is possible.',
        firstImpression: 'Open, adventurous, and philosophical. Your warmth and laughter disarm people instantly.',
        presence: 'Expansive and inspiring — you carry the energy of someone who has seen a lot and loves life for it.',
        lifeApproach: 'Questing and open-minded — life is a grand adventure with a bigger meaning to uncover.'
    },
    Capricorn: {
        intro: 'With Capricorn rising, you carry yourself with a natural authority and quiet ambition. People sense your competence and substance before you have said much at all.',
        firstImpression: 'Composed and quietly commanding. Others naturally look to you for leadership and steadiness.',
        presence: 'Structured and dignified — you radiate a quiet strength that says "I have everything handled."',
        lifeApproach: 'Strategic and disciplined — you play the long game, building toward enduring success.'
    },
    Aquarius: {
        intro: 'With Aquarius rising, you project an original, slightly unconventional energy that makes people curious about you. You seem to march to a different drummer — and people are fascinated.',
        firstImpression: 'Unique, progressive, and intriguing. Others sense immediately that you see the world differently.',
        presence: 'Cool and observant — there is a detached brilliance in how you analyse and engage with everything.',
        lifeApproach: 'Innovative and collective — you challenge norms and care deeply about improving the whole.'
    },
    Pisces: {
        intro: 'With Pisces rising, you have an otherworldly, dreamy quality that people find instantly intriguing. You seem to feel everything, and others sense your deep empathy before you speak.',
        firstImpression: 'Gentle, ethereal, and deeply compassionate. People feel your empathy the moment they meet you.',
        presence: 'Fluid and enchanting — you blur boundaries, absorbing the world\'s energy and reflecting it back.',
        lifeApproach: 'Intuitive and imaginative — you navigate life through feeling, vision, and quiet spiritual knowing.'
    }
};

function drawChartWheel(chart) {
    const svg = document.getElementById('chartWheel');
    if (!svg) return;

    const cx = 200, cy = 200;
    const R_OUTER = 175;   // outer edge of zodiac sign ring
    const R_SIGN  = 150;   // inner edge of zodiac / outer edge of house ring
    const R_HOUSE = 110;   // inner edge of house ring / outer edge of planet zone
    const R_INNER = 60;    // center circle radius

    const NS = 'http://www.w3.org/2000/svg';
    svg.innerHTML = '';

    // Convert degrees to SVG coordinate point on a circle
    // 0° = right (3-o'clock); angle increases => point moves clockwise on screen
    // (SVG y-axis points down, so sin(θ) > 0 is below center)
    function pt(deg, r) {
        const rad = deg * Math.PI / 180;
        return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
    }

    // Create and append an SVG element with given attributes / optional text
    function el(tag, attrs, text) {
        const e = document.createElementNS(NS, tag);
        for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
        if (text !== undefined) e.textContent = text;
        svg.appendChild(e);
        return e;
    }

    // Build an annular (donut) segment path.
    // The zodiac goes CCW on screen from the Ascendant:
    //   ASC at 180° (left/9-o'clock) → House 2 at 150° (lower-left) → IC at 90° (bottom) …
    // Going from a1 to a2 (a2 = a1 − 30°) traces a CCW arc on screen.
    // In SVG math (y-down): CCW on screen = sweep-flag 0
    //                        CW on screen  = sweep-flag 1
    function arcSeg(a1, a2, r1, r2) {
        const p1o = pt(a1, r2), p2o = pt(a2, r2);
        const p1i = pt(a1, r1), p2i = pt(a2, r1);
        // Each segment = 30° < 180°, so large-arc-flag is always 0
        // Outer: from a1 to a2 going CCW on screen → sweep=0
        // Inner: from a2 back to a1 going CW on screen  → sweep=1
        return `M${p1o.x},${p1o.y} A${r2},${r2},0,0,0,${p2o.x},${p2o.y} ` +
               `L${p2i.x},${p2i.y} A${r1},${r1},0,0,1,${p1i.x},${p1i.y} Z`;
    }

    // Ascendant absolute ecliptic longitude (0–360°)
    const risingIdx = SIGNS_ORDER.indexOf(chart.rising_sign);
    const ascLon    = risingIdx * 30 + (chart.rising_degree || 0);

    // Convert a planet's absolute ecliptic longitude to its SVG angle on the wheel.
    // The ASC sits at SVG 180° (left). Each zodiac degree CCW from ASC = -1° in SVG angle.
    function lonToAngle(lon) {
        const rel = ((lon - ascLon) % 360 + 360) % 360; // 0–360° ahead of ASC
        return (180 - rel + 360) % 360;
    }

    // ── Background disk ──────────────────────────────────────────────────────
    el('circle', { cx, cy, r: R_OUTER, fill: '#09091a', stroke: '#1e1e30', 'stroke-width': '1.5' });

    // ── Zodiac sign ring ─────────────────────────────────────────────────────
    for (let i = 0; i < 12; i++) {
        const signIdx = (risingIdx + i) % 12;
        const sign    = SIGNS_ORDER[signIdx];
        const elem    = SIGN_ELEMENTS[sign];
        // House i+1 cusp angle: 180° − i×30°; segment spans to 180° − (i+1)×30°
        const a1 = 180 - i * 30;
        const a2 = 180 - (i + 1) * 30;

        el('path', { d: arcSeg(a1, a2, R_SIGN, R_OUTER),
                     fill: ELEM_PALE[elem], stroke: '#12122a', 'stroke-width': '0.5' });

        // Sign glyph at arc midpoint
        const mid = pt(a1 - 15, (R_SIGN + R_OUTER) / 2);
        el('text', { x: mid.x, y: mid.y, 'text-anchor': 'middle', 'dominant-baseline': 'middle',
                     'font-size': '15', fill: ELEM_COLOR[elem], 'font-family': 'serif' },
           SIGN_GLYPHS[sign]);
    }

    // ── House ring ───────────────────────────────────────────────────────────
    const AXIS_HOUSES = new Set([1, 4, 7, 10]);
    for (let h = 1; h <= 12; h++) {
        const a1 = 180 - (h - 1) * 30;
        const isAxis = AXIS_HOUSES.has(h);

        // Radial cusp line (from zodiac ring inward to house ring)
        const pOuter = pt(a1, R_SIGN);
        const pInner = pt(a1, R_HOUSE);
        el('line', { x1: pOuter.x, y1: pOuter.y, x2: pInner.x, y2: pInner.y,
                     stroke: isAxis ? '#c9b458' : '#282840',
                     'stroke-width': isAxis ? '1.5' : '0.7' });

        // House number at arc midpoint
        const midH = pt(a1 - 15, (R_SIGN + R_HOUSE) / 2 - 2);
        el('text', { x: midH.x, y: midH.y, 'text-anchor': 'middle', 'dominant-baseline': 'middle',
                     'font-size': '9.5', fill: isAxis ? '#c9b45880' : '#38385880' }, h);
    }

    // Inner house ring border
    el('circle', { cx, cy, r: R_HOUSE, fill: 'none', stroke: '#242438', 'stroke-width': '0.8' });

    // ── Axis lines (ASC–DSC horizon, MC–IC meridian) ─────────────────────────
    const horizL = pt(180, R_OUTER), horizR = pt(0, R_OUTER);
    el('line', { x1: horizL.x, y1: horizL.y, x2: horizR.x, y2: horizR.y,
                 stroke: '#c9b45845', 'stroke-width': '0.8', 'stroke-dasharray': '3,3' });

    const mcPt = pt(270, R_OUTER), icPt = pt(90, R_OUTER);
    el('line', { x1: mcPt.x, y1: mcPt.y, x2: icPt.x, y2: icPt.y,
                 stroke: '#9060ff45', 'stroke-width': '0.8', 'stroke-dasharray': '3,3' });

    // Axis labels
    el('text', { x: horizL.x + 5, y: horizL.y - 5, 'font-size': '8', fill: '#c9b458', 'font-weight': '600' }, 'ASC');
    el('text', { x: horizR.x - 28, y: horizR.y - 5, 'font-size': '8', fill: '#c9b45875' }, 'DSC');
    el('text', { x: mcPt.x - 8, y: mcPt.y + 12, 'font-size': '8', fill: '#9060ff75' }, 'MC');
    el('text', { x: icPt.x - 5, y: icPt.y - 5,  'font-size': '8', fill: '#9060ff75' }, 'IC');

    // ── Planets ──────────────────────────────────────────────────────────────
    // Group by house so we can spread overlapping planets
    const byHouse = {};
    for (const [name, data] of Object.entries(chart.planets)) {
        const h = data.house || 1;
        if (!byHouse[h]) byHouse[h] = [];
        byHouse[h].push({ name, data });
    }

    for (const planets of Object.values(byHouse)) {
        planets.forEach((p, idx) => {
            // Exact angle from the planet's absolute longitude
            const pSignIdx = SIGNS_ORDER.indexOf(p.data.sign);
            const pLon     = pSignIdx * 30 + (p.data.degree || 0);
            const baseAngle = lonToAngle(pLon);

            // Spread multiple planets in the same house to avoid overlap
            const spread = planets.length > 1 ? (idx - (planets.length - 1) / 2) * 11 : 0;
            const angle  = baseAngle + spread;

            // Vary radius slightly for further de-collision
            const r = Math.min(R_INNER + 16 + (idx % 3) * 15, R_HOUSE - 14);
            const pos = pt(angle, r);

            // Glow dot
            el('circle', { cx: pos.x, cy: pos.y, r: 8,
                           fill: 'rgba(155,109,255,0.15)', stroke: '#9b6dff60', 'stroke-width': '0.8' });
            // Planet glyph
            el('text', { x: pos.x, y: pos.y, 'text-anchor': 'middle', 'dominant-baseline': 'middle',
                         'font-size': '10', fill: '#ddd0ff', 'font-family': 'serif' },
               PLANET_GLYPHS_SVG[p.name] || '●');
            // Retrograde marker
            if (p.data.retrograde) {
                el('text', { x: pos.x + 9, y: pos.y - 5, 'font-size': '7', fill: '#ff8080' }, '℞');
            }
        });
    }

    // ── Center circle ────────────────────────────────────────────────────────
    el('circle', { cx, cy, r: R_INNER, fill: '#0b0b18', stroke: '#242438', 'stroke-width': '1.5' });

    // Rising sign glyph
    el('text', { x: cx, y: cy - 10, 'text-anchor': 'middle', 'dominant-baseline': 'middle',
                 'font-size': '28', fill: '#c9b458', 'font-family': 'serif' },
       SIGN_GLYPHS[chart.rising_sign] || '');
    el('text', { x: cx, y: cy + 9, 'text-anchor': 'middle', 'dominant-baseline': 'middle',
                 'font-size': '7.5', fill: '#7777aa', 'letter-spacing': '1' }, 'ASCENDANT');
    el('text', { x: cx, y: cy + 22, 'text-anchor': 'middle', 'dominant-baseline': 'middle',
                 'font-size': '9', fill: '#9090bb' }, chart.rising_sign.toUpperCase());
}

// ─── Rising Sign Spotlight ──────────────────────────────────────────────────

function renderRisingSpotlight(chart) {
    const data = RISING_DATA[chart.rising_sign];
    if (!data) return;

    document.getElementById('risingGlyph').textContent      = SIGN_GLYPHS[chart.rising_sign] || '';
    document.getElementById('risingSignTitle').textContent  = chart.rising_sign;

    const elem     = SIGN_ELEMENTS[chart.rising_sign] || '';
    const modality = SIGN_MODALITIES[chart.rising_sign] || '';
    const deg      = chart.rising_degree != null ? chart.rising_degree.toFixed(2) : '—';
    document.getElementById('risingDegreeLabel').textContent =
        `${deg}° ${chart.rising_sign}  ·  ${elem.charAt(0).toUpperCase() + elem.slice(1)} · ${modality}`;

    document.getElementById('risingIntro').textContent = data.intro;
    document.getElementById('pillar1').textContent     = data.firstImpression;
    document.getElementById('pillar2').textContent     = data.presence;
    document.getElementById('pillar3').textContent     = data.lifeApproach;
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

// --- Ask the Stars ---
const STARS_MAX = 600;

function setupAskStars() {
    const btn      = document.getElementById('askStarsBtn');
    const textarea = document.getElementById('starsQuestion');
    const loading  = document.getElementById('starsLoading');
    const answer   = document.getElementById('starsAnswer');
    const counter  = document.getElementById('starsCounter');
    const token    = getToken();

    if (textarea) {
        textarea.maxLength = STARS_MAX;
        textarea.addEventListener('input', () => {
            const left = STARS_MAX - textarea.value.length;
            if (counter) {
                counter.textContent = `${left} characters left`;
                counter.classList.toggle('counter-warn', left < 80);
            }
        });
    }

    btn?.addEventListener('click', async () => {
        const question = textarea.value.trim();
        if (!question) { textarea?.focus(); return; }

        btn.disabled = true;
        btn.textContent = '✨ Consulting the stars…';
        loading.classList.remove('hidden');
        answer.classList.add('hidden');
        answer.style.color = '';

        try {
            const res = await apiFetch('/api/charts/ask-stars', 'POST', { question }, token);
            answer.innerHTML = formatReading(res.answer);
            answer.classList.remove('hidden');
            // Clear after success so user can ask another question
            textarea.value = '';
            if (counter) counter.textContent = `${STARS_MAX} characters left`;
            // Show usage nudge if approaching free limit
            if (res.free_uses_remaining !== null && res.free_uses_remaining !== undefined) {
                const used = 10 - res.free_uses_remaining;
                if (used >= 5) showFreeTierNudge(res.free_uses_remaining);
            }
        } catch (err) {
            if (err.status === 402) {
                showFreeLimitModal();
            } else {
                answer.textContent = err.message || 'Could not get an answer. Please try again.';
                answer.style.color = '#ff8080';
                answer.classList.remove('hidden');
            }
        } finally {
            btn.disabled = false;
            btn.textContent = 'Ask the Stars ✨';
            loading.classList.add('hidden');
        }
    });
}

function showFreeTierNudge(remaining) {
    let nudge = document.getElementById('freeTierNudge');
    if (!nudge) {
        nudge = document.createElement('p');
        nudge.id = 'freeTierNudge';
        nudge.style.cssText = 'font-size:0.85rem;color:var(--text-muted);margin-top:10px;text-align:center;';
        document.getElementById('starsAnswer')?.after(nudge);
    }
    nudge.innerHTML = `${remaining} free reading${remaining === 1 ? '' : 's'} remaining. <a href="/pricing" style="color:var(--accent)">Upgrade for unlimited access →</a>`;
}

function showFreeLimitModal() {
    let modal = document.getElementById('freeLimitModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'freeLimitModal';
        modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.7);display:flex;align-items:center;justify-content:center;z-index:1000;padding:20px;';
        modal.innerHTML = `
            <div style="background:var(--card-bg,#1a1a2e);border-radius:16px;padding:40px;max-width:420px;width:100%;text-align:center;border:1px solid rgba(255,255,255,0.1);">
                <div style="font-size:2.5rem;margin-bottom:16px;">✨</div>
                <h2 style="margin-bottom:12px;color:var(--text)">You've used all 10 free readings</h2>
                <p style="color:var(--text-muted);margin-bottom:28px;line-height:1.6">Upgrade to Premium for unlimited questions, daily horoscopes, compatibility checks — all for $3.99/month.</p>
                <a href="/pricing" style="display:block;background:var(--accent,#8b5cf6);color:#fff;padding:14px 24px;border-radius:10px;text-decoration:none;font-weight:600;margin-bottom:12px;">See Pricing →</a>
                <button onclick="document.getElementById('freeLimitModal').remove()" style="background:none;border:none;color:var(--text-muted);cursor:pointer;font-size:0.9rem;">Maybe later</button>
            </div>
        `;
        document.body.appendChild(modal);
    }
    modal.style.display = 'flex';
}

// --- Paywall ---
function setupPaywall() {
    const token = getToken();

    document.getElementById('upgradeMonthlyBtn')?.addEventListener('click', async (e) => {
        e.preventDefault();
        await redirectToCheckout('monthly', token);
    });
    document.getElementById('upgradeYearlyBtn')?.addEventListener('click', async (e) => {
        e.preventDefault();
        await redirectToCheckout('yearly', token);
    });
}

async function redirectToCheckout(plan, token) {
    try {
        const res = await apiFetch(`/api/payments/checkout-url?plan=${plan}`, 'GET', null, token);
        window.location.href = res.checkout_url;
    } catch (err) {
        alert('Unable to open checkout. Please try again.');
    }
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
