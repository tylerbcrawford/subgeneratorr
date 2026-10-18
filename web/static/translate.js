/**
 * Subtitle translation UI (v2.4.0; catalog + model-aware targets v3.3.0).
 *
 * Self-contained add-on to app.js. Reuses app.js globals (getCurrentVideoPath,
 * showToast, escapeHtml) which are available because both are classic scripts
 * sharing one global scope. Drives POST /api/translate + status polling.
 */
(function () {
    'use strict';

    // Target languages come from the shared catalog (languages.js, rendered
    // from core/languages.py) filtered by the user's saved list; the backend
    // validates them too.
    function targetLanguages() {
        return window.SubgenLanguages ? window.SubgenLanguages.translationTargets() : [];
    }

    // Cloud model roster from core/llm_providers.MODEL_SPECS, injected by
    // index.html as window.LLM_MODELS ({provider: [{id, label, hint}]}).
    function modelsFor(provider) {
        return (window.LLM_MODELS && window.LLM_MODELS[provider]) || [];
    }

    function modelLabel(modelId) {
        const all = Object.values(window.LLM_MODELS || {}).flat();
        const match = all.find(function (m) { return m.id === modelId; });
        return match ? match.label : modelId;
    }

    let providerStatus = {}; // {anthropic: bool, openai: bool, google: bool, ollama: bool}

    // --- Small helpers (fall back gracefully if app.js globals are absent) ---

    function toast(type, msg) {
        if (typeof showToast === 'function') showToast(type, msg);
    }

    function esc(s) {
        return typeof escapeHtml === 'function' ? escapeHtml(s) : String(s);
    }

    function currentVideo() {
        if (typeof getCurrentVideoPath === 'function') return getCurrentVideoPath();
        const checked = document.querySelector('.browser-file input[type="checkbox"]:checked');
        return checked ? checked.value : null;
    }

    function $(id) {
        return document.getElementById(id);
    }

    // --- DOM construction ---------------------------------------------------

    let selectedTargets = []; // target language codes, in selection order

    // Advisory support info for the selected model (GET /api/languages/translation-support):
    // {supported: [codes] | null (all), verified, label}
    let support = { supported: null, verified: true, label: '' };

    function isSupported(code) {
        return !support.supported || support.supported.indexOf(code) !== -1;
    }

    function buildTargetDropdown() {
        const select = $('translateTargetSelect');
        if (!select) return;
        const langs = targetLanguages();
        const ok = langs.filter(function (l) { return isSupported(l.code); });
        const no = langs.filter(function (l) { return !isSupported(l.code); });
        function opt(l, disabled) {
            return '<option value="' + esc(l.code) + '"' + (disabled ? ' disabled' : '') + '>' +
                esc(l.name) + '</option>';
        }
        let html = '<option value="" disabled selected>Add a language…</option>' +
            ok.map(function (l) { return opt(l, false); }).join('');
        if (no.length) {
            html += '<optgroup label="Not supported by ' + esc(support.label) + '">' +
                no.map(function (l) { return opt(l, true); }).join('') + '</optgroup>';
        }
        const customize = window.SubgenLanguages ? window.SubgenLanguages.CUSTOMIZE : '';
        if (customize) {
            html += '<optgroup label="──────────"><option value="' + customize +
                '">Customize languages…</option></optgroup>';
        }
        select.innerHTML = html;
        renderSupportNote(langs.length, no.length);
    }

    function renderSupportNote(total, unsupported) {
        const note = $('translateSupportNote');
        if (!note) return;
        let text = '';
        if (!support.verified) {
            text = 'No language data for ' + support.label + ' — every target is listed, but quality is unverified.';
        } else if (support.supported && support.supported.length === 0) {
            text = support.label + ' is English-only per its model card. Pick a multilingual model (e.g. qwen3, gemma3) to translate.';
        } else if (unsupported) {
            text = support.label + ' officially supports ' + (total - unsupported) + ' of these ' + total +
                ' languages; the rest are greyed out.';
        }
        note.textContent = text;
        note.classList.toggle('hidden', !text);
    }

    function _langName(code) {
        return window.SubgenLanguages ? window.SubgenLanguages.name(code) : code;
    }

    function renderChips() {
        const box = $('translateChips');
        if (!box) return;
        box.innerHTML = selectedTargets.map(function (code) {
            const ok = isSupported(code);
            const title = ok ? '' : ' title="Not officially supported by ' + esc(support.label) + '"';
            return (
                '<span class="translate-chip' + (ok ? '' : ' translate-chip-warn') + '"' + title + '>' +
                (ok ? '' : '<span aria-hidden="true">⚠</span>') + esc(_langName(code)) +
                (ok ? '' : '<span class="sr-only"> (not supported by ' + esc(support.label) + ')</span>') +
                '<button type="button" class="chip-remove" data-code="' + esc(code) +
                '" aria-label="Remove ' + esc(_langName(code)) + '">✕</button></span>'
            );
        }).join('');
        box.querySelectorAll('.chip-remove').forEach(function (btn) {
            btn.addEventListener('click', function () { removeTarget(btn.getAttribute('data-code')); });
        });
        // Grey out already-selected and unsupported languages in the dropdown.
        const select = $('translateTargetSelect');
        if (select) {
            Array.from(select.options).forEach(function (opt) {
                if (opt.value && !(window.SubgenLanguages && opt.value === window.SubgenLanguages.CUSTOMIZE)) {
                    opt.disabled = selectedTargets.indexOf(opt.value) !== -1 || !isSupported(opt.value);
                }
            });
        }
    }

    let supportRequest = 0;

    async function refreshSupport() {
        const pm = getProviderModel();
        const ticket = ++supportRequest;
        let info = { supported: null, verified: true, label: modelLabel(pm.model) };
        if (pm.provider === 'ollama' && !pm.model) {
            info = { supported: null, verified: true, label: 'Ollama' };
        } else {
            try {
                const resp = await fetch('/api/languages/translation-support?provider=' +
                    encodeURIComponent(pm.provider) + '&model=' + encodeURIComponent(pm.model || ''));
                if (resp.ok) info = await resp.json();
            } catch (_e) { /* advisory only: keep everything selectable */ }
        }
        if (ticket !== supportRequest) return; // a newer model choice won
        support = info;
        buildTargetDropdown();
        renderChips();
    }

    function rebuildTargets() {
        // Drop chips the user removed from their saved list; keep the rest
        const allowed = targetLanguages().map(function (l) { return l.code; });
        selectedTargets = selectedTargets.filter(function (c) { return allowed.indexOf(c) !== -1; });
        buildTargetDropdown();
        renderChips();
        updateCostEstimate();
    }

    function addTarget(code) {
        if (!code || selectedTargets.indexOf(code) !== -1) return;
        selectedTargets.push(code);
        renderChips();
        updateCostEstimate();
    }

    function removeTarget(code) {
        selectedTargets = selectedTargets.filter(function (c) { return c !== code; });
        renderChips();
        updateCostEstimate();
    }

    function getSelectedTargets() {
        return selectedTargets.slice();
    }

    let ollamaPicker = null; // web/static/ollama.js controller

    function getProviderModel() {
        const provider = ($('translateProvider') || {}).value || 'anthropic';
        if (provider === 'ollama') {
            return {
                provider: provider,
                model: ollamaPicker ? ollamaPicker.model() : '',
                ollamaHost: ollamaPicker ? ollamaPicker.host() : null,
            };
        }
        const model = ($('translateModel') || {}).value || (modelsFor(provider)[0] || {}).id;
        return { provider: provider, model: model, ollamaHost: null };
    }

    // --- Provider / model wiring -------------------------------------------

    function onModelChange() {
        updateModelDisplay();
        updateProviderStatusBadge();
        updateCostEstimate();
        refreshSupport();
    }

    function onProviderChange() {
        const provider = ($('translateProvider') || {}).value || 'anthropic';
        const modelSelect = $('translateModel');
        const ollamaHostGroup = $('translateOllamaHostGroup');

        const isOllama = provider === 'ollama';
        if (ollamaHostGroup) ollamaHostGroup.classList.toggle('hidden', !isOllama);

        if (isOllama && ollamaPicker) {
            if (modelSelect) modelSelect.innerHTML = '';
            ollamaPicker.refresh(); // fills the select, then calls onModelChange
            onModelChange();
            return;
        }
        if (ollamaPicker) ollamaPicker.deactivate();
        if (modelSelect) {
            modelSelect.innerHTML = modelsFor(provider).map(function (m) {
                return '<option value="' + esc(m.id) + '">' + esc(m.label) + ' (' + esc(m.hint) + ')</option>';
            }).join('');
        }
        onModelChange();
    }

    function updateModelDisplay() {
        const display = $('translateModelDisplay');
        if (!display) return;
        const pm = getProviderModel();
        if (pm.provider === 'ollama') {
            display.textContent = 'Ollama (' + (pm.model || 'pick a model') + ')';
        } else {
            display.textContent = modelLabel(pm.model);
        }
    }

    function updateProviderStatusBadge() {
        const provider = ($('translateProvider') || {}).value || 'anthropic';
        const badge = $('translateKeyStatus');
        const notice = $('translateKeyNotice');
        const ok = !!providerStatus[provider] ||
            (provider === 'ollama' && !!(ollamaPicker && ollamaPicker.host()));
        const label = provider.charAt(0).toUpperCase() + provider.slice(1);

        if (badge) {
            badge.className = 'api-key-status ' + (ok ? 'configured' : 'missing');
            const msg = ok ? label + ' configured' : label + ' not configured';
            badge.setAttribute('data-status', msg);
            badge.setAttribute('aria-label', msg);
        }
        if (notice) {
            if (ok) {
                notice.style.display = 'none';
            } else {
                notice.style.display = '';
                notice.textContent = provider === 'ollama'
                    ? 'Set OLLAMA_HOST (or enter a host below) to use local translation.'
                    : 'Set the ' + provider.toUpperCase() + ' API key on the server to use this provider.';
            }
        }
    }

    // --- Cost estimate ------------------------------------------------------

    async function updateCostEstimate() {
        const el = $('translateCostEstimate');
        if (!el) return;

        const videoPath = currentVideo();
        const targets = getSelectedTargets();
        if (!videoPath || targets.length === 0) {
            el.textContent = '';
            el.style.color = 'var(--text-tertiary)';
            return;
        }

        const pm = getProviderModel();
        if (pm.provider === 'ollama') {
            el.textContent = pm.model ? 'Free · runs on your Ollama server' : 'Pick an Ollama model';
            el.style.color = 'var(--text-tertiary)';
            return;
        }
        try {
            el.textContent = 'Calculating...';
            el.style.color = 'var(--text-tertiary)';
            const resp = await fetch('/api/translate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    video_path: videoPath,
                    targets: targets,
                    provider: pm.provider,
                    model: pm.model,
                    ollama_host: pm.ollamaHost,
                    estimate_only: true,
                }),
            });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.error || 'estimate failed');
            const cost = (data.estimated_cost || 0).toFixed(4);
            el.textContent = 'Est. cost: $' + cost + ' (' + targets.length + ' language' +
                (targets.length === 1 ? '' : 's') + ')';
            el.style.color = 'var(--text-secondary)';
        } catch (err) {
            el.textContent = 'Unable to estimate cost';
            el.style.color = 'var(--text-tertiary)';
        }
    }

    // --- Translate action ---------------------------------------------------

    function setTranslating(on) {
        const btn = $('translateBtn');
        if (!btn) return;
        btn.disabled = on;
        if (on) {
            btn.classList.add('processing');
            btn.innerHTML = '<span class="spinner-inline" aria-hidden="true"></span>Translating...';
        } else {
            btn.classList.remove('processing');
            btn.textContent = 'Translate';
        }
    }

    async function handleTranslate() {
        const videoPath = currentVideo();
        if (!videoPath) {
            toast('warning', 'Select a video with subtitles first');
            return;
        }
        const targets = getSelectedTargets();
        if (targets.length === 0) {
            toast('warning', 'Pick at least one target language');
            return;
        }
        const pm = getProviderModel();
        if (pm.provider === 'ollama' && !pm.model) {
            toast('warning', 'Pick an installed Ollama model (or type a model name) first');
            return;
        }
        const overwrite = !!($('translateOverwrite') || {}).checked;

        setTranslating(true);
        try {
            const resp = await fetch('/api/translate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    video_path: videoPath,
                    targets: targets,
                    provider: pm.provider,
                    model: pm.model,
                    ollama_host: pm.ollamaHost,
                    overwrite: overwrite,
                }),
            });
            const data = await resp.json();
            if (!resp.ok) {
                throw new Error(data.error || 'Failed to start translation');
            }
            toast('info', 'Translating into ' + targets.length + ' language' +
                (targets.length === 1 ? '' : 's') + '...');
            pollStatus(data.task_id, pm.provider);
        } catch (err) {
            setTranslating(false);
            toast('error', 'Translation failed: ' + err.message);
        }
    }

    function pollStatus(taskId, provider) {
        let polls = 0;
        // 150 × 2s = 5 min for cloud; local CPU models can take much longer
        const maxPolls = provider === 'ollama' ? 1800 : 150;
        const interval = setInterval(async function () {
            polls++;
            try {
                const resp = await fetch('/api/translate/status/' + taskId);
                const data = await resp.json();

                if (!resp.ok || (!data.state && data.error)) {
                    clearInterval(interval);
                    setTranslating(false);
                    toast('error', 'Translation failed: ' + (data.error || 'server error'));
                    return;
                }
                if (polls >= maxPolls) {
                    clearInterval(interval);
                    setTranslating(false);
                    toast('error', 'Translation timed out');
                    return;
                }
                if (data.state === 'SUCCESS') {
                    clearInterval(interval);
                    setTranslating(false);
                    const made = data.translated || 0;
                    const skipped = data.skipped_count || 0;
                    let msg = 'Translation complete — ' + made + ' written';
                    if (skipped) msg += ', ' + skipped + ' skipped (already existed)';
                    toast('success', msg);
                    updateCostEstimate();
                } else if (data.state === 'FAILURE') {
                    clearInterval(interval);
                    setTranslating(false);
                    toast('error', 'Translation failed: ' + (data.error || 'unknown error'));
                }
            } catch (err) {
                clearInterval(interval);
                setTranslating(false);
                toast('error', 'Lost connection while translating');
            }
        }, 2000);
    }

    // --- Init ---------------------------------------------------------------

    function loadProviderStatus() {
        fetch('/api/config')
            .then(function (r) { return r.json(); })
            .then(function (config) {
                providerStatus = (config && config.providers) || {};
                updateProviderStatusBadge();
            })
            .catch(function () { /* non-fatal */ });
    }

    function init() {
        buildTargetDropdown();
        renderChips();

        const targetSelect = $('translateTargetSelect');
        if (targetSelect) {
            targetSelect.addEventListener('change', function () {
                if (window.SubgenLanguages && targetSelect.value === window.SubgenLanguages.CUSTOMIZE) {
                    targetSelect.value = '';
                    window.SubgenLanguages.openPanel('translation');
                    return;
                }
                addTarget(targetSelect.value);
                targetSelect.value = ''; // reset to the "Add a language…" placeholder
            });
        }

        const provider = $('translateProvider');
        if (provider) provider.addEventListener('change', onProviderChange);

        const modelSelect = $('translateModel');
        if (modelSelect) modelSelect.addEventListener('change', onModelChange);
        if (window.SubgenOllama && provider) {
            ollamaPicker = window.SubgenOllama.attach({
                select: modelSelect,
                textInput: $('translateOllamaModel'),
                hostInput: $('translateOllamaHost'),
                refreshBtn: $('translateOllamaRefresh'),
                statusEl: $('translateOllamaStatus'),
                isActive: function () { return provider.value === 'ollama'; },
                onChange: onModelChange,
            });
        }
        if (window.SubgenLanguages) window.SubgenLanguages.onPrefsChange(rebuildTargets);

        const toggle = $('translateConfigToggleBtn');
        const panel = $('translateConfigPanel');
        if (toggle && panel) {
            toggle.addEventListener('click', function () {
                const isHidden = panel.classList.toggle('hidden');
                toggle.setAttribute('aria-expanded', String(!isHidden));
            });
        }

        const btn = $('translateBtn');
        if (btn) btn.addEventListener('click', handleTranslate);

        loadProviderStatus();
        onProviderChange();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
