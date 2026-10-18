/**
 * Shared Ollama model picker (v3.3.0).
 *
 * Fills an existing <select> with the models installed on an Ollama server
 * (GET /api/ollama/models, which proxies Ollama's /api/tags), with a refresh
 * button, an optional host field, and a free-text fallback input when the
 * server cannot be reached. Used by the keyterm (app.js) and translation
 * (translate.js) panels; both keep reading the model from select.value.
 */
(function () {
    'use strict';

    const LAST_MODEL_KEY = 'subgenOllamaModel';
    const LAST_HOST_KEY = 'subgenOllamaHost';

    function readPref(key) {
        try { return localStorage.getItem(key) || ''; } catch (_e) { return ''; }
    }

    function writePref(key, value) {
        try {
            if (value) localStorage.setItem(key, value);
            else localStorage.removeItem(key);
        } catch (_e) { /* storage blocked: preference just isn't remembered */ }
    }

    function esc(s) {
        return typeof escapeHtml === 'function' ? escapeHtml(s) : String(s);
    }

    async function fetchModels(host) {
        const qs = host ? '?host=' + encodeURIComponent(host) : '';
        const resp = await fetch('/api/ollama/models' + qs);
        let data = {};
        try { data = await resp.json(); } catch (_e) { /* non-JSON error page */ }
        if (!resp.ok) throw new Error(data.error || 'Could not reach Ollama');
        return data;
    }

    function optionLabel(m) {
        return m.parameter_size ? m.name + ' (' + m.parameter_size + ')' : m.name;
    }

    /**
     * Wire a picker. opts: {select, textInput, hostInput, refreshBtn, statusEl,
     * isActive: () => bool, onChange: () => void}. Returns a controller.
     */
    function attach(opts) {
        const select = opts.select;
        const textInput = opts.textInput;
        const hostInput = opts.hostInput;
        const refreshBtn = opts.refreshBtn;
        let models = [];
        let loading = null;
        let fallback = false;

        if (hostInput && !hostInput.value) hostInput.value = readPref(LAST_HOST_KEY);

        function setStatus(text, kind) {
            if (!opts.statusEl) return;
            opts.statusEl.textContent = text || '';
            opts.statusEl.className = 'ollama-status' + (kind ? ' ollama-status-' + kind : '');
            opts.statusEl.classList.toggle('hidden', !text);
        }

        function showFallback(on) {
            fallback = on;
            if (select) select.classList.toggle('hidden', on);
            if (textInput) {
                textInput.classList.toggle('hidden', !on);
                if (on && !textInput.value) textInput.value = readPref(LAST_MODEL_KEY);
            }
        }

        function render() {
            const preferred = select.value || readPref(LAST_MODEL_KEY);
            select.innerHTML = models.map(function (m) {
                return '<option value="' + esc(m.name) + '">' + esc(optionLabel(m)) + '</option>';
            }).join('');
            const match = models.find(function (m) { return m.name === preferred; });
            select.value = match ? match.name : (models[0] ? models[0].name : '');
        }

        async function refresh() {
            if (!opts.isActive()) return;
            const host = hostInput ? hostInput.value.trim() : '';
            if (refreshBtn) refreshBtn.disabled = true;
            setStatus('Loading installed models…', 'info');
            const request = loading = fetchModels(host);
            try {
                const data = await request;
                if (request !== loading) return; // a newer refresh superseded this one
                models = data.models || [];
                if (models.length) {
                    showFallback(false);
                    render();
                    setStatus('');
                } else {
                    showFallback(true);
                    setStatus('No models installed on ' + data.host + ' — pull one (e.g. ollama pull qwen3:8b) or type a name.', 'warn');
                }
            } catch (err) {
                if (request !== loading) return;
                models = [];
                showFallback(true);
                setStatus(err.message + '. Enter a model name manually.', 'warn');
            } finally {
                if (request === loading && refreshBtn) refreshBtn.disabled = false;
            }
            if (opts.onChange) opts.onChange();
        }

        function model() {
            const value = fallback ? (textInput ? textInput.value : '') : select.value;
            return (value || '').trim();
        }

        function host() {
            return hostInput ? (hostInput.value.trim() || null) : null;
        }

        if (refreshBtn) refreshBtn.addEventListener('click', refresh);
        if (hostInput) {
            hostInput.addEventListener('change', function () {
                writePref(LAST_HOST_KEY, hostInput.value.trim());
                refresh();
            });
        }
        if (select) {
            select.addEventListener('change', function () {
                if (opts.isActive() && !fallback) writePref(LAST_MODEL_KEY, select.value);
            });
        }
        if (textInput) {
            textInput.addEventListener('input', function () {
                writePref(LAST_MODEL_KEY, textInput.value.trim());
                if (opts.onChange) opts.onChange();
            });
        }

        return {
            refresh: refresh,
            model: model,
            host: host,
            deactivate: function () { showFallback(false); setStatus(''); },
            isFallback: function () { return fallback; },
        };
    }

    window.SubgenOllama = { attach: attach, fetchModels: fetchModels };
})();
