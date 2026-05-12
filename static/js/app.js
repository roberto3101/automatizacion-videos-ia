// === STATE ===
let currentVideoId = null;
let statusInterval = null;
let batchVideoIds = [];

// === INIT ===
document.addEventListener('DOMContentLoaded', () => {
    loadCharacters();
    loadVideos();
    loadSettings();
    loadVoiceSettings();
    loadXttsVoices();
    loadBenchmark();
    loadDashboard().then(() => loadScheduler());
});

// === TABS ===
function switchTab(tab) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    document.getElementById(`tab-${tab}`).classList.add('active');
    document.querySelector(`[data-tab="${tab}"]`).classList.add('active');
    if (tab === 'characters') loadCharacters();
    if (tab === 'videos') loadVideos();
    if (tab === 'dashboard') loadDashboard();
    if (tab === 'publish') loadPublishTab();
    if (tab === 'produce') loadTemplates();
}

function toggleSidebar() { document.getElementById('sidebar').classList.toggle('open'); }

function toggleBatchMode() {
    const mode = document.getElementById('prod-mode').value;
    document.getElementById('single-topic-group').classList.toggle('hidden', mode === 'batch');
    document.getElementById('batch-topic-group').classList.toggle('hidden', mode === 'single');
}

// === DASHBOARD ===
async function loadDashboard() {
    try {
        const res = await fetch('/api/analytics');
        const data = await res.json();
        const o = data.overview;

        document.getElementById('dash-total').textContent = o.total_videos;
        document.getElementById('dash-done').textContent = o.completed;
        document.getElementById('dash-rate').textContent = o.success_rate + '%';
        document.getElementById('dash-cost').textContent = '$' + o.total_cost_usd.toFixed(2);
        document.getElementById('stat-videos').textContent = o.completed;
        document.getElementById('stat-chars').textContent = data.by_character?.length || 0;
        document.getElementById('stat-cost').textContent = o.total_cost_usd.toFixed(2);

        // Recommendations
        const recEl = document.getElementById('dash-recommendations');
        const recs = data.recommendations || [];
        recEl.innerHTML = recs.length ? recs.map(r =>
            `<div class="rec-item ${r.type}">${r.message}</div>`
        ).join('') : '<div class="rec-item info">All good! Keep producing content consistently.</div>';

        // Recent activity
        const recentEl = document.getElementById('dash-recent');
        const recent = data.recent_videos || [];
        recentEl.innerHTML = recent.length ? recent.map(v =>
            `<div class="rec-item info">
                <span class="badge badge-${v.status}">${v.status}</span>
                <span>${esc(v.title || 'Untitled')} — ${esc(v.character_name)} — ${v.created_at?.slice(0,10) || ''}</span>
            </div>`
        ).join('') : '<p class="empty-state">No activity yet</p>';

        // Autopilot character select
        const chars = data.by_character || [];
        const charRes = await fetch('/api/characters');
        const allChars = await charRes.json();
        const charOptions = allChars.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join('');
        const apSel = document.getElementById('autopilot-character');
        if (apSel) apSel.innerHTML = charOptions;
        const schedSel = document.getElementById('sched-character');
        if (schedSel) schedSel.innerHTML = charOptions;
    } catch (e) { console.error('Dashboard error:', e); }
}

// === CONTEXT STATE ===
let contextImagePaths = [];

function toggleAutopilotContext() {
    document.getElementById('autopilot-context').classList.toggle('hidden');
}

function addContextText() {
    const list = document.getElementById('context-texts-list');
    const idx = list.children.length;
    if (idx >= 5) { toast('Max 5 texts', 'error'); return; }
    const div = document.createElement('div');
    div.className = 'context-text-item';
    div.innerHTML = `<textarea class="input textarea context-text" placeholder="Paste text context here (story, article, idea, notes...)"></textarea><button class="remove-text" onclick="this.parentElement.remove()">✕</button>`;
    list.appendChild(div);
}

async function uploadContextImages(files) {
    if (!files || !files.length) return;
    for (const file of files) {
        if (contextImagePaths.length >= 5) { toast('Max 5 images', 'error'); break; }

        const formData = new FormData();
        formData.append('file', file);

        try {
            const res = await fetch('/api/upload/image', { method: 'POST', body: formData });
            if (!res.ok) { const err = await res.json(); toast(err.detail || 'Upload failed', 'error'); continue; }
            const data = await res.json();

            contextImagePaths.push(data.path);
            const grid = document.getElementById('context-images-list');
            const div = document.createElement('div');
            div.className = 'context-img-item';
            div.dataset.path = data.path;
            div.innerHTML = `<img src="${data.url}" alt="context"><button class="remove-img" onclick="removeContextImage(this)">✕</button>`;
            grid.appendChild(div);
            toast(`Uploaded: ${data.filename} (${data.size_mb}MB)`, 'success');
        } catch (e) { toast('Upload error: ' + e.message, 'error'); }
    }
    document.getElementById('context-image-input').value = '';
}

function removeContextImage(btn) {
    const item = btn.closest('.context-img-item');
    const path = item.dataset.path;
    contextImagePaths = contextImagePaths.filter(p => p !== path);
    item.remove();
}

// Drag & drop on upload area
document.addEventListener('DOMContentLoaded', () => {
    const area = document.getElementById('upload-area');
    if (area) {
        area.addEventListener('dragover', e => { e.preventDefault(); area.classList.add('dragover'); });
        area.addEventListener('dragleave', () => area.classList.remove('dragover'));
        area.addEventListener('drop', e => { e.preventDefault(); area.classList.remove('dragover'); uploadContextImages(e.dataTransfer.files); });
    }
});

// === AUTOPILOT ===
async function runAutopilot() {
    const charId = document.getElementById('autopilot-character').value;
    if (!charId) { toast('Select a character', 'error'); return; }

    // Collect context
    const contextTexts = [];
    document.querySelectorAll('.context-text').forEach(t => { if (t.value.trim()) contextTexts.push(t.value.trim()); });
    const topic = document.getElementById('autopilot-topic')?.value?.trim() || '';
    const language = document.getElementById('autopilot-language')?.value || 'en';

    const btn = document.getElementById('btn-autopilot');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Running...';
    document.getElementById('autopilot-status').classList.remove('hidden');

    try {
        const res = await fetch('/api/autopilot/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                character_id: parseInt(charId),
                context_texts: contextTexts,
                context_image_paths: contextImagePaths,
                topic: topic,
                language: language,
            }),
        });
        const data = await res.json();

        const statusEl = document.getElementById('autopilot-status');
        if (data.status === 'topic_ready') {
            const hasScript = !!data.script;
            if (hasScript && data.video_id) {
                statusEl.innerHTML = `<div class="log-entry"><span class="log-step">[autopilot]</span> <span class="log-detail">Found: "${esc(data.topic)}" — Script generated, producing...</span></div>`;
                await fetch(`/api/videos/${data.video_id}/produce`, { method: 'POST' });
                notify(`Autopilot producing: "${data.topic}"`);
                toast('Autopilot: Production started!', 'success');
            } else {
                statusEl.innerHTML = `<div class="log-entry"><span class="log-step">[autopilot]</span> <span class="log-detail">Found: "${esc(data.topic)}" — ${esc(data.message || 'No API key for scripts. Paste a script manually for this topic.')}</span></div>`;
                notify(`Topic found: "${data.topic}" — needs script`);
                toast('Topic saved! Paste a script manually to produce.', 'info');
            }
        } else if (data.status === 'no_trends') {
            statusEl.innerHTML = '<div class="log-entry"><span class="log-step">[autopilot]</span> <span class="log-detail">No new trends found. Try again later.</span></div>';
        } else {
            statusEl.innerHTML = `<div class="log-entry"><span class="log-step">[autopilot]</span> <span class="log-detail">${esc(data.error || data.status)}</span></div>`;
        }
    } catch (e) {
        toast('Autopilot error: ' + e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = '🚀 Run Autopilot Cycle';
    }
}

