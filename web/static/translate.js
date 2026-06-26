/**
 * Subtitle translation UI (v2.4.0).
 *
 * Self-contained add-on to app.js. Reuses app.js globals (getCurrentVideoPath,
 * showToast, escapeHtml) which are available because both are classic scripts
 * sharing one global scope. Drives POST /api/translate + status polling.
 */
(function () {
    'use strict';

    // Supported subtitle target languages (mirrors core/_SUBTITLE_LANG_MAP),
    // sorted by display name. The backend validates these too.
    const TRANSLATE_LANGUAGES = [
        { code: 'ar', name: 'Arabic' }, { code: 'be', name: 'Belarusian' },
        { code: 'bn', name: 'Bengali' }, { code: 'bs', name: 'Bosnian' },
        { code: 'bg', name: 'Bulgarian' }, { code: 'ca', name: 'Catalan' },
        { code: 'zh', name: 'Chinese' }, { code: 'hr', name: 'Croatian' },
        { code: 'cs', name: 'Czech' }, { code: 'da', name: 'Danish' },
        { code: 'nl', name: 'Dutch' }, { code: 'et', name: 'Estonian' },
        { code: 'fi', name: 'Finnish' }, { code: 'fr', name: 'French' },
        { code: 'de', name: 'German' }, { code: 'el', name: 'Greek' },
        { code: 'gu', name: 'Gujarati' }, { code: 'he', name: 'Hebrew' },
        { code: 'hi', name: 'Hindi' }, { code: 'hu', name: 'Hungarian' },
        { code: 'id', name: 'Indonesian' }, { code: 'it', name: 'Italian' },
        { code: 'ja', name: 'Japanese' }, { code: 'kn', name: 'Kannada' },
        { code: 'ko', name: 'Korean' }, { code: 'lv', name: 'Latvian' },
        { code: 'lt', name: 'Lithuanian' }, { code: 'mk', name: 'Macedonian' },
        { code: 'ms', name: 'Malay' }, { code: 'mr', name: 'Marathi' },
        { code: 'no', name: 'Norwegian' }, { code: 'fa', name: 'Persian' },
        { code: 'pl', name: 'Polish' }, { code: 'pt', name: 'Portuguese' },
        { code: 'ro', name: 'Romanian' }, { code: 'ru', name: 'Russian' },
        { code: 'sr', name: 'Serbian' }, { code: 'sk', name: 'Slovak' },
        { code: 'sl', name: 'Slovenian' }, { code: 'es', name: 'Spanish' },
        { code: 'sv', name: 'Swedish' }, { code: 'tl', name: 'Tagalog' },
        { code: 'ta', name: 'Tamil' }, { code: 'te', name: 'Telugu' },
        { code: 'th', name: 'Thai' }, { code: 'tr', name: 'Turkish' },
        { code: 'uk', name: 'Ukrainian' }, { code: 'ur', name: 'Urdu' },
        { code: 'vi', name: 'Vietnamese' },
    ];

    const MODELS_BY_PROVIDER = {
        anthropic: [
            { value: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6 (Best Quality)' },
            { value: 'claude-haiku-4-5', label: 'Claude Haiku 4.5 (Faster, Cheaper)' },
        ],
        openai: [
            { value: 'gpt-4.1', label: 'GPT-4.1 (Best Quality)' },
            { value: 'gpt-4.1-mini', label: 'GPT-4.1 Mini (Faster, Cheaper)' },
        ],
        google: [
            { value: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash' },
        ],
    };

    const MODEL_DISPLAY = {
        'claude-sonnet-4-6': 'Claude Sonnet 4.6',
        'claude-haiku-4-5': 'Claude Haiku 4.5',
        'gpt-4.1': 'GPT-4.1',
        'gpt-4.1-mini': 'GPT-4.1 Mini',
        'gemini-2.5-flash': 'Gemini 2.5 Flash',
    };

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

    function buildTargetDropdown() {
        const select = $('translateTargetSelect');
        if (!select) return;
        const placeholder = '<option value="" disabled selected>Add a language…</option>';
        const opts = TRANSLATE_LANGUAGES.map(function (lang) {
            return '<option value="' + lang.code + '">' + esc(lang.name) + '</option>';
        }).join('');
        select.innerHTML = placeholder + opts;
    }

    function _langName(code) {
        const lang = TRANSLATE_LANGUAGES.find(function (l) { return l.code === code; });
        return lang ? lang.name : code;
    }

    function renderChips() {
        const box = $('translateChips');
        if (!box) return;
        box.innerHTML = selectedTargets.map(function (code) {
            return (
                '<span class="translate-chip">' + esc(_langName(code)) +
                '<button type="button" class="chip-remove" data-code="' + code +
                '" aria-label="Remove ' + esc(_langName(code)) + '">✕</button></span>'
            );
        }).join('');
        box.querySelectorAll('.chip-remove').forEach(function (btn) {
            btn.addEventListener('click', function () { removeTarget(btn.getAttribute('data-code')); });
        });
        // Grey out already-selected languages in the dropdown.
        const select = $('translateTargetSelect');
        if (select) {
            Array.from(select.options).forEach(function (opt) {
                if (opt.value) opt.disabled = selectedTargets.indexOf(opt.value) !== -1;
            });
        }
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

    function getProviderModel() {
        const provider = ($('translateProvider') || {}).value || 'anthropic';
        let model;
        let ollamaHost = null;
        if (provider === 'ollama') {
            model = ($('translateOllamaModel') || {}).value || 'llama3.1';
            ollamaHost = ($('translateOllamaHost') || {}).value || null;
        } else {
            model = ($('translateModel') || {}).value || MODELS_BY_PROVIDER[provider][0].value;
        }
        return { provider: provider, model: model, ollamaHost: ollamaHost };
    }

    // --- Provider / model wiring -------------------------------------------

    function onProviderChange() {
        const provider = ($('translateProvider') || {}).value || 'anthropic';
        const modelSelect = $('translateModel');
        const ollamaModel = $('translateOllamaModel');
        const ollamaHostGroup = $('translateOllamaHostGroup');

        const isOllama = provider === 'ollama';
        if (modelSelect) modelSelect.classList.toggle('hidden', isOllama);
        if (ollamaModel) ollamaModel.classList.toggle('hidden', !isOllama);
        if (ollamaHostGroup) ollamaHostGroup.classList.toggle('hidden', !isOllama);

        if (!isOllama && modelSelect) {
            modelSelect.innerHTML = (MODELS_BY_PROVIDER[provider] || []).map(function (m) {
                return '<option value="' + m.value + '">' + esc(m.label) + '</option>';
            }).join('');
        }

        updateModelDisplay();
        updateProviderStatusBadge();
        updateCostEstimate();
    }

    function updateModelDisplay() {
        const display = $('translateModelDisplay');
        if (!display) return;
        const pm = getProviderModel();
        if (pm.provider === 'ollama') {
            display.textContent = 'Ollama (' + (pm.model || 'local') + ')';
        } else {
            display.textContent = MODEL_DISPLAY[pm.model] || pm.model;
        }
    }

    function updateProviderStatusBadge() {
        const provider = ($('translateProvider') || {}).value || 'anthropic';
        const badge = $('translateKeyStatus');
        const notice = $('translateKeyNotice');
        const ok = !!providerStatus[provider];

        if (badge) {
            badge.textContent = ok ? '✓' : '✗';
            badge.title = ok ? 'Configured' : 'Not configured';
            badge.style.color = ok ? 'var(--color-green)' : 'var(--color-red)';
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
            el.textContent = 'Est. cost: $0.00';
            el.style.color = 'var(--text-tertiary)';
            return;
        }

        const pm = getProviderModel();
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
            pollStatus(data.task_id);
        } catch (err) {
            setTranslating(false);
            toast('error', 'Translation failed: ' + err.message);
        }
    }

    function pollStatus(taskId) {
        let polls = 0;
        const maxPolls = 150; // 150 × 2s = 5 min
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
                addTarget(targetSelect.value);
                targetSelect.value = ''; // reset to the "Add a language…" placeholder
            });
        }

        const provider = $('translateProvider');
        if (provider) provider.addEventListener('change', onProviderChange);

        const modelSelect = $('translateModel');
        if (modelSelect) {
            modelSelect.addEventListener('change', updateModelDisplay);
            modelSelect.addEventListener('change', updateCostEstimate);
        }
        const ollamaModel = $('translateOllamaModel');
        if (ollamaModel) {
            ollamaModel.addEventListener('input', updateModelDisplay);
            ollamaModel.addEventListener('input', updateCostEstimate);
        }
        const ollamaHost = $('translateOllamaHost');
        if (ollamaHost) ollamaHost.addEventListener('input', updateProviderStatusBadge);

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
