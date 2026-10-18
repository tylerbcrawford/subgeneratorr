/**
 * Language lists + "Customize languages" panel (v3.3.0).
 *
 * The catalog (core/languages.py) and the saved visibility prefs are injected
 * by index.html as window.LANGUAGE_CATALOG / window.LANGUAGE_PREFS, so the
 * transcription dropdown exists before app.js restores saved settings. The
 * visible list is: catalog ∩ what the selected engine supports ∩ saved prefs.
 * Prefs persist server-side (PUT /api/settings/languages); null = all.
 *
 * Exposes window.SubgenLanguages for app.js (engine changes) and translate.js
 * (target list, prefs-change subscription).
 */
(function () {
    'use strict';

    const CUSTOMIZE = '__customize__';
    let rendering = false;
    const SEPARATOR = '──────────';
    const KINDS = ['transcription', 'translation'];

    const catalog = Array.isArray(window.LANGUAGE_CATALOG) ? window.LANGUAGE_CATALOG : [];
    const byCode = {};
    catalog.forEach(function (l) { byCode[l.code] = l; });
    let prefs = normalizePrefs(window.LANGUAGE_PREFS);
    const defaultLanguage = window.DEFAULT_LANGUAGE || 'en';
    let engine = 'deepgram';
    // The language the user (or saved settings) asked for. Kept across engine
    // switches so a code one engine lacks comes back when the other returns.
    let preferred = null;
    const listeners = [];

    function normalizePrefs(raw) {
        const out = {};
        KINDS.forEach(function (k) {
            const v = raw && raw[k];
            out[k] = Array.isArray(v) && v.length ? v.slice() : null;
        });
        return out;
    }

    function esc(s) {
        return String(s).replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function toast(type, msg) {
        if (typeof showToast === 'function') showToast(type, msg);
    }

    function $(id) {
        return document.getElementById(id);
    }

    function eligible(kind) {
        return catalog.filter(function (l) {
            return kind === 'translation' ? l.translate : (l.deepgram || l.whisper);
        });
    }

    function visible(kind, code) {
        const list = prefs[kind];
        return !list || list.indexOf(code) !== -1;
    }

    function name(code) {
        return byCode[code] ? byCode[code].name : code;
    }

    // --- Transcription dropdown -------------------------------------------

    function engineEntries(eng) {
        const key = eng === 'whisper' ? 'whisper' : 'deepgram';
        const all = catalog.filter(function (l) { return l[key]; });
        const shown = all.filter(function (l) { return visible('transcription', l.code); });
        // Saved prefs may hold only the other engine's languages (or stale
        // codes); show the full engine list rather than an empty dropdown.
        return shown.length ? shown : all;
    }

    function pickValue(entries, wanted) {
        const codes = entries.map(function (l) { return l.code; });
        if (wanted && codes.indexOf(wanted) !== -1) return wanted;
        const base = wanted ? wanted.split('-')[0] : '';
        if (base && codes.indexOf(base) !== -1) return base;
        if (codes.indexOf(defaultLanguage) !== -1) return defaultLanguage;
        return codes[0] || '';
    }

    /**
     * Rebuild #language for an engine. A change event fires whenever the value
     * moves so app.js availability gating stays current; with notify, a
     * preferred language the new list cannot keep is also announced.
     */
    function renderTranscription(eng, opts) {
        if (eng) engine = eng;
        const select = $('language');
        if (!select || !catalog.length) return;
        const current = select.value;
        const wanted = preferred || current;
        const entries = engineEntries(engine);
        const top = entries.filter(function (l) { return l.code === defaultLanguage; });
        const specials = entries.filter(function (l) { return l.special; });
        const rest = entries.filter(function (l) { return !l.special && l.code !== defaultLanguage; });

        function opt(l) {
            return '<option value="' + esc(l.code) + '">' + esc(l.name) + '</option>';
        }
        function group(items) {
            return items.length
                ? '<optgroup label="' + SEPARATOR + '">' + items.map(opt).join('') + '</optgroup>'
                : '';
        }
        select.innerHTML = top.map(opt).join('') + group(specials) + group(rest) +
            '<optgroup label="' + SEPARATOR + '"><option value="' + CUSTOMIZE +
            '">Customize languages…</option></optgroup>';

        const value = pickValue(entries, wanted);
        select.value = value;
        if (opts && opts.notify && wanted && wanted !== CUSTOMIZE && value !== wanted) {
            const where = engine === 'whisper' ? 'the Local engine' : 'the Cloud engine';
            toast('info', name(wanted) + ' isn\'t available with ' + where + ' — switched to ' + name(value));
        }
        if (value !== current) {
            rendering = true;
            try {
                select.dispatchEvent(new Event('change'));
            } finally {
                rendering = false;
            }
        }
    }

    /** Set the transcription language, falling back like an engine switch would. */
    function selectTranscription(code) {
        const select = $('language');
        if (!select) return;
        if (code) preferred = code;
        select.value = pickValue(engineEntries(engine), code);
    }

    // --- Customize panel ---------------------------------------------------

    let activeKind = 'transcription';
    let draft = null; // {kind: Set(codes)}
    let lastFocus = null;

    function startDraft() {
        draft = {};
        KINDS.forEach(function (k) {
            const all = eligible(k).map(function (l) { return l.code; });
            draft[k] = new Set(prefs[k] ? prefs[k].filter(function (c) { return byCode[c]; }) : all);
        });
    }

    function badges(l) {
        if (activeKind !== 'transcription') return '';
        return (l.deepgram ? '<span class="lang-badge lang-badge-cloud">Cloud</span>' : '') +
            (l.whisper ? '<span class="lang-badge lang-badge-local">Local</span>' : '');
    }

    function filteredEntries() {
        const q = (($('langSearch') || {}).value || '').trim().toLowerCase();
        return eligible(activeKind).filter(function (l) {
            return !q || l.name.toLowerCase().indexOf(q) !== -1 || l.code.toLowerCase().indexOf(q) !== -1;
        });
    }

    function renderList() {
        const list = $('langList');
        if (!list) return;
        const entries = filteredEntries();
        const chosen = draft[activeKind];
        list.innerHTML = entries.length ? entries.map(function (l) {
            return '<label class="lang-row"><input type="checkbox" value="' + esc(l.code) + '"' +
                (chosen.has(l.code) ? ' checked' : '') + '>' +
                '<span class="lang-row-name" title="' + esc(l.name) + '">' + esc(l.name) + '</span>' +
                '<span class="lang-row-meta">' + badges(l) +
                (l.special ? '' : '<span class="lang-row-code">' + esc(l.code) + '</span>') +
                '</span></label>';
        }).join('') : '<p class="lang-empty">No languages match.</p>';
        updateCount();
    }

    function updateCount() {
        const el = $('langCount');
        if (!el) return;
        const total = eligible(activeKind).length;
        const n = draft[activeKind].size;
        el.textContent = (n === total ? 'All ' + total : n + ' of ' + total) + ' languages shown';
        const err = $('langError');
        if (err) err.classList.add('hidden');
    }

    function setTab(kind) {
        activeKind = kind;
        document.querySelectorAll('.lang-tab').forEach(function (tab) {
            const on = tab.getAttribute('data-kind') === kind;
            tab.setAttribute('aria-selected', String(on));
            tab.tabIndex = on ? 0 : -1;
        });
        const list = $('langList');
        if (list) list.setAttribute('aria-labelledby', kind === 'translation' ? 'langTabTranslation' : 'langTabTranscription');
        renderList();
    }

    function openPanel(kind, returnFocusTo) {
        const dialog = $('languagePanel');
        if (!dialog || typeof dialog.showModal !== 'function') return;
        lastFocus = returnFocusTo || document.activeElement;
        startDraft();
        const search = $('langSearch');
        if (search) search.value = '';
        setTab(kind || 'transcription');
        dialog.showModal();
        if (search) search.focus();
    }

    function closePanel() {
        const dialog = $('languagePanel');
        if (dialog && dialog.open) dialog.close();
    }

    function showError(msg) {
        const err = $('langError');
        if (!err) return;
        err.textContent = msg;
        err.classList.remove('hidden');
    }

    async function save() {
        const body = {};
        for (let i = 0; i < KINDS.length; i++) {
            const k = KINDS[i];
            const all = eligible(k).map(function (l) { return l.code; });
            const chosen = all.filter(function (c) { return draft[k].has(c); });
            if (!chosen.length) {
                setTab(k);
                showError('Keep at least one ' + k + ' language.');
                return;
            }
            body[k] = chosen.length === all.length ? null : chosen;
        }
        const btn = $('langSave');
        if (btn) btn.disabled = true;
        try {
            const resp = await fetch('/api/settings/languages', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await resp.json().catch(function () { return {}; });
            if (!resp.ok) throw new Error(data.error || 'Could not save');
            prefs = normalizePrefs(data);
            renderTranscription(null, { notify: true });
            listeners.forEach(function (fn) { fn(); });
            closePanel();
            toast('success', 'Language lists saved');
        } catch (err) {
            showError(err.message);
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    function initPanel() {
        const dialog = $('languagePanel');
        if (!dialog) return;

        document.querySelectorAll('.lang-tab').forEach(function (tab) {
            tab.addEventListener('click', function () { setTab(tab.getAttribute('data-kind')); });
            tab.addEventListener('keydown', function (e) {
                if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
                e.preventDefault();
                const next = activeKind === 'transcription' ? 'translation' : 'transcription';
                setTab(next);
                const el = document.querySelector('.lang-tab[data-kind="' + next + '"]');
                if (el) el.focus();
            });
        });

        const list = $('langList');
        if (list) {
            list.addEventListener('change', function (e) {
                const box = e.target;
                if (!box || box.type !== 'checkbox') return;
                if (box.checked) draft[activeKind].add(box.value);
                else draft[activeKind].delete(box.value);
                updateCount();
            });
        }

        const search = $('langSearch');
        if (search) search.addEventListener('input', renderList);

        function bulk(on) {
            filteredEntries().forEach(function (l) {
                if (on) draft[activeKind].add(l.code);
                else draft[activeKind].delete(l.code);
            });
            renderList();
        }
        const all = $('langSelectAll');
        if (all) all.addEventListener('click', function () { bulk(true); });
        const none = $('langSelectNone');
        if (none) none.addEventListener('click', function () { bulk(false); });

        const cancel = $('langCancel');
        if (cancel) cancel.addEventListener('click', closePanel);
        const close = $('langClose');
        if (close) close.addEventListener('click', closePanel);
        const saveBtn = $('langSave');
        if (saveBtn) saveBtn.addEventListener('click', save);

        // Click on the backdrop (outside the inner box) closes, like Esc
        dialog.addEventListener('click', function (e) {
            if (e.target === dialog) closePanel();
        });
        dialog.addEventListener('close', function () {
            if (lastFocus && typeof lastFocus.focus === 'function') lastFocus.focus();
        });
    }

    // The dropdown's last entry opens the panel instead of being selected
    function initTranscriptionSelect() {
        const select = $('language');
        if (!select) return;
        let previous = select.value;
        select.addEventListener('focus', function () { previous = select.value; });
        select.addEventListener('change', function (e) {
            if (select.value === CUSTOMIZE) {
                e.stopImmediatePropagation();
                select.value = previous;
                openPanel('transcription', select);
                return;
            }
            previous = select.value;
            // A fallback chosen by renderTranscription is not the user's choice
            if (!rendering) preferred = select.value;
        });
    }

    renderTranscription('deepgram');
    initTranscriptionSelect();
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initPanel);
    } else {
        initPanel();
    }

    window.SubgenLanguages = {
        CUSTOMIZE: CUSTOMIZE,
        name: name,
        translationTargets: function () {
            return eligible('translation').filter(function (l) { return visible('translation', l.code); });
        },
        renderTranscription: renderTranscription,
        selectTranscription: selectTranscription,
        openPanel: openPanel,
        onPrefsChange: function (fn) { listeners.push(fn); },
    };
})();