// === CHARACTERS ===
async function loadCharacters() {
    try {
        const res = await fetch('/api/characters');
        const chars = await res.json();
        renderCharactersList(chars);
        renderCharacterSelect(chars);
    } catch (e) { console.error(e); }
}

function renderCharactersList(chars) {
    const c = document.getElementById('characters-list');
    if (!chars.length) { c.innerHTML = '<p class="empty-state">No characters. Create one!</p>'; return; }
    c.innerHTML = chars.map(ch => `
        <div class="character-card">
            <h4>${esc(ch.name)}</h4>
            <p>${esc((ch.description || '').substring(0, 80))}${(ch.description || '').length > 80 ? '...' : ''}</p>
            <div style="font-size:11px;color:var(--text-muted);margin-bottom:6px">🗣 ${esc(ch.voice_id)} · ${ch.language === 'en' ? '🇺🇸' : '🇪🇸'}</div>
            <div class="card-actions">
                <button class="btn btn-secondary btn-small" onclick="editCharacter(${ch.id})">Edit</button>
                <button class="btn btn-danger btn-small" onclick="deleteCharacter(${ch.id},'${esc(ch.name)}')">Delete</button>
            </div>
        </div>
    `).join('');
}

function renderCharacterSelect(chars) {
    const s = document.getElementById('prod-character');
    s.innerHTML = chars.length ? chars.map(c => `<option value="${c.id}">${esc(c.name)} (${c.language === 'en' ? 'EN' : 'ES'})</option>`).join('') : '<option value="">Create a character first</option>';
}

function showCharacterForm(d = null) {
    document.getElementById('character-form').classList.remove('hidden');
    document.getElementById('char-form-title').textContent = d ? 'Edit Character' : 'New Character';
    document.getElementById('char-edit-id').value = d ? d.id : '';
    document.getElementById('char-name').value = d ? d.name : '';
    document.getElementById('char-description').value = d ? (d.description || '') : '';
    document.getElementById('char-personality').value = d ? (d.personality || '') : '';
    document.getElementById('char-voice').value = d ? (d.voice_id || 'en-US-GuyNeural') : 'en-US-GuyNeural';
    document.getElementById('char-language').value = d ? (d.language || 'en') : 'en';
    document.getElementById('char-visual').value = d ? (d.visual_prompt || '') : '';
    const hooks = d?.sample_hooks ? (Array.isArray(d.sample_hooks) ? d.sample_hooks : []) : [];
    document.getElementById('char-hooks').value = hooks.join('\n');
}

function hideCharacterForm() { document.getElementById('character-form').classList.add('hidden'); }

async function saveCharacter() {
    const editId = document.getElementById('char-edit-id').value;
    const hooks = document.getElementById('char-hooks').value.split('\n').map(h => h.trim()).filter(h => h);
    const data = {
        name: document.getElementById('char-name').value,
        description: document.getElementById('char-description').value,
        personality: document.getElementById('char-personality').value,
        voice_id: document.getElementById('char-voice').value,
        language: document.getElementById('char-language').value,
        visual_prompt: document.getElementById('char-visual').value,
        sample_hooks: hooks,
    };
    if (!data.name) { toast('Name required', 'error'); return; }
    try {
        const url = editId ? `/api/characters/${editId}` : '/api/characters';
        const res = await fetch(url, { method: editId ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
        if (!res.ok) throw new Error(await res.text());
        toast(editId ? 'Updated' : 'Created', 'success');
        hideCharacterForm(); loadCharacters(); loadDashboard();
    } catch (e) { toast(e.message, 'error'); }
}

async function editCharacter(id) { const res = await fetch('/api/characters'); const chars = await res.json(); const c = chars.find(x => x.id === id); if (c) showCharacterForm(c); }
async function deleteCharacter(id, name) { if (!confirm(`Delete "${name}"?`)) return; await fetch(`/api/characters/${id}`, { method: 'DELETE' }); toast('Deleted', 'success'); loadCharacters(); }

// === TRENDS ===
async function loadTrends() {
    const container = document.getElementById('trends-content');
    const btn = document.getElementById('btn-trends');
    btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Scanning...';
    container.innerHTML = '<p class="empty-state"><span class="spinner"></span> Scanning 5 sources...</p>';
    try {
        const res = await fetch('/api/trends?niche=horror');
        const data = await res.json();
        let html = `<p style="font-size:11px;color:var(--text-muted);margin-bottom:12px">${data.total_ideas||0} ideas found</p>`;

        const reddit = (data.reddit || []).filter(t => !t.error);
        if (reddit.length) {
            html += '<h3>🟠 Reddit — Viral Horror Stories</h3><div class="trends-list">';
            html += reddit.map(t => `<div class="trend-row ${t.video_potential === 'high' ? 'trend-hot' : t.video_potential === 'medium' ? 'trend-warm' : ''}" onclick="useTrend('${esc(t.title)}')">
                <div class="trend-title">${esc(t.title)}</div>
                <div class="trend-meta"><span class="trend-score">⬆${t.score.toLocaleString()}</span> <span>💬${t.comments}</span> <span>📊${(t.ratio*100).toFixed(0)}%</span> <span class="trend-sub">r/${esc(t.subreddit)}</span> <span>⏱${t.duration_hint}</span> ${t.video_potential === 'high' ? '<span class="badge-hot">🔥HIGH</span>' : ''}</div>
            </div>`).join('');
            html += '</div>';
        }

        const yt = (data.youtube || []).filter(t => !t.error);
        if (yt.length) {
            html += '<h3>📺 YouTube — Viral Horror</h3><div class="trends-list">';
            html += yt.map(t => `<div class="trend-row" onclick="useTrend('${esc(t.title)}')">
                <div class="trend-title">${esc(t.title)}</div>
                <div class="trend-meta"><span>👁${t.views ? t.views.toLocaleString() : t.views_text || ''}</span> ${t.channel ? `<span>📺${esc(t.channel)}</span>` : ''}</div>
            </div>`).join('');
            html += '</div>';
        }

        const gt = (data.google_trends || []).filter(t => !t.error);
        if (gt.length) { html += '<h3>🔍 Google — Rising Searches</h3><div class="trends-grid">'; html += gt.map(t => `<div class="trend-item" onclick="useTrend('${esc(t.title)}')">${esc(t.title)}</div>`).join(''); html += '</div>'; }

        const cp = (data.creepypasta || []).filter(t => !t.error);
        if (cp.length) { html += '<h3>👻 Creepypasta</h3><div class="trends-grid">'; html += cp.map(t => `<div class="trend-item" onclick="useTrend('${esc(t.title)}')">${esc(t.title)}</div>`).join(''); html += '</div>'; }

        const chan = (data.chan_x || []).filter(t => !t.error);
        if (chan.length) { html += '<h3>🔮 4chan /x/</h3><div class="trends-list">'; html += chan.map(t => `<div class="trend-row" onclick="useTrend('${esc(t.title)}')"><div class="trend-title">${esc(t.title)}</div><div class="trend-meta"><span>💬${t.replies} replies</span></div></div>`).join(''); html += '</div>'; }

        container.innerHTML = html || '<p class="empty-state">No trends found.</p>';
    } catch (e) { container.innerHTML = `<p class="empty-state">Error: ${e.message}</p>`; }
    finally { btn.disabled = false; btn.innerHTML = 'Scan Now'; }
}

function useTrend(title) { switchTab('produce'); document.getElementById('prod-topic').value = title; toast('Topic set!', 'info'); }

// === SCRIPT GENERATION ===
async function generateScript() {
    const mode = document.getElementById('prod-mode').value;
    if (mode === 'batch') { await generateBatch(); return; }
    const charId = document.getElementById('prod-character').value;
    const topic = document.getElementById('prod-topic').value;
    const duration = document.getElementById('prod-duration').value;
    const language = document.getElementById('prod-language').value;
    if (!charId) { toast('Select character', 'error'); return; }
    if (!topic) { toast('Enter a topic', 'error'); return; }
    const btn = document.getElementById('btn-generate-script');
    btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Generating...';
    try {
        const res = await fetch('/api/videos/generate-script', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ character_id: parseInt(charId), topic, duration: parseInt(duration), language }) });
        if (!res.ok) { const err = await res.json(); throw new Error(err.detail); }
        const data = await res.json();
        currentVideoId = data.video_id;
        renderScriptPreview(data.script);
        document.getElementById('script-preview').classList.remove('hidden');
        document.getElementById('batch-results').classList.add('hidden');
        document.getElementById('production-status').classList.add('hidden');
        toast('Script generated!', 'success');
    } catch (e) { toast(e.message, 'error'); }
    finally { btn.disabled = false; btn.innerHTML = '📝 Generate Script (API)'; }
}

async function generateBatch() {
    const charId = document.getElementById('prod-character').value;
    const topics = document.getElementById('prod-topics-batch').value.split('\n').map(t => t.trim()).filter(t => t);
    const duration = document.getElementById('prod-duration').value;
    const language = document.getElementById('prod-language').value;
    if (!charId || !topics.length) { toast('Need character and topics', 'error'); return; }
    const btn = document.getElementById('btn-generate-script');
    btn.disabled = true; btn.innerHTML = `<span class="spinner"></span> ${topics.length} scripts...`;
    try {
        const res = await fetch('/api/videos/batch', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ character_id: parseInt(charId), topics, duration: parseInt(duration), language }) });
        const data = await res.json();
        batchVideoIds = data.batch.filter(b => b.video_id).map(b => b.video_id);
        document.getElementById('batch-list').innerHTML = data.batch.map(b => `<div class="scene-card"><div class="scene-num">${b.status === 'error' ? '❌' : '✅'} ${esc(b.topic)}</div></div>`).join('');
        document.getElementById('script-preview').classList.add('hidden');
        document.getElementById('batch-results').classList.remove('hidden');
        toast(`${batchVideoIds.length} scripts ready!`, 'success');
    } catch (e) { toast(e.message, 'error'); }
    finally { btn.disabled = false; btn.innerHTML = '📝 Generate Script (API)'; }
}

async function produceBatch() {
    for (const vid of batchVideoIds) { try { await fetch(`/api/videos/${vid}/produce`, { method: 'POST' }); } catch (e) {} }
    toast(`${batchVideoIds.length} videos queued!`, 'success');
    switchTab('videos');
}

// === MANUAL SCRIPT ===
function showManualScript() { document.getElementById('manual-script-input').classList.remove('hidden'); }
function hideManualScript() { document.getElementById('manual-script-input').classList.add('hidden'); }

async function loadManualScript() {
    const charId = document.getElementById('prod-character').value;
    const language = document.getElementById('prod-language').value;
    const duration = document.getElementById('prod-duration').value;
    const jsonText = document.getElementById('manual-script-json').value.trim();
    if (!charId) { toast('Select character', 'error'); return; }
    if (!jsonText) { toast('Paste JSON', 'error'); return; }
    let script;
    try { script = JSON.parse(jsonText); } catch (e) { toast('Invalid JSON', 'error'); return; }
    if (!script.scenes?.length) { toast('Need "scenes" array', 'error'); return; }
    try {
        const res = await fetch('/api/videos/manual-script', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ script, character_id: parseInt(charId), language, duration: parseInt(duration) }) });
        if (!res.ok) { const err = await res.json(); throw new Error(err.detail); }
        const data = await res.json();
        currentVideoId = data.video_id;
        renderScriptPreview(data.script);
        document.getElementById('script-preview').classList.remove('hidden');
        document.getElementById('manual-script-input').classList.add('hidden');
        document.getElementById('production-status').classList.add('hidden');
        toast('Script loaded!', 'success');
    } catch (e) { toast(e.message, 'error'); }
}

// === SCRIPT PREVIEW (inline editable, draggable) ===
function renderScriptPreview(script) {
    document.getElementById('script-title').value = script.title || '';
    document.getElementById('script-scenes-count').textContent = `${script.scenes.length} scenes`;
    const c = document.getElementById('script-scenes');
    c.innerHTML = script.scenes.map(s => `
        <div class="scene-card" data-scene="${s.scene_number}" draggable="true" ondragstart="dragStart(event)" ondragover="dragOver(event)" ondrop="drop(event)">
            <span class="drag-handle">⋮⋮</span>
            <button class="edit-btn" onclick="toggleSceneEdit(this)">✏️</button>
            <div class="scene-num">Scene ${s.scene_number} · ${s.duration_seconds}s</div>
            <div class="scene-narration">${esc(s.narration)}</div>
            <div class="scene-visual">🎬 ${esc(s.visual_prompt)}</div>
            <div class="scene-edit">
                <label style="font-size:11px;color:var(--text-muted)">Narration:</label>
                <textarea class="edit-narration">${esc(s.narration)}</textarea>
                <label style="font-size:11px;color:var(--text-muted);margin-top:6px">Visual:</label>
                <textarea class="edit-visual">${esc(s.visual_prompt)}</textarea>
                <button class="btn btn-small btn-primary" style="margin-top:6px" onclick="saveSceneEdit(this)">Save</button>
            </div>
        </div>
    `).join('');
}

function toggleSceneEdit(btn) {
    const card = btn.closest('.scene-card');
    const editDiv = card.querySelector('.scene-edit');
    editDiv.style.display = editDiv.style.display === 'block' ? 'none' : 'block';
}

function saveSceneEdit(btn) {
    const card = btn.closest('.scene-card');
    const narration = card.querySelector('.edit-narration').value;
    const visual = card.querySelector('.edit-visual').value;
    card.querySelector('.scene-narration').textContent = narration;
    card.querySelector('.scene-visual').textContent = '🎬 ' + visual;
    card.querySelector('.scene-edit').style.display = 'none';
    toast('Scene updated', 'success');
}

// Drag & Drop
let draggedEl = null;
function dragStart(e) { draggedEl = e.target.closest('.scene-card'); draggedEl.classList.add('dragging'); }
function dragOver(e) { e.preventDefault(); }
function drop(e) {
    e.preventDefault();
    const target = e.target.closest('.scene-card');
    if (target && draggedEl && target !== draggedEl) {
        const container = document.getElementById('script-scenes');
        const children = [...container.children];
        const dragIdx = children.indexOf(draggedEl);
        const dropIdx = children.indexOf(target);
        if (dragIdx < dropIdx) target.after(draggedEl);
        else target.before(draggedEl);
        // Renumber
        container.querySelectorAll('.scene-card').forEach((card, i) => {
            card.dataset.scene = i + 1;
            card.querySelector('.scene-num').textContent = `Scene ${i + 1}`;
        });
    }
    if (draggedEl) draggedEl.classList.remove('dragging');
}

// === PRODUCTION ===
async function startProduction() {
    if (!currentVideoId) { toast('Generate script first', 'error'); return; }
    const title = document.getElementById('script-title').value;
    const scenes = [];
    document.querySelectorAll('#script-scenes .scene-card').forEach((card, i) => {
        scenes.push({
            scene_number: i + 1,
            narration: card.querySelector('.scene-narration').textContent,
            visual_prompt: card.querySelector('.scene-visual').textContent.replace('🎬 ', ''),
            duration_seconds: 10
        });
    });
    try {
        await fetch(`/api/videos/${currentVideoId}/update-script`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ script: { title, scenes } }) });
        const btn = document.getElementById('btn-produce');
        btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> Starting...';
        const res = await fetch(`/api/videos/${currentVideoId}/produce`, { method: 'POST' });
        if (!res.ok) { const err = await res.json(); throw new Error(err.detail); }
        document.getElementById('production-status').classList.remove('hidden');
        document.getElementById('production-result').classList.add('hidden');
        resetProgressSteps();
        toast('Production started!', 'info');
        startStatusPolling(currentVideoId);
    } catch (e) {
        toast(e.message, 'error');
        const btn = document.getElementById('btn-produce');
        btn.disabled = false; btn.innerHTML = '🚀 Start Production';
    }
}

function resetProgressSteps() {
    document.querySelectorAll('.step-item').forEach(s => { s.className = 'step-item'; s.querySelector('.step-icon').textContent = '⏳'; });
    document.getElementById('progress-fill').style.width = '0%';
    document.getElementById('progress-pct').textContent = '0%';
}

function startStatusPolling(videoId) {
    if (statusInterval) clearInterval(statusInterval);
    const pMap = { voice: 15, music: 30, video: 55, subtitles: 70, assembly: 88, thumbnail: 95 };

    statusInterval = setInterval(async () => {
        try {
            const res = await fetch(`/api/videos/${videoId}/status`);
            const data = await res.json();

            // Update logs
            const logsEl = document.getElementById('production-logs');
            if (logsEl) {
                logsEl.innerHTML = data.logs.map(l => `<div class="log-entry"><span class="log-step">[${l.step}]</span> <span class="log-detail">${esc(l.detail || '')}</span> ${l.cost_usd > 0 ? `<span class="log-cost">$${parseFloat(l.cost_usd).toFixed(4)}</span>` : ''}</div>`).join('');
            }

            // Update progress steps
            let maxP = 0;
            data.logs.forEach(l => {
                const stepEl = document.querySelector(`.step-item[data-step="${l.step}"]`);
                if (stepEl) {
                    if (l.status === 'done') { stepEl.className = 'step-item done'; stepEl.querySelector('.step-icon').textContent = '✅'; }
                    else if (l.status === 'running') { stepEl.className = 'step-item active'; stepEl.querySelector('.step-icon').textContent = '⏳'; }
                    else if (l.status === 'failed') { stepEl.className = 'step-item failed'; stepEl.querySelector('.step-icon').textContent = '❌'; }
                }
                if (l.status === 'done' && pMap[l.step]) maxP = Math.max(maxP, pMap[l.step]);
            });

            // Cost
            const costEl = document.getElementById('production-cost');
            if (costEl && data.total_cost_usd > 0) costEl.textContent = `Cost: $${data.total_cost_usd.toFixed(4)}`;

            if (data.status === 'done') {
                maxP = 100;
                clearInterval(statusInterval);
                document.getElementById('production-result').classList.remove('hidden');
                document.getElementById('result-video').src = `/api/videos/${videoId}/download`;
                document.getElementById('result-download').href = `/api/videos/${videoId}/download`;
                const btn = document.getElementById('btn-produce');
                if (btn) { btn.disabled = false; btn.innerHTML = '🚀 Start Production'; }
                notify('Video production complete!');
                loadVideos(); loadDashboard();
            } else if (data.status === 'error') {
                clearInterval(statusInterval);
                const btn = document.getElementById('btn-produce');
                if (btn) { btn.disabled = false; btn.innerHTML = '🚀 Start Production'; }
                notify('Production failed. Check logs.');
            }

            document.getElementById('progress-fill').style.width = maxP + '%';
            document.getElementById('progress-pct').textContent = maxP + '%';
        } catch (e) { console.error(e); }
    }, 2500);
}

// === VIDEOS LIST (with thumbnails) ===
async function loadVideos() {
    try {
        const res = await fetch('/api/videos');
        const videos = await res.json();
        const c = document.getElementById('videos-list');
        const noV = document.getElementById('no-videos');
        if (!videos.length) { c.innerHTML = ''; noV.classList.remove('hidden'); return; }
        noV.classList.add('hidden');
        c.innerHTML = videos.map(v => `
            <div class="video-card-full">
                ${v.status === 'done' ? `<video class="video-thumb" src="/api/videos/${v.id}/download" muted preload="metadata"></video>` : `<div class="video-thumb" style="display:flex;align-items:center;justify-content:center;color:var(--text-muted);font-size:12px">${v.status}</div>`}
                <div class="video-card-body">
                    <h4>${esc(v.title || 'Untitled')}</h4>
                    <div class="video-meta">👤 ${esc(v.character_name)} · ${v.language === 'en' ? '🇺🇸' : '🇪🇸'} · ${v.created_at?.slice(0,10) || ''}</div>
                    <span class="badge badge-${v.status}">${v.status}</span>
                    <div class="card-actions" style="margin-top:8px">
                        ${v.status === 'done' ? `<a class="btn btn-primary btn-small" href="/api/videos/${v.id}/download" download>⬇️</a> <button class="btn btn-secondary btn-small" onclick="scheduleVideoPublish(${v.id})">📤</button>` : ''}
                        ${v.status === 'draft' ? `<button class="btn btn-primary btn-small" onclick="produceFromList(${v.id})">🚀</button>` : ''}
                        ${v.status === 'error' ? `<button class="btn btn-secondary btn-small" onclick="produceFromList(${v.id})">🔄</button>` : ''}
                        <button class="btn btn-danger btn-small" onclick="deleteVideo(${v.id})">🗑</button>
                    </div>
                </div>
            </div>
        `).join('');
    } catch (e) { console.error(e); }
}

async function produceFromList(id) { await fetch(`/api/videos/${id}/produce`, { method: 'POST' }); toast('Started!', 'info'); loadVideos(); }
async function deleteVideo(id) { if (!confirm('Delete?')) return; await fetch(`/api/videos/${id}`, { method: 'DELETE' }); toast('Deleted', 'success'); loadVideos(); loadDashboard(); }

// === PUBLISH ===
async function loadPublishTab() {
    // Check YouTube auth status
    try {
        const res = await fetch('/api/publish/youtube-status');
        const data = await res.json();
        const badge = document.getElementById('yt-auth-badge');
        const steps = document.getElementById('yt-setup-steps');
        const actions = document.getElementById('yt-auth-actions');

        if (data.authenticated) {
            badge.textContent = '✅ Connected';
            badge.className = 'badge badge-done';
            steps.innerHTML = '<p style="color:var(--success);font-size:13px">YouTube auto-upload is ready!</p>';
            actions.innerHTML = '';
        } else if (data.configured) {
            badge.textContent = '⚠️ Not Authenticated';
            badge.className = 'badge badge-generating';
            steps.innerHTML = '<p style="font-size:13px;color:var(--warning)">OAuth credentials found but not authenticated yet.</p>';
            actions.innerHTML = '<button class="btn btn-primary" onclick="authYouTube()">🔑 Authenticate YouTube</button>';
        } else {
            badge.textContent = '❌ Not Set Up';
            badge.className = 'badge badge-error';
            steps.innerHTML = '<div style="font-size:12px;color:var(--text-muted)">' +
                data.setup_steps.map(s => `<p>${esc(s)}</p>`).join('') + '</div>';
            actions.innerHTML = '';
        }
    } catch (e) { console.error(e); }

    // Load video select
    try {
        const res = await fetch('/api/videos');
        const videos = await res.json();
        const sel = document.getElementById('publish-video-select');
        const done = videos.filter(v => v.status === 'done');
        sel.innerHTML = done.length
            ? done.map(v => `<option value="${v.id}">${esc(v.title || 'Untitled')} (ID:${v.id})</option>`).join('')
            : '<option value="">No videos ready</option>';
    } catch (e) {}
}

async function authYouTube() {
    toast('Opening YouTube auth...', 'info');
    try {
        const res = await fetch('/api/publish/youtube-auth', { method: 'POST' });
        const data = await res.json();
        if (data.status === 'ok') {
            toast('YouTube connected!', 'success');
            loadPublishTab();
        } else {
            toast(data.message, 'error');
        }
    } catch (e) { toast('Auth error: ' + e.message, 'error'); }
}

function _getPublishParams() {
    const videoId = document.getElementById('publish-video-select').value;
    if (!videoId) { toast('Select a video first', 'error'); return null; }
    const title = document.getElementById('publish-title').value.trim();
    const tags = document.getElementById('publish-tags').value.split(',').map(t => t.trim()).filter(t => t);
    const privacy = document.getElementById('publish-privacy').value;
    return { videoId, title, tags, privacy };
}

function _showPublishResult(platform, data) {
    const container = document.getElementById('publish-results');
    const content = document.getElementById('publish-results-content');
    container.classList.remove('hidden');

    const icons = { youtube: '📺', tiktok: '🎵', instagram: '📸' };
    let html = `<div class="card" style="margin-bottom:8px">
        <h4>${icons[platform] || '📤'} ${platform}</h4>`;

    if (data.status === 'uploaded') {
        html += `<p style="color:var(--success)">✅ Uploaded! <a href="${data.url}" target="_blank">${data.url}</a></p>`;
    } else if (data.status === 'ready') {
        html += `<p style="color:var(--success)">✅ Export ready (${data.size_mb}MB)</p>`;
        html += `<p style="font-size:12px;color:var(--text-muted);margin:6px 0">${esc(data.caption?.substring(0, 150))}...</p>`;
        html += `<a class="btn btn-primary btn-small" href="${data.video_url}" download>⬇️ Download Video</a>`;
        if (data.instructions) {
            html += '<ol style="font-size:12px;color:var(--text-muted);margin-top:8px">';
            data.instructions.forEach(s => html += `<li>${esc(s)}</li>`);
            html += '</ol>';
        }
    } else {
        html += `<p style="color:var(--warning)">⚠️ ${esc(data.message || data.status)}</p>`;
    }
    html += '</div>';
    content.innerHTML += html;
}

async function publishAll() {
    const p = _getPublishParams();
    if (!p) return;
    document.getElementById('publish-results-content').innerHTML = '';

    toast('Publishing to all platforms...', 'info');
    try {
        const res = await fetch(`/api/publish/all/${p.videoId}`, { method: 'POST' });
        const data = await res.json();
        if (data.youtube) _showPublishResult('YouTube', data.youtube);
        if (data.tiktok) _showPublishResult('TikTok', data.tiktok);
        if (data.instagram) _showPublishResult('Instagram', data.instagram);
        toast('Done!', 'success');
    } catch (e) { toast(e.message, 'error'); }
}

async function publishYouTubeOnly() {
    const p = _getPublishParams();
    if (!p) return;
    document.getElementById('publish-results-content').innerHTML = '';
    toast('Uploading to YouTube...', 'info');
    try {
        const res = await fetch(`/api/publish/youtube/${p.videoId}`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: p.title || undefined, tags: p.tags, privacy: p.privacy }),
        });
        _showPublishResult('YouTube', await res.json());
    } catch (e) { toast(e.message, 'error'); }
}

async function exportTikTok() {
    const p = _getPublishParams();
    if (!p) return;
    document.getElementById('publish-results-content').innerHTML = '';
    toast('Preparing TikTok export...', 'info');
    try {
        const res = await fetch(`/api/publish/tiktok/${p.videoId}`, { method: 'POST' });
        _showPublishResult('TikTok', await res.json());
    } catch (e) { toast(e.message, 'error'); }
}

async function exportInstagram() {
    const p = _getPublishParams();
    if (!p) return;
    document.getElementById('publish-results-content').innerHTML = '';
    toast('Preparing Instagram export...', 'info');
    try {
        const res = await fetch(`/api/publish/instagram/${p.videoId}`, { method: 'POST' });
        _showPublishResult('Instagram', await res.json());
    } catch (e) { toast(e.message, 'error'); }
}

function scheduleVideoPublish(videoId) {
    document.getElementById('publish-video-select').value = videoId;
    switchTab('publish');
}

// === SETTINGS ===
async function loadSettings() {
    try {
        const res = await fetch('/api/settings');
        const s = await res.json();
        if (s.anthropic_api_key) { document.getElementById('set-anthropic-key').placeholder = s.anthropic_api_key; document.getElementById('anthropic-status').classList.add('active'); }
        if (s.fal_api_key) { document.getElementById('set-fal-key').placeholder = s.fal_api_key; document.getElementById('fal-status').classList.add('active'); }
        if (s.youtube_api_key) { document.getElementById('set-youtube-key').placeholder = s.youtube_api_key; document.getElementById('youtube-status').classList.add('active'); }
        if (s.fish_api_key) { document.getElementById('set-fish-key').placeholder = s.fish_api_key; document.getElementById('fish-status').classList.add('active'); }
        if (s.fish_model_id) { document.getElementById('set-fish-model').value = s.fish_model_id; }
    } catch (e) {}
}

async function saveSettings() {
    const data = {};
    const ak = document.getElementById('set-anthropic-key').value;
    const fk = document.getElementById('set-fal-key').value;
    const yk = document.getElementById('set-youtube-key').value;
    const fishk = document.getElementById('set-fish-key').value;
    const fishm = document.getElementById('set-fish-model').value;
    if (ak) data.anthropic_api_key = ak;
    if (fk) data.fal_api_key = fk;
    if (yk) data.youtube_api_key = yk;
    if (fishk) data.fish_api_key = fishk;
    if (fishm !== undefined) data.fish_model_id = fishm;
    if (!Object.keys(data).length) { toast('No changes', 'info'); return; }
    try {
        await fetch('/api/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
        toast('Saved', 'success'); loadSettings(); loadBenchmark();
        document.getElementById('set-anthropic-key').value = '';
        document.getElementById('set-fal-key').value = '';
        document.getElementById('set-youtube-key').value = '';
        document.getElementById('set-fish-key').value = '';
    } catch (e) { toast('Error', 'error'); }
}

// === SCRIPT TEMPLATES ===
async function loadTemplates() {
    try {
        const res = await fetch('/api/templates');
        const templates = await res.json();
        const c = document.getElementById('templates-list');
        if (!templates.length) { c.innerHTML = '<p class="empty-state" style="padding:12px">No saved scripts yet.</p>'; return; }
        c.innerHTML = templates.map(t => {
            const script = t.script_json || {};
            const sceneCount = script.scenes ? script.scenes.length : 0;
            return `<div class="trend-row" style="cursor:default">
                <div class="trend-title">${esc(t.name)} ${t.tags ? `<span style="color:var(--text-muted);font-size:10px">${esc(t.tags)}</span>` : ''}</div>
                <div class="trend-meta">
                    <span>${sceneCount} scenes</span>
                    <span>📊 Used ${t.use_count}x</span>
                    ${t.character_name ? `<span>👤 ${esc(t.character_name)}</span>` : ''}
                    <span>📅 ${t.created_at?.slice(0,10) || ''}</span>
                </div>
                <div class="card-actions" style="margin-top:6px">
                    <button class="btn btn-primary btn-small" onclick="useTemplate(${t.id})">📋 Use</button>
                    <button class="btn btn-secondary btn-small" onclick="copyTemplate(${t.id})">📄 Copy JSON</button>
                    <button class="btn btn-danger btn-small" onclick="deleteTemplate(${t.id})">🗑</button>
                </div>
            </div>`;
        }).join('');
    } catch (e) { console.error(e); }
}

async function saveAsTemplate() {
    const jsonText = document.getElementById('manual-script-json').value.trim();
    if (!jsonText) { toast('Paste a script first', 'error'); return; }
    let script;
    try { script = JSON.parse(jsonText); } catch (e) { toast('Invalid JSON', 'error'); return; }

    const name = prompt('Name for this template:', script.title || 'My Script');
    if (!name) return;
    const tags = prompt('Tags (optional, comma separated):', 'horror');
    const charId = document.getElementById('prod-character').value;

    try {
        await fetch('/api/templates', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, script, character_id: charId ? parseInt(charId) : null, language: document.getElementById('prod-language').value, tags: tags || '' }),
        });
        toast('Template saved!', 'success');
        loadTemplates();
    } catch (e) { toast('Error saving', 'error'); }
}

async function useTemplate(id) {
    try {
        const res = await fetch(`/api/templates/${id}/use`, { method: 'POST' });
        const template = await res.json();
        const script = template.script_json;
        document.getElementById('manual-script-json').value = JSON.stringify(script, null, 2);
        document.getElementById('manual-script-input').classList.remove('hidden');
        toast('Template loaded — click "Load Script" to use it', 'info');
        loadTemplates();
    } catch (e) { toast('Error loading template', 'error'); }
}

async function copyTemplate(id) {
    try {
        const res = await fetch(`/api/templates/${id}/use`, { method: 'POST' });
        const template = await res.json();
        const json = JSON.stringify(template.script_json, null, 2);
        await navigator.clipboard.writeText(json);
        toast('JSON copied to clipboard!', 'success');
        loadTemplates();
    } catch (e) { toast('Error copying', 'error'); }
}

async function deleteTemplate(id) {
    if (!confirm('Delete this template?')) return;
    await fetch(`/api/templates/${id}`, { method: 'DELETE' });
    toast('Deleted', 'success');
    loadTemplates();
}

// === SCHEDULER ===
async function loadScheduler() {
    try {
        // Ensure character select is populated
        const schedChar = document.getElementById('sched-character');
        if (schedChar && schedChar.options.length === 0) {
            const charRes = await fetch('/api/characters');
            const allChars = await charRes.json();
            schedChar.innerHTML = allChars.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join('');
        }

        const res = await fetch('/api/scheduler');
        const config = await res.json();
        const modeEl = document.getElementById('sched-mode');
        const timesEl = document.getElementById('sched-times');
        const intervalEl = document.getElementById('sched-interval');
        const maxEl = document.getElementById('sched-max');
        const publishEl = document.getElementById('sched-publish');
        if (modeEl) modeEl.value = config.mode || 'daily';
        if (timesEl) timesEl.value = (config.daily_times || ['08:00']).join(', ');
        if (intervalEl) intervalEl.value = config.interval_hours || 12;
        if (maxEl) maxEl.value = config.max_videos_per_day || 2;
        if (publishEl) publishEl.value = config.auto_publish_youtube ? 'true' : 'false';
        if (schedChar && config.character_id) schedChar.value = config.character_id;
        const startBtn = document.getElementById('btn-sched-start');
        const stopBtn = document.getElementById('btn-sched-stop');
        const statusEl = document.getElementById('sched-status');
        if (config.enabled) {
            if (startBtn) startBtn.style.display = 'none';
            if (stopBtn) stopBtn.style.display = '';
            if (statusEl) statusEl.innerHTML = '🟢 Scheduler is <b>RUNNING</b>. Produced today: ' + (config.videos_produced_today || 0);
        } else {
            if (startBtn) startBtn.style.display = '';
            if (stopBtn) stopBtn.style.display = 'none';
            if (statusEl) statusEl.innerHTML = '⏸ Scheduler is <b>stopped</b>';
        }
    } catch (e) { console.error('loadScheduler:', e); }
}

async function startScheduler() {
    const config = {
        mode: document.getElementById('sched-mode').value,
        daily_times: document.getElementById('sched-times').value.split(',').map(t => t.trim()),
        interval_hours: parseInt(document.getElementById('sched-interval').value),
        max_videos_per_day: parseInt(document.getElementById('sched-max').value),
        auto_publish_youtube: document.getElementById('sched-publish').value === 'true',
        character_id: parseInt(document.getElementById('sched-character')?.value || '1'),
    };
    await fetch('/api/scheduler', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(config) });
    await fetch('/api/scheduler/start', { method: 'POST' });
    toast('Scheduler started!', 'success');
    loadScheduler();
}

async function stopScheduler() {
    await fetch('/api/scheduler/stop', { method: 'POST' });
    toast('Scheduler stopped', 'info');
    loadScheduler();
}

async function runSchedulerNow() {
    toast('Running production cycle...', 'info');
    try {
        const res = await fetch('/api/scheduler/run-now', { method: 'POST' });
        const result = await res.json();
        if (result.status === 'done') {
            toast('Video produced: ' + (result.title || 'Success'), 'success');
            if (typeof loadDashboard === 'function') loadDashboard();
            loadVideos();
        } else if (result.status === 'skipped') {
            toast('Skipped: ' + result.reason, 'info');
        } else {
            toast('Error: ' + (result.error || 'Unknown'), 'error');
        }
    } catch (e) {
        toast('Error: ' + e.message, 'error');
    }
}

// === SUBTITLE CONFIG ===
const SUB_PRESETS = {
    viral: { font: "Arial Black", size: 18, highlight_color: "&H0000FFFF", position: "center", words_per_chunk: 2, bold: true },
    bold_red: { font: "Impact", size: 20, highlight_color: "&H000000FF", position: "center", words_per_chunk: 2, bold: true },
    neon_green: { font: "Arial Black", size: 18, highlight_color: "&H0000FF00", position: "center", words_per_chunk: 2, bold: true },
    classic: { font: "Arial", size: 14, highlight_color: "&H00FFFFFF", position: "bottom", words_per_chunk: 8, bold: false },
};

function loadSubPreset() {
    const preset = document.getElementById('sub-preset').value;
    const p = SUB_PRESETS[preset];
    if (!p) return;
    document.getElementById('sub-font').value = p.font;
    document.getElementById('sub-size').value = p.size;
    document.getElementById('sub-size-val').textContent = p.size;
    document.getElementById('sub-highlight').value = p.highlight_color;
    document.getElementById('sub-position').value = p.position;
    document.getElementById('sub-words').value = p.words_per_chunk;
}

function _getSubStyle() {
    return {
        preset: document.getElementById('sub-preset').value,
        font: document.getElementById('sub-font').value,
        size: parseInt(document.getElementById('sub-size').value),
        highlight_color: document.getElementById('sub-highlight').value,
        primary_color: "&H00FFFFFF",
        outline_color: "&H00000000",
        outline_width: 3,
        shadow: 2,
        position: document.getElementById('sub-position').value,
        margin_v: document.getElementById('sub-position').value === 'center' ? 400 : 60,
        bold: true,
        words_per_chunk: parseInt(document.getElementById('sub-words').value),
    };
}

async function previewSubtitles() {
    const style = _getSubStyle();
    const text = document.getElementById('sub-preview-text').value.trim();
    const lang = document.getElementById('sub-preview-lang').value;

    toast('Generating preview...', 'info');

    try {
        const res = await fetch('/api/subtitles/preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text || '', language: lang, style }),
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Preview failed');
        }

        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const video = document.getElementById('sub-preview-video');
        video.src = url;
        document.getElementById('sub-preview-container').classList.remove('hidden');
        video.play();
        toast('Preview ready!', 'success');
    } catch (e) {
        toast('Preview error: ' + e.message, 'error');
    }
}

async function saveSubtitleStyle() {
    const style = _getSubStyle();
    try {
        await fetch('/api/subtitles/save-style', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(style),
        });
        toast('Subtitle style saved globally!', 'success');
    } catch (e) {
        toast('Error saving', 'error');
    }
}

// === VOICE PREVIEW ===
function previewVoice() {
    const voiceId = document.getElementById('char-voice').value;
    if (!voiceId) { toast('Select a voice first', 'error'); return; }
    const player = document.getElementById('voice-preview-player');
    player.src = `/api/voice-preview/${voiceId}`;
    player.style.display = 'block';
    player.play();
    toast(`Playing: ${voiceId}`, 'info');
}

function stopVoicePreview() {
    const player = document.getElementById('voice-preview-player');
    player.pause();
    player.style.display = 'none';
}

async function saveOllama() {
    const model = document.getElementById('set-ollama-model').value;
    await fetch('/api/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ollama_model: model }) });
    toast(model ? `Ollama: ${model}` : 'Ollama disabled', 'success');
}

async function saveMusicSettings() {
    const enabled = document.getElementById('set-music-enabled').value === 'true';
    const mood = document.getElementById('set-music-mood').value;
    await fetch('/api/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ music_enabled: enabled, music_mood: mood }) });
    toast(`Music ${enabled ? 'on' : 'off'} (${mood})`, 'success');
}

async function saveVoiceSettings() {
    const speed = parseFloat(document.getElementById('set-kokoro-speed').value);
    const rate = document.getElementById('set-tts-rate').value;
    const pitch = document.getElementById('set-tts-pitch').value;
    await fetch('/api/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ kokoro_speed: speed, tts_rate: rate, tts_pitch: pitch }) });
    toast(`Voice: Kokoro ${speed}x, Edge ${rate}`, 'success');
}

async function loadVoiceSettings() {
    try {
        const res = await fetch('/api/settings');
        const s = await res.json();
        if (s.kokoro_speed !== undefined) {
            document.getElementById('set-kokoro-speed').value = s.kokoro_speed;
            document.getElementById('kokoro-speed-val').textContent = s.kokoro_speed;
        }
        if (s.tts_rate) document.getElementById('set-tts-rate').value = s.tts_rate;
        if (s.tts_pitch) document.getElementById('set-tts-pitch').value = s.tts_pitch;
    } catch (e) {}
}

// === TTS BENCHMARK ===
async function loadBenchmark() {
    try {
        const res = await fetch('/api/tts/benchmark');
        const data = await res.json();
        const container = document.getElementById('benchmark-container');
        if (!container) return;

        const colors = { fish: '#00d4aa', xtts: '#7c3aed', 'edge-tts': '#3b82f6', kokoro: '#f59e0b', elevenlabs: '#ef4444' };

        let html = '<table style="width:100%;font-size:12px;border-collapse:collapse">';
        html += '<tr style="border-bottom:1px solid var(--border)">';
        html += '<th style="text-align:left;padding:8px 6px">Engine</th>';
        html += '<th style="text-align:center;padding:8px 4px">Naturalidad</th>';
        html += '<th style="text-align:center;padding:8px 4px">Español</th>';
        html += '<th style="text-align:left;padding:8px 4px">Velocidad</th>';
        html += '<th style="text-align:left;padding:8px 4px">Costo</th>';
        html += '<th style="text-align:center;padding:8px 4px">Clonar</th>';
        html += '<th style="text-align:center;padding:8px 4px">Local</th>';
        html += '<th style="text-align:center;padding:8px 4px">Estado</th>';
        html += '</tr>';

        data.engines.forEach(e => {
            const color = colors[e.id] || '#888';
            const natBar = `<div style="background:var(--bg-input);border-radius:4px;height:16px;width:100px;display:inline-block;position:relative"><div style="background:${color};border-radius:4px;height:16px;width:${e.naturalness*10}px"></div><span style="position:absolute;left:50%;top:0;transform:translateX(-50%);font-size:10px;font-weight:700;color:white;line-height:16px">${e.naturalness}</span></div>`;
            const esBar = `<div style="background:var(--bg-input);border-radius:4px;height:16px;width:100px;display:inline-block;position:relative"><div style="background:${color};border-radius:4px;height:16px;width:${e.spanish*10}px"></div><span style="position:absolute;left:50%;top:0;transform:translateX(-50%);font-size:10px;font-weight:700;color:white;line-height:16px">${e.spanish}</span></div>`;

            html += `<tr style="border-bottom:1px solid var(--border)">`;
            html += `<td style="padding:8px 6px;font-weight:600"><span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${color};margin-right:6px"></span>${e.name}</td>`;
            html += `<td style="text-align:center;padding:8px 4px">${natBar}</td>`;
            html += `<td style="text-align:center;padding:8px 4px">${esBar}</td>`;
            html += `<td style="padding:8px 4px;font-size:11px">${e.speed}</td>`;
            html += `<td style="padding:8px 4px;font-size:11px">${e.cost}</td>`;
            html += `<td style="text-align:center;padding:8px 4px">${e.voice_clone ? '✅' : '❌'}</td>`;
            html += `<td style="text-align:center;padding:8px 4px">${e.local ? '✅' : '☁️'}</td>`;
            html += `<td style="text-align:center;padding:8px 4px">${e.configured ? '<span style="color:var(--success)">Listo</span>' : '<span style="color:var(--text-muted)">No config</span>'}</td>`;
            html += '</tr>';

            // Pros/cons row
            html += `<tr style="border-bottom:2px solid var(--border)"><td colspan="8" style="padding:2px 6px 8px 20px;font-size:10px;color:var(--text-muted)">`;
            html += e.pros.map(p => `<span style="color:var(--success)">+${p}</span>`).join(' &nbsp; ');
            html += ' &nbsp; ';
            html += e.cons.map(c => `<span style="color:var(--danger)">-${c}</span>`).join(' &nbsp; ');
            html += '</td></tr>';
        });

        html += '</table>';
        container.innerHTML = html;
    } catch (e) { console.error('Benchmark load error', e); }
}

// === XTTS v2 ===
let mediaRecorder = null;
let recordedChunks = [];

async function loadXttsVoices() {
    try {
        const res = await fetch('/api/xtts/voices');
        const voices = await res.json();
        const select = document.getElementById('xtts-voice-select');
        const optgroup = document.getElementById('xtts-voice-options');
        if (!select || !optgroup) return;

        select.innerHTML = '<option value="default">Default (auto-generated)</option>';
        optgroup.innerHTML = '<option value="xtts:default">XTTS: Default voice</option>';

        voices.forEach(v => {
            const name = v.id.replace('xtts:', '');
            if (name === 'default' || name.startsWith('_')) return;
            select.innerHTML += `<option value="${name}">${name} (${v.file || 'uploaded'})</option>`;
            optgroup.innerHTML += `<option value="${v.id}">${v.name}</option>`;
        });
    } catch (e) {}
}

async function uploadXttsVoice() {
    const fileInput = document.getElementById('xtts-voice-file');
    const nameInput = document.getElementById('xtts-voice-name');
    if (!fileInput.files.length) { toast('Select an audio file', 'error'); return; }
    if (!nameInput.value.trim()) { toast('Enter a voice name', 'error'); return; }

    const formData = new FormData();
    formData.append('audio', fileInput.files[0]);
    formData.append('name', nameInput.value.trim());

    try {
        const res = await fetch('/api/xtts/upload-voice', { method: 'POST', body: formData });
        const data = await res.json();
        toast(data.message, 'success');
        fileInput.value = '';
        nameInput.value = '';
        loadXttsVoices();
    } catch (e) { toast('Upload failed', 'error'); }
}

function toggleRecording() {
    const btn = document.getElementById('xtts-record-btn');
    const status = document.getElementById('xtts-record-status');

    if (mediaRecorder && mediaRecorder.state === 'recording') {
        mediaRecorder.stop();
        btn.textContent = '🎙️ Start Recording';
        btn.classList.remove('btn-danger');
        btn.classList.add('btn-secondary');
        status.textContent = 'Processing...';
        return;
    }

    const name = document.getElementById('xtts-record-name').value.trim();
    if (!name) { toast('Enter a voice name first', 'error'); return; }

    navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
        recordedChunks = [];
        mediaRecorder = new MediaRecorder(stream);

        mediaRecorder.ondataavailable = e => { if (e.data.size > 0) recordedChunks.push(e.data); };

        mediaRecorder.onstop = async () => {
            stream.getTracks().forEach(t => t.stop());
            const blob = new Blob(recordedChunks, { type: 'audio/webm' });
            const formData = new FormData();
            formData.append('audio', blob, 'recording.webm');
            formData.append('name', name);

            try {
                const res = await fetch('/api/xtts/record-voice', { method: 'POST', body: formData });
                const data = await res.json();
                toast(data.message, 'success');
                status.textContent = 'Saved!';
                loadXttsVoices();
            } catch (e) {
                toast('Recording failed', 'error');
                status.textContent = 'Error';
            }
        };

        mediaRecorder.start();
        btn.textContent = '⏹️ Stop Recording';
        btn.classList.remove('btn-secondary');
        btn.classList.add('btn-danger');
        status.textContent = 'Recording... (speak for 6-15 seconds)';

        // Auto-stop after 15 seconds
        setTimeout(() => {
            if (mediaRecorder && mediaRecorder.state === 'recording') {
                mediaRecorder.stop();
                btn.textContent = '🎙️ Start Recording';
                btn.classList.remove('btn-danger');
                btn.classList.add('btn-secondary');
            }
        }, 15000);
    }).catch(e => {
        toast('Microphone access denied', 'error');
    });
}

async function previewXtts() {
    const text = document.getElementById('xtts-preview-text').value;
    const lang = document.getElementById('xtts-language').value;
    const voice = document.getElementById('xtts-voice-select').value;
    const btn = document.getElementById('xtts-preview-btn');
    const audio = document.getElementById('xtts-preview-audio');

    btn.textContent = '⏳ Generating...';
    btn.disabled = true;

    try {
        const res = await fetch('/api/xtts/preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text, language: lang, voice })
        });
        if (!res.ok) throw new Error('Preview failed');
        const blob = await res.blob();
        audio.src = URL.createObjectURL(blob);
        audio.style.display = 'block';
        audio.play();
        toast('Preview generated!', 'success');
    } catch (e) {
        toast('Preview failed: ' + e.message, 'error');
    } finally {
        btn.textContent = '▶️ Preview';
        btn.disabled = false;
    }
}

async function saveXttsSettings() {
    const lang = document.getElementById('xtts-language').value;
    const settings = { xtts: { language: lang } };
    // Save to settings.json via the generic settings endpoint
    const res = await fetch('/api/settings');
    const current = await res.json();
    current.xtts = settings.xtts;
    // Direct write
    await fetch('/api/settings/raw', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(current)
    });
    toast(`XTTS language: ${lang}`, 'success');
}

// === UTILS ===
function esc(str) { if (!str) return ''; const d = document.createElement('div'); d.textContent = str; return d.innerHTML; }
function toast(msg, type = 'info') { const el = document.getElementById('toast'); el.textContent = msg; el.className = `toast ${type}`; el.classList.remove('hidden'); setTimeout(() => el.classList.add('hidden'), 4000); }
function notify(msg) { const el = document.getElementById('notification'); document.getElementById('notif-text').textContent = msg; el.classList.remove('hidden'); setTimeout(() => el.classList.add('hidden'), 8000); }
