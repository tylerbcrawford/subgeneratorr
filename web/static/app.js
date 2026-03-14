// Subgeneratorr - Web UI Client

let selectedFiles = [];
let currentPath = '/media';
let currentFolder = '/media'; // Track which folder files are selected from
let currentBatchId = null;
let eventSource = null;
let pollInterval = null;
let pollCount = 0;
const MAX_POLL_COUNT = 200; // 200 polls × 3s = 10 minutes
let onlyFoldersWithVideos = true; // Default to filtering empty folders
let isInitialLoad = true; // Flag to prevent clearing keyterms on initial page load
let currentPathHasSubdirs = false; // True when current view has subdirectories (not a leaf file listing)
let searchDebounceTimer = null; // Debounce timer for API-backed search

/* ============================================
   INITIALIZATION
   ============================================ */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize theme
    initTheme();

    // Load config
    fetch('/api/config')
        .then(r => r.json())
        .then(config => {
            document.getElementById('language').value = config.default_language;
        })
        .catch(err => console.error('Failed to load config:', err));

    // Check if we should load saved settings — only if rememberSettings was checked
    const savedSettings = localStorage.getItem('deepgramSettings');
    let shouldLoadSaved = false;

    if (savedSettings !== null) {
        try {
            const parsed = JSON.parse(savedSettings);
            // Only restore settings if rememberSettings was explicitly enabled
            shouldLoadSaved = parsed.rememberSettings === true ||
                              (parsed.rememberSettings === undefined && savedSettings !== null);
        } catch (e) {
            shouldLoadSaved = false;
        }
    }

    let initialPath = '/media'; // Default path

    if (shouldLoadSaved) {
        // Load saved settings (including folder path and keyterms)
        const restoredPath = loadSavedSettings();
        if (restoredPath) {
            initialPath = restoredPath;
        }
    } else {
        // Apply default settings and clear keyterms
        applyDefaultSettings();
        clearKeytermField();
        // Clear any stale saved settings if rememberSettings wasn't enabled
        if (savedSettings !== null) {
            localStorage.removeItem('deepgramSettings');
        }
    }

    // Hide transcript options
    document.getElementById('transcriptOptions').style.display = 'none';

    // Setup event delegation for directory items
    document.getElementById('directoryList').addEventListener('click', function(e) {
        // Prevent clicks on file checkboxes and labels from triggering directory navigation
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'LABEL') {
            return;
        }

        // Find the directory-item
        let dirItem = null;
        if (e.target.classList && e.target.classList.contains('directory-item') && e.target.hasAttribute('data-path')) {
            dirItem = e.target;
        } else {
            dirItem = e.target.closest('.directory-item[data-path]');
        }

        if (dirItem) {
            const path = dirItem.getAttribute('data-path');
            if (path) {
                browseDirectories(path);
            }
        }
    });

    // Automatically load directory on page load
    console.log('Initial path for browseDirectories:', initialPath);
    browseDirectories(initialPath);

    // Setup keyboard shortcuts
    setupKeyboardShortcuts();
    
    // Setup LLM provider change handler
    const llmProvider = document.getElementById('llmProvider');
    if (llmProvider) {
        llmProvider.addEventListener('change', (e) => {
            const provider = e.target.value;
            const modelSelect = document.getElementById('llmModel');
            
            if (provider === 'anthropic') {
                modelSelect.innerHTML = `
                    <option value="claude-sonnet-4-6">Claude Sonnet 4.6 (Best Quality)</option>
                    <option value="claude-haiku-4-5">Claude Haiku 4.5 (Faster, Cheaper)</option>
                `;
            } else if (provider === 'openai') {
                modelSelect.innerHTML = `
                    <option value="gpt-4.1">GPT-4.1 (Best Quality)</option>
                    <option value="gpt-4.1-mini">GPT-4.1 Mini (Faster, Cheaper)</option>
                `;
            } else if (provider === 'google') {
                modelSelect.innerHTML = `
                    <option value="gemini-2.5-flash">Gemini 2.5 Flash (Free Tier)</option>
                `;
            }
            
            // Trigger change event to update API key status check and cost estimate
            modelSelect.dispatchEvent(new Event('change'));
        });

        // Initialize with correct models for default provider on page load
        llmProvider.dispatchEvent(new Event('change'));
    }
    
    // Setup Generate Keyterms button handler
    const generateBtn = document.getElementById('generateKeytermsBtn');
    if (generateBtn) {
        generateBtn.addEventListener('click', handleGenerateKeyterms);
    }

    // Update AI model display label and cost estimate when provider/model changes
    const modelSelect = document.getElementById('llmModel');
    if (modelSelect) {
        modelSelect.addEventListener('change', updateAiModelDisplay);
        modelSelect.addEventListener('change', updateKeytermCostEstimate);
    }
    if (llmProvider) {
        llmProvider.addEventListener('change', function() {
            // Delay to let model options update first
            setTimeout(updateAiModelDisplay, 0);
        });
    }

    // Check API key status on page load
    checkApiKeyStatus();

    // Initialize keyterm cost estimate
    updateKeytermCostEstimate();

    // Re-check API key status when provider changes
    if (llmProvider) {
        llmProvider.addEventListener('change', checkApiKeyStatus);
    }

    // Initialize keyterm availability state on page load
    updateKeytermAvailability();

    // Handle auto-clear files checkbox
    const autoClearFilesCheckbox = document.getElementById('autoClearFiles');
    if (autoClearFilesCheckbox) {
        autoClearFilesCheckbox.addEventListener('change', function() {
            localStorage.setItem('autoClearFiles', this.checked);
        });
    }

    // Update cost estimate when keyterms change
    const keytermsField = document.getElementById('keyTerms');
    if (keytermsField) {
        let isAutoLoading = false; // Flag to track programmatic changes
        let autoSaveTimeout = null; // Debounce timer for auto-save

        keytermsField.addEventListener('input', function(e) {
            if (selectedFiles.length > 0) {
                calculateEstimatesAuto();
            }
            // Update button state when user manually edits keyterms
            updateGenerateKeytermButtonState();

            // Only trigger auto-save and label reset if this is a manual edit (not programmatic)
            if (!isAutoLoading) {
                // Reset label ONLY if it shows auto-loaded or generated (not if it shows "saved")
                const keyTermsLabel = document.querySelector('label[for="keyTerms"]');
                if (keyTermsLabel && (keyTermsLabel.textContent.includes('auto-loaded') || keyTermsLabel.textContent.includes('generated')) && !keyTermsLabel.textContent.includes('saved')) {
                    console.log('Resetting keyterm label from:', keyTermsLabel.textContent);
                    resetKeytermLabel();
                }

                // Auto-save after user stops typing (debounced)
                if (autoSaveTimeout) {
                    clearTimeout(autoSaveTimeout);
                }

                console.log('Setting auto-save timer...');
                autoSaveTimeout = setTimeout(() => {
                    console.log('Auto-save timer triggered');
                    autoSaveKeyterms();
                }, 1500); // Wait 1.5 seconds after user stops typing
            }
        });

        // Store the flag on the field for access in other functions
        keytermsField._isAutoLoading = () => isAutoLoading;
        keytermsField._setAutoLoading = (value) => { isAutoLoading = value; };
    }
});

/* ============================================
   BREADCRUMB NAVIGATION
   ============================================ */

function updateBreadcrumb(path) {
    const breadcrumb = document.getElementById('breadcrumb');
    if (!breadcrumb) return;  // Exit early if breadcrumb element doesn't exist

    const parts = path.split('/').filter(p => p.length > 0);
    let html = '';
    
    // Start breadcrumb at /media (the MEDIA_ROOT)
    if (parts.length === 0 || path === '/media') {
        html = `<span class="breadcrumb-item current">media</span>`;
    } else {
        // Show "media" as clickable root
        html = `<button class="breadcrumb-item" onclick="navigateToPath('/media')" aria-label="Navigate to media root">media</button>`;
        
        // Build path starting after /media
        let currentPath = '/media';
        const mediaIndex = parts.indexOf('media');
        const relevantParts = mediaIndex >= 0 ? parts.slice(mediaIndex + 1) : parts;
        
        relevantParts.forEach((part, index) => {
            currentPath += '/' + part;
            const isLast = index === relevantParts.length - 1;
            
            html += `<span class="breadcrumb-separator">/</span>`;
            
            if (isLast) {
                html += `<span class="breadcrumb-item current">${part}</span>`;
            } else {
                const pathCopy = currentPath;
                html += `<button class="breadcrumb-item" onclick="navigateToPath('${pathCopy}')">${part}</button>`;
            }
        });
    }
    
    breadcrumb.innerHTML = html;
}

function navigateToPath(path) {
    // Ensure path is at least /media
    if (!path || path === '/' || path === '') {
        path = '/media';
    }
    browseDirectories(path);
}

/* ============================================
   DIRECTORY BROWSING
   ============================================ */

async function browseDirectories(path) {
    currentPath = path;
    const directoryList = document.getElementById('directoryList');
    const showAll = true;

    // Clear search filter when navigating
    const searchInput = document.getElementById('fileSearch');
    if (searchInput) {
        searchInput.value = '';
        const searchClear = document.getElementById('searchClear');
        if (searchClear) searchClear.style.display = 'none';
    }

    // Clear selection when navigating to a different folder (Group B: Folder Scope)
    if (path !== currentFolder && selectedFiles.length > 0) {
        selectedFiles = [];
        currentFolder = path;
        updateSelectionStatus();
    }

    // Clear keyterms when navigating directories (but not on initial load if settings are restored)
    if (!isInitialLoad) {
        clearKeytermField();
    } else {
        isInitialLoad = false; // Reset flag after first load
    }

    console.log('Browsing directory:', path);
    updateBreadcrumb(path);
    
    // Show skeleton loader
    let skeleton = document.getElementById('skeleton');
    if (!skeleton) {
        skeleton = document.createElement('div');
        skeleton.id = 'skeleton';
        skeleton.className = 'skeleton-loader';
        skeleton.innerHTML = '<div class="skeleton-item"></div><div class="skeleton-item"></div><div class="skeleton-item"></div>';
        directoryList.appendChild(skeleton);
    }
    skeleton.classList.remove('hidden');
    skeleton.style.display = 'block';
    directoryList.style.display = 'block';
    
    try {
        const response = await fetch(`/api/browse?path=${encodeURIComponent(path)}&show_all=${showAll}&only_folders_with_videos=${onlyFoldersWithVideos}`);
        console.log('API Response status:', response.status);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        console.log('API Response data:', data);
        
        // Hide skeleton loader
        skeleton = document.getElementById('skeleton');
        if (skeleton) {
            skeleton.classList.add('hidden');
            skeleton.style.display = 'none';
        }
        
        let html = '';
        
        // Add parent directory link if not at root
        if (data.parent_path) {
            html += `
                <button class="browser-item directory-item" data-path="${data.parent_path.replace(/"/g, '&quot;')}">
                    <span class="item-icon">↑</span>
                    <span class="item-name">Go to parent directory</span>
                </button>
            `;
        }
        
        // Add subdirectories
        if (data.directories.length > 0) {
            html += '<div class="browser-section">';
            data.directories.forEach(dir => {
                html += `
                    <button class="browser-item directory-item" data-path="${dir.path.replace(/"/g, '&quot;')}" data-video-count="${dir.video_count}">
                        <span class="item-icon">📁</span>
                        <span class="item-name">${dir.name}</span>
                        <span class="item-action">→</span>
                    </button>
                `;
            });
            html += '</div>';
        }
        
        // Update folder count display
        const folderCount = document.getElementById('folderCount');
        if (folderCount) {
            const folderText = data.directories.length === 1 ? 'folder' : 'folders';
            folderCount.textContent = `${data.directories.length} ${folderText}`;
        }
        
        // Add video files with checkboxes
        if (data.files.length > 0) {
            html += '<h3 class="section-header">Videos</h3>';
            html += '<div class="browser-section">';
            data.files.forEach((file, index) => {
                const isSelected = selectedFiles.includes(file.path);
                const statusIcon = getStatusIcon(file);
                const escapedPath = file.path.replace(/"/g, '&quot;');
                html += `
                    <label class="browser-item browser-file ${isSelected ? 'selected' : ''}" data-has-subtitles="${file.has_subtitles ? 'true' : 'false'}">
                        <input type="checkbox" class="item-checkbox" id="file-${index}" value="${escapedPath}"
                               ${isSelected ? 'checked' : ''}
                               onchange="toggleFileSelection(this.value)">
                        ${statusIcon}
                        <span class="item-name">${file.name}</span>
                    </label>
                `;
            });
            html += '</div>';
        }
        
        if (data.directories.length === 0 && data.files.length === 0) {
            html += `
                <div class="empty-state">
                    <div class="empty-icon">
                        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
                        </svg>
                    </div>
                    <h3 class="empty-title">No videos found</h3>
                    <p class="empty-message">This folder doesn't contain any video files</p>
                </div>
            `;
        }
        
        console.log('Setting innerHTML with', html.length, 'characters');
        directoryList.innerHTML = html;
        console.log('Updated directory list, now has', directoryList.children.length, 'children');
        currentPathHasSubdirs = data.directories.length > 0;

        updateSelectionStatus();
        
    } catch (error) {
        console.error('Browse error:', error);
        const skeletonEl = document.getElementById('skeleton');
        if (skeletonEl) {
            skeletonEl.classList.add('hidden');
            skeletonEl.style.display = 'none';
        }
        directoryList.innerHTML = `<div style="color: var(--color-red); text-align: center; padding: var(--space-l);">Error: ${error.message}</div>`;
        showToast('error', `Failed to browse directory: ${error.message}`);
    }
}

function getStatusIcon(file) {
    if (file.has_subtitles) {
        return '<span class="item-status" data-status="complete" title="Has subtitles" aria-label="Has subtitles"></span>';
    } else {
        return '<span class="item-status" data-status="missing" title="Missing subtitles" aria-label="Missing subtitles"></span>';
    }
}

/* ============================================
   FILE SELECTION
   ============================================ */

function toggleFileSelection(filePath) {
    const index = selectedFiles.indexOf(filePath);
    if (index > -1) {
        selectedFiles.splice(index, 1);
    } else {
        // Group B: Set current folder when first file is selected
        if (selectedFiles.length === 0) {
            currentFolder = currentPath;
        }
        selectedFiles.push(filePath);
    }
    updateSelectionStatus();
    
    // Update visual selection
    document.querySelectorAll('.browser-file').forEach(item => {
        const checkbox = item.querySelector('input[type="checkbox"]');
        if (checkbox && checkbox.value === filePath) {
            if (index === -1) {
                item.classList.add('selected');
            } else {
                item.classList.remove('selected');
            }
        }
    });
    
    // Calculate estimates and handle keyterms
    if (selectedFiles.length > 0) {
        calculateEstimatesAuto();
        // Auto-load keyterms for the first selected file
        loadKeytermsForSelection();
        // Update keyterm cost estimate
        updateKeytermCostEstimate();
    } else {
        // Clear keyterms when no files are selected
        clearKeytermField();
        const costPrimary = document.getElementById('costPrimary');
        const costSecondary = document.getElementById('costSecondary');
        costPrimary.textContent = '0 files selected';
        costSecondary.textContent = 'Select videos to see estimates';
        // Clear keyterm cost estimate
        updateKeytermCostEstimate();
    }
}

/* ============================================
   FOLDER FILTERING
   ============================================ */

function toggleFolderFilter() {
    const checkbox = document.getElementById('onlyFoldersWithVideos');
    onlyFoldersWithVideos = checkbox.checked;

    // Reload current directory with new filter
    browseDirectories(currentPath);

    const filterText = onlyFoldersWithVideos ? 'Showing folders with media only' : 'Showing all folders';
    showToast('info', filterText);
}

/* ============================================
   FILE SEARCH / FILTER
   ============================================ */

function filterBrowserItems(query) {
    const searchClear = document.getElementById('searchClear');
    searchClear.style.display = query ? 'block' : 'none';

    // At a leaf directory (files in DOM, no subdirs): filter in place
    if (!currentPathHasSubdirs) {
        _filterBrowserItemsDOM(query);
        return;
    }

    // At a parent directory: use API search with debounce
    if (searchDebounceTimer) clearTimeout(searchDebounceTimer);

    if (!query) {
        // Query cleared — restore normal directory listing
        browseDirectories(currentPath);
        return;
    }
    if (query.trim().length < 2) {
        // Too short to search yet — wait for more input without modifying the view
        return;
    }

    searchDebounceTimer = setTimeout(() => _searchBrowserAPI(query.trim()), 300);
}

function _filterBrowserItemsDOM(query) {
    const normalizedQuery = query.toLowerCase().trim();
    const items = document.querySelectorAll('#directoryList .browser-item');
    items.forEach(item => {
        if (item.querySelector('.item-name')?.textContent === 'Go to parent directory') return;
        const name = item.querySelector('.item-name')?.textContent?.toLowerCase() || '';
        item.style.display = name.includes(normalizedQuery) ? '' : 'none';
    });
    document.querySelectorAll('#directoryList .section-header').forEach(header => {
        const section = header.nextElementSibling;
        if (section?.classList.contains('browser-section')) {
            const visibleItems = section.querySelectorAll('.browser-item:not([style*="display: none"])');
            header.style.display = visibleItems.length > 0 ? '' : 'none';
            section.style.display = visibleItems.length > 0 ? '' : 'none';
        }
    });
}

async function _searchBrowserAPI(query) {
    const directoryList = document.getElementById('directoryList');
    directoryList.innerHTML = '<div style="text-align:center; padding: var(--space-l); color: var(--text-secondary);">Searching...</div>';

    try {
        const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();

        if (data.directories.length === 0 && data.files.length === 0) {
            directoryList.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">
                        <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="11" cy="11" r="8"></circle>
                            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                        </svg>
                    </div>
                    <h3 class="empty-title">No results</h3>
                    <p class="empty-message">Nothing matching "${query}"</p>
                </div>`;
            return;
        }

        let html = '';
        if (data.directories.length > 0) {
            html += '<div class="browser-section">';
            data.directories.forEach(dir => {
                const contextHtml = dir.context
                    ? `<span class="item-meta" style="opacity:0.5; font-size:0.8em; margin-left:auto; padding-right:var(--space-s)">${dir.context}/</span>`
                    : '';
                html += `
                    <button class="browser-item directory-item" data-path="${dir.path.replace(/"/g, '&quot;')}">
                        <span class="item-icon">📁</span>
                        <span class="item-name">${dir.name}</span>
                        ${contextHtml}
                        <span class="item-action">→</span>
                    </button>`;
            });
            html += '</div>';
        }

        if (data.files.length > 0) {
            html += '<h3 class="section-header">Videos</h3><div class="browser-section">';
            data.files.forEach((file, index) => {
                const isSelected = selectedFiles.includes(file.path);
                const statusIcon = getStatusIcon(file);
                html += `
                    <label class="browser-item browser-file ${isSelected ? 'selected' : ''}" data-has-subtitles="${file.has_subtitles}">
                        <input type="checkbox" class="item-checkbox" id="search-file-${index}" value="${file.path.replace(/"/g, '&quot;')}"
                               ${isSelected ? 'checked' : ''}
                               onchange="toggleFileSelection(this.value)">
                        ${statusIcon}
                        <span class="item-name">${file.name}</span>
                    </label>`;
            });
            html += '</div>';
        }

        directoryList.innerHTML = html;
        updateSelectionStatus();
    } catch (err) {
        console.error('Search error:', err);
        directoryList.innerHTML = `<div style="color: var(--color-red); text-align:center; padding: var(--space-l);">Search failed: ${err.message}</div>`;
    }
}

function clearFileSearch() {
    const searchInput = document.getElementById('fileSearch');
    searchInput.value = '';
    filterBrowserItems('');
    searchInput.focus();
}

/* ============================================
   SETTINGS PERSISTENCE
   ============================================ */

function toggleRememberSettings() {
    const rememberCheckbox = document.getElementById('rememberSettings');

    if (rememberCheckbox.checked) {
        // Save current settings to localStorage
        saveCurrentSettings();
        showToast('info', 'Settings will be remembered');
    } else {
        // Clear saved settings from localStorage
        localStorage.removeItem('deepgramSettings');
        // Clear keyterms field immediately
        clearKeytermField();
        // Navigate back to /media directory
        browseDirectories('/media');
        showToast('info', 'Settings cleared - using defaults');
    }
}

function applyDefaultSettings() {
    // Reset language dropdown to default
    const languageSelect = document.getElementById('language');
    if (languageSelect) languageSelect.value = 'en';

    // Reset checkboxes that should be unchecked by default
    const uncheckIds = [
        'enableTranscript', 'saveRawJson', 'numerals', 'fillerWords',
        'diarization', 'dictation', 'redact', 'findReplace', 'multichannel',
        'sentiment', 'summarize', 'topics', 'intents', 'detectEntities', 'enableSearch'
    ];
    uncheckIds.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.checked = false;
    });

    // Set checkboxes that should be checked by default (best practices for subtitles)
    const checkIds = ['measurements', 'utterances', 'paragraphs', 'onlyFoldersWithVideos'];
    checkIds.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.checked = true;
    });

    // Reset model radio to General (nova-3)
    const modelDefault = document.querySelector('input[name="model"][value="nova-3"]');
    if (modelDefault) modelDefault.checked = true;

    // Reset profanity filter radio buttons to default (off)
    const profanityFilterOff = document.querySelector('input[name="profanityFilter"][value="off"]');
    if (profanityFilterOff) profanityFilterOff.checked = true;

    // Reset slider to default
    const uttSplit = document.getElementById('uttSplit');
    if (uttSplit) {
        uttSplit.value = '0.8';
        const display = document.getElementById('uttSplitValue');
        if (display) display.textContent = '0.8s';
    }

    // Clear text inputs
    const clearIds = ['replaceTerms', 'searchTerms', 'requestTag'];
    clearIds.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });

    // Uncheck remember settings
    const rememberCheckbox = document.getElementById('rememberSettings');
    if (rememberCheckbox) rememberCheckbox.checked = false;
}

function saveCurrentSettings() {
    const settings = {
        language: document.getElementById('language')?.value,
        model: document.querySelector('input[name="model"]:checked')?.value,
        enableTranscript: document.getElementById('enableTranscript')?.checked,
        numerals: document.getElementById('numerals')?.checked,
        measurements: document.getElementById('measurements')?.checked,
        fillerWords: document.getElementById('fillerWords')?.checked,
        profanityFilter: document.querySelector('input[name="profanityFilter"]:checked')?.value,
        saveRawJson: document.getElementById('saveRawJson')?.checked,
        diarization: document.getElementById('diarization')?.checked,
        utterances: document.getElementById('utterances')?.checked,
        paragraphs: document.getElementById('paragraphs')?.checked,
        onlyFoldersWithVideos: document.getElementById('onlyFoldersWithVideos')?.checked,
        autoClearFiles: document.getElementById('autoClearFiles')?.checked,
        rememberSettings: document.getElementById('rememberSettings')?.checked,
        currentPath: currentPath,
        keyterms: document.getElementById('keyTerms')?.value.trim() || '',
        // New Tier 1 features
        dictation: document.getElementById('dictation')?.checked,
        redact: document.getElementById('redact')?.checked,
        redactPci: document.getElementById('redactPci')?.checked,
        redactPii: document.getElementById('redactPii')?.checked,
        redactNumbers: document.getElementById('redactNumbers')?.checked,
        findReplace: document.getElementById('findReplace')?.checked,
        replaceTerms: document.getElementById('replaceTerms')?.value || '',
        multichannel: document.getElementById('multichannel')?.checked,
        uttSplit: document.getElementById('uttSplit')?.value || '0.8',
        // Tier 2: Audio Intelligence
        sentiment: document.getElementById('sentiment')?.checked,
        summarize: document.getElementById('summarize')?.checked,
        topics: document.getElementById('topics')?.checked,
        intents: document.getElementById('intents')?.checked,
        detectEntities: document.getElementById('detectEntities')?.checked,
        enableSearch: document.getElementById('enableSearch')?.checked,
        searchTerms: document.getElementById('searchTerms')?.value || '',
        // Tier 3: Operational
        requestTag: document.getElementById('requestTag')?.value || ''
    };

    console.log('Saving settings with currentPath:', currentPath);
    localStorage.setItem('deepgramSettings', JSON.stringify(settings));
}

function loadSavedSettings() {
    const rememberCheckbox = document.getElementById('rememberSettings');
    const savedSettings = localStorage.getItem('deepgramSettings');

    if (savedSettings) {
        try {
            const settings = JSON.parse(savedSettings);

            // Apply saved settings
            if (settings.language) document.getElementById('language').value = settings.language;
            if (settings.model) {
                const modelRadio = document.querySelector(`input[name="model"][value="${settings.model}"]`);
                if (modelRadio) modelRadio.checked = true;
            }
            if (settings.enableTranscript !== undefined) document.getElementById('enableTranscript').checked = settings.enableTranscript;
            if (settings.numerals !== undefined) document.getElementById('numerals').checked = settings.numerals;
            if (settings.measurements !== undefined) document.getElementById('measurements').checked = settings.measurements;
            if (settings.fillerWords !== undefined) document.getElementById('fillerWords').checked = settings.fillerWords;
            if (settings.saveRawJson !== undefined) document.getElementById('saveRawJson').checked = settings.saveRawJson;
            if (settings.diarization !== undefined) document.getElementById('diarization').checked = settings.diarization;
            if (settings.utterances !== undefined) document.getElementById('utterances').checked = settings.utterances;
            if (settings.paragraphs !== undefined) document.getElementById('paragraphs').checked = settings.paragraphs;

            // Tier 1 features
            if (settings.dictation !== undefined) {
                const el = document.getElementById('dictation');
                if (el) el.checked = settings.dictation;
            }
            if (settings.redact !== undefined) {
                const el = document.getElementById('redact');
                if (el) { el.checked = settings.redact; toggleRedactOptions(); }
            }
            if (settings.redactPci !== undefined) {
                const el = document.getElementById('redactPci');
                if (el) el.checked = settings.redactPci;
            }
            if (settings.redactPii !== undefined) {
                const el = document.getElementById('redactPii');
                if (el) el.checked = settings.redactPii;
            }
            if (settings.redactNumbers !== undefined) {
                const el = document.getElementById('redactNumbers');
                if (el) el.checked = settings.redactNumbers;
            }
            if (settings.findReplace !== undefined) {
                const el = document.getElementById('findReplace');
                if (el) { el.checked = settings.findReplace; toggleReplaceOptions(); }
            }
            if (settings.replaceTerms) {
                const el = document.getElementById('replaceTerms');
                if (el) el.value = settings.replaceTerms;
            }
            if (settings.multichannel !== undefined) {
                const el = document.getElementById('multichannel');
                if (el) el.checked = settings.multichannel;
            }
            if (settings.uttSplit) {
                const el = document.getElementById('uttSplit');
                if (el) {
                    el.value = settings.uttSplit;
                    const display = document.getElementById('uttSplitValue');
                    if (display) display.textContent = parseFloat(settings.uttSplit).toFixed(1) + 's';
                }
            }

            // Tier 2: Audio Intelligence
            if (settings.sentiment !== undefined) {
                const el = document.getElementById('sentiment');
                if (el) el.checked = settings.sentiment;
            }
            if (settings.summarize !== undefined) {
                const el = document.getElementById('summarize');
                if (el) el.checked = settings.summarize;
            }
            if (settings.topics !== undefined) {
                const el = document.getElementById('topics');
                if (el) el.checked = settings.topics;
            }
            if (settings.intents !== undefined) {
                const el = document.getElementById('intents');
                if (el) el.checked = settings.intents;
            }
            if (settings.detectEntities !== undefined) {
                const el = document.getElementById('detectEntities');
                if (el) el.checked = settings.detectEntities;
            }
            if (settings.enableSearch !== undefined) {
                const el = document.getElementById('enableSearch');
                if (el) { el.checked = settings.enableSearch; toggleSearchTerms(); }
            }
            if (settings.searchTerms) {
                const el = document.getElementById('searchTerms');
                if (el) el.value = settings.searchTerms;
            }

            // Tier 3: Operational
            if (settings.requestTag) {
                const el = document.getElementById('requestTag');
                if (el) el.value = settings.requestTag;
            }

            // Auto-lock JSON if any intelligence feature is enabled
            updateIntelligenceJsonLock();
            if (settings.onlyFoldersWithVideos !== undefined) {
                document.getElementById('onlyFoldersWithVideos').checked = settings.onlyFoldersWithVideos;
                onlyFoldersWithVideos = settings.onlyFoldersWithVideos;
            }
            if (settings.autoClearFiles !== undefined) {
                document.getElementById('autoClearFiles').checked = settings.autoClearFiles;
                localStorage.setItem('autoClearFiles', settings.autoClearFiles);
            }

            if (settings.profanityFilter) {
                const radio = document.querySelector(`input[name="profanityFilter"][value="${settings.profanityFilter}"]`);
                if (radio) radio.checked = true;
            }

            // Restore folder path (will be returned and used for initial navigation)
            let restoredPath = null;
            if (settings.currentPath) {
                currentPath = settings.currentPath;
                restoredPath = settings.currentPath;
                console.log('Restored currentPath from settings:', currentPath);
            }

            // Restore keyterms
            if (settings.keyterms) {
                const keytermsInput = document.getElementById('keyTerms');
                if (keytermsInput) {
                    // Set flag to prevent input listener from triggering auto-save
                    if (keytermsInput._setAutoLoading) {
                        keytermsInput._setAutoLoading(true);
                    }

                    keytermsInput.value = settings.keyterms;

                    // Reset flag after a brief delay
                    setTimeout(() => {
                        if (keytermsInput._setAutoLoading) {
                            keytermsInput._setAutoLoading(false);
                        }
                    }, 100);

                    // Update label to show restored state
                    const keytermCount = settings.keyterms.split(',').filter(k => k.trim().length > 0).length;
                    const keyTermsLabel = document.querySelector('label[for="keyTerms"]');
                    if (keyTermsLabel && keytermCount > 0) {
                        keyTermsLabel.textContent = `KEYTERMS (${keytermCount} restored from last session)`;
                        keyTermsLabel.style.color = 'var(--color-blue)';
                        keyTermsLabel.setAttribute('data-original-text', 'KEYTERMS');
                    }
                }
            }

            // Check the remember settings checkbox
            if (rememberCheckbox) rememberCheckbox.checked = true;

            // Return the restored path so it can be used for initial navigation
            return restoredPath;
        } catch (e) {
            console.error('Error loading saved settings:', e);
            localStorage.removeItem('deepgramSettings');
            applyDefaultSettings();
            return null;
        }
    }
    return null;
}

/* ============================================
   KEYTERMS AUTO-LOADING
   ============================================ */

function resetKeytermLabel() {
    const keyTermsLabel = document.querySelector('label[for="keyTerms"]');
    if (keyTermsLabel) {
        const originalText = keyTermsLabel.getAttribute('data-original-text') || 'KEYTERMS';
        keyTermsLabel.textContent = originalText;
        keyTermsLabel.style.color = '';
    }
}

function clearKeytermField() {
    const keytermsInput = document.getElementById('keyTerms');
    if (keytermsInput) {
        keytermsInput.value = '';
    }
    resetKeytermLabel();
}

async function autoSaveKeyterms() {
    // Only auto-save if we have a selected file
    if (selectedFiles.length === 0) {
        return;
    }

    const keytermsInput = document.getElementById('keyTerms');
    const keyterms = keytermsInput?.value.trim();

    if (!keyterms) {
        return; // Don't save empty keyterms
    }

    const firstFile = selectedFiles[0];

    try {
        const response = await fetch('/api/keyterms/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                video_path: firstFile,
                keyterms: keyterms
            })
        });

        if (response.ok) {
            const data = await response.json();
            console.log(`Auto-saved ${data.keyterms_count} keyterms`);

            // Update label to show it was saved
            const keyTermsLabel = document.querySelector('label[for="keyTerms"]');
            if (keyTermsLabel) {
                keyTermsLabel.textContent = `KEYTERMS (${data.keyterms_count} saved)`;
                keyTermsLabel.style.color = 'var(--color-green)';
                keyTermsLabel.setAttribute('data-original-text', 'KEYTERMS');
            }
        } else {
            const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
            console.error('Failed to auto-save keyterms:', response.status, errorData);
        }
    } catch (error) {
        console.error('Error auto-saving keyterms:', error);
    }
}

async function loadKeytermsForSelection() {
    // Only load if we have selected files
    if (selectedFiles.length === 0) {
        return;
    }

    // Clear existing keyterms first
    clearKeytermField();

    // Use the first selected file to determine which keyterms to load
    const firstFile = selectedFiles[0];

    try {
        const response = await fetch(`/api/keyterms/load?video_path=${encodeURIComponent(firstFile)}`);

        if (!response.ok) {
            console.log('No keyterms found for this video');
            updateGenerateKeytermButtonState();
            return;
        }

        const data = await response.json();

        if (data.keyterms && data.keyterms.length > 0) {
            // Populate the keyterms text box
            const keyTermsInput = document.getElementById('keyTerms');
            if (keyTermsInput) {
                // Set flag to prevent input listener from resetting label
                if (keyTermsInput._setAutoLoading) {
                    keyTermsInput._setAutoLoading(true);
                }

                // Join keyterms with commas
                keyTermsInput.value = data.keyterms.join(', ');

                // Reset flag after a brief delay
                setTimeout(() => {
                    if (keyTermsInput._setAutoLoading) {
                        keyTermsInput._setAutoLoading(false);
                    }
                }, 100);

                // Show a subtle notification
                console.log(`Auto-loaded ${data.count} keyterms from CSV`);

                // Show persistent indicator that keyterms were auto-loaded
                const keyTermsLabel = document.querySelector('label[for="keyTerms"]');
                if (keyTermsLabel) {
                    keyTermsLabel.textContent = `KEYTERMS (${data.count} auto-loaded)`;
                    keyTermsLabel.style.color = 'var(--color-green)';
                    // Store the original text for later reset
                    keyTermsLabel.setAttribute('data-original-text', 'KEYTERMS');
                }
            }
        }

        // Update button state after loading keyterms
        updateGenerateKeytermButtonState();
    } catch (error) {
        console.error('Failed to load keyterms:', error);
        // Silently fail - not critical
        updateGenerateKeytermButtonState();
    }
}

/* ============================================
   THEME MANAGEMENT
   ============================================ */

function initTheme() {
    const savedTheme = localStorage.getItem('theme') || 'dark';
    document.documentElement.setAttribute('data-theme', savedTheme);
    
    document.querySelectorAll('.theme-icon').forEach(icon => {
        icon.style.display = icon.classList.contains(`theme-icon-${savedTheme}`) ? 'block' : 'none';
    });
}

function toggleTheme() {
    const html = document.documentElement;
    const currentTheme = html.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    
    html.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    
    // Update icon visibility
    document.querySelectorAll('.theme-icon').forEach(icon => {
        icon.style.display = icon.classList.contains(`theme-icon-${newTheme}`) ? 'block' : 'none';
    });
    
    // Announce to screen readers
    const message = `${newTheme.charAt(0).toUpperCase() + newTheme.slice(1)} mode enabled`;
    announceToScreenReader(message);
    
    showToast('info', `Switched to ${newTheme} mode`);
}

/* ============================================
   MULTI-LANGUAGE TOGGLE HANDLER
   ============================================ */

/* ============================================
   KEYTERM AVAILABILITY (LANGUAGE CHECK)
   ============================================ */

function updateKeytermAvailability() {
    const languageSelect = document.getElementById('language');
    const keytermsInput = document.getElementById('keyTerms');
    const generateBtn = document.getElementById('generateKeytermsBtn');
    const keytermsSection = document.querySelector('.config-section');

    if (!languageSelect || !keytermsInput) return;

    const selectedLanguage = languageSelect.value;
    const isMultiLanguage = selectedLanguage === 'multi';

    // Keyterms disabled only for multi-language (auto-detect keeps them enabled — audio might be English)
    const keytermAvailable = !isMultiLanguage;

    // Disable/enable keyterms elements with visual feedback
    keytermsInput.disabled = !keytermAvailable;
    keytermsInput.style.opacity = keytermAvailable ? '1' : '0.5';
    if (generateBtn) {
        generateBtn.disabled = !keytermAvailable;
        generateBtn.style.opacity = keytermAvailable ? '1' : '0.5';
    }

    // Show warning toast when switching to multi-language with existing keyterms
    if (isMultiLanguage && keytermsInput.value.trim()) {
        showToast('warning', 'Keyterm prompting is not available with multi-language mode');
    }

    // Update button state if keyterms are available
    if (keytermAvailable) {
        updateGenerateKeytermButtonState();
    }
}

/* ============================================
   NEW FEATURE TOGGLES
   ============================================ */

function toggleRedactOptions() {
    const redact = document.getElementById('redact');
    const options = document.getElementById('redactOptions');
    if (redact && options) {
        options.classList.toggle('hidden', !redact.checked);
        // Default PII checked when first enabling redaction
        if (redact.checked) {
            const pii = document.getElementById('redactPii');
            if (pii && !document.getElementById('redactPci')?.checked && !pii.checked && !document.getElementById('redactNumbers')?.checked) {
                pii.checked = true;
            }
        }
    }
}

function toggleReplaceOptions() {
    const findReplace = document.getElementById('findReplace');
    const options = document.getElementById('replaceOptions');
    if (findReplace && options) {
        options.classList.toggle('hidden', !findReplace.checked);
    }
}

function toggleUttSplit() {
    const utterances = document.getElementById('utterances');
    const options = document.getElementById('uttSplitOptions');
    if (utterances && options) {
        options.classList.toggle('hidden', !utterances.checked);
    }
}

function toggleSearchTerms() {
    const enableSearch = document.getElementById('enableSearch');
    const options = document.getElementById('searchTermsOptions');
    if (enableSearch && options) {
        options.classList.toggle('hidden', !enableSearch.checked);
    }
    updateIntelligenceJsonLock();
}

/* ============================================
   AUDIO INTELLIGENCE — LANGUAGE GATING & JSON LOCK
   ============================================ */

function updateIntelligenceAvailability() {
    const languageSelect = document.getElementById('language');
    const section = document.getElementById('intelligenceSection');
    if (!languageSelect || !section) return;

    const lang = languageSelect.value;
    // Intelligence available for English variants and auto-detect (might be English)
    const isEnglishLike = lang === 'en' || lang.startsWith('en-') || lang === 'auto';

    if (isEnglishLike) {
        section.classList.remove('intelligence-disabled');
    } else {
        section.classList.add('intelligence-disabled');
        // Uncheck all intelligence checkboxes when disabled
        ['sentiment', 'summarize', 'topics', 'intents', 'detectEntities', 'enableSearch'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.checked = false;
        });
        // Hide search terms
        const searchOpts = document.getElementById('searchTermsOptions');
        if (searchOpts) searchOpts.classList.add('hidden');
    }

    updateIntelligenceJsonLock();
}

function updateIntelligenceJsonLock() {
    const intelligenceIds = ['sentiment', 'summarize', 'topics', 'intents', 'detectEntities', 'enableSearch'];
    const anyIntelligence = intelligenceIds.some(id => document.getElementById(id)?.checked);
    const saveRawJson = document.getElementById('saveRawJson');

    if (!saveRawJson) return;

    if (anyIntelligence) {
        // Auto-enable and lock Raw JSON
        if (!saveRawJson.checked) {
            saveRawJson.checked = true;
            showToast('info', 'Raw JSON auto-enabled for intelligence output');
        }
        saveRawJson.disabled = true;
        saveRawJson.closest('.checkbox-label').style.opacity = '0.6';
    } else {
        // Unlock for manual toggle
        saveRawJson.disabled = false;
        saveRawJson.closest('.checkbox-label').style.opacity = '1';
    }
}

// Attach intelligence JSON lock to all intelligence checkboxes
document.addEventListener('DOMContentLoaded', function() {
    ['sentiment', 'summarize', 'topics', 'intents', 'detectEntities'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('change', updateIntelligenceJsonLock);
    });

    // Initialize utterance split visibility
    toggleUttSplit();

    // Initialize intelligence availability
    updateIntelligenceAvailability();
});

/* ============================================
   KEYBOARD SHORTCUTS
   ============================================ */

function setupKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        // Ctrl/Cmd + A: Select All
        if ((e.ctrlKey || e.metaKey) && e.key === 'a' && !e.target.matches('input, textarea, select')) {
            e.preventDefault();
            selectAll();
        }
        
        // Escape: Clear selection
        if (e.key === 'Escape') {
            selectNone();
        }
        
        // Enter: Start transcription if files selected
        if (e.key === 'Enter' && selectedFiles.length > 0 && !e.target.matches('input, textarea, select')) {
            submitBatch();
        }
        
        // Ctrl/Cmd + T: Toggle theme
        if ((e.ctrlKey || e.metaKey) && e.key === 't') {
            e.preventDefault();
            toggleTheme();
        }
    });
}

/* ============================================
   TOAST NOTIFICATIONS
   ============================================ */

// Track the generating toast so we can remove it when done
let generatingToast = null;

function showToast(type, message, options = {}) {
    // Remove any existing toasts
    document.querySelectorAll('.toast').forEach(t => t.remove());

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    const dismiss = () => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    };

    // Errors get a close button; all toasts are click-to-dismiss
    const closeBtn = type === 'error' ? '<button class="toast-close" aria-label="Dismiss">&times;</button>' : '';
    toast.innerHTML = `<span class="toast-message">${message}</span>${closeBtn}`;
    toast.addEventListener('click', dismiss);

    document.body.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('show');
    }, 10);

    // Auto-dismiss: 3s for info/success, 8s for errors
    if (!options.persist) {
        const delay = type === 'error' ? 8000 : 3000;
        setTimeout(dismiss, delay);
    }

    return toast;
}

// Overwrite dialog — returns Promise resolving to 'overwrite', 'skip', or 'cancel'
function showOverwriteDialog(filesWithSubtitles, totalFiles) {
    return new Promise(resolve => {
        const allHaveSubs = filesWithSubtitles === totalFiles;
        const fileText = filesWithSubtitles === 1 ? 'file already has' : 'files already have';

        const overlay = document.createElement('div');
        overlay.className = 'dialog-overlay';
        overlay.innerHTML = `
            <div class="dialog-box">
                <div class="dialog-title">Existing Subtitles</div>
                <div class="dialog-message">
                    ${filesWithSubtitles} of ${totalFiles} selected ${fileText} subtitles.
                </div>
                <div class="dialog-actions">
                    <button class="btn-primary" data-action="overwrite">Overwrite All</button>
                    ${!allHaveSubs ? '<button class="btn-secondary" data-action="skip">Skip Existing</button>' : ''}
                    <button class="btn-link" data-action="cancel">Cancel</button>
                </div>
            </div>
        `;

        function cleanup(action) {
            overlay.classList.remove('show');
            setTimeout(() => overlay.remove(), 200);
            document.removeEventListener('keydown', onKey);
            resolve(action);
        }

        function onKey(e) {
            if (e.key === 'Escape') cleanup('cancel');
        }

        // Backdrop click dismisses
        overlay.addEventListener('click', e => {
            if (e.target === overlay) cleanup('cancel');
        });

        // Button clicks
        overlay.querySelectorAll('[data-action]').forEach(btn => {
            btn.addEventListener('click', () => cleanup(btn.dataset.action));
        });

        document.addEventListener('keydown', onKey);
        document.body.appendChild(overlay);

        // Trigger transition
        requestAnimationFrame(() => overlay.classList.add('show'));
    });
}

// Update unified status display
function updateUnifiedStatus(text, showProgress = false, progressPercent = 0) {
    const statusText = document.getElementById('statusText');
    const statusProgress = document.getElementById('statusProgress');
    const progressFill = document.getElementById('progressFill');
    const progressLabel = document.getElementById('progressLabel');

    if (statusText) statusText.textContent = text;

    if (showProgress) {
        if (statusProgress) statusProgress.style.display = 'flex';
        if (progressFill) progressFill.style.width = progressPercent + '%';
        if (progressLabel) progressLabel.textContent = Math.round(progressPercent) + '%';
    } else {
        if (statusProgress) statusProgress.style.display = 'none';
    }
}

/* ============================================
   SCREEN READER SUPPORT
   ============================================ */

function announceToScreenReader(message) {
    const announcer = document.getElementById('status-announcer');
    announcer.textContent = message;
    
    setTimeout(() => {
        announcer.textContent = '';
    }, 1000);
}

/* ============================================
   UTILITY FUNCTIONS
   ============================================ */

function showStatus(elementId, message, type = 'info') {
    const el = document.getElementById(elementId);
    el.textContent = message;
    el.className = `status ${type}`;
    el.style.display = 'block';
}

function toggleTranscriptOptions() {
    const checkbox = document.getElementById('enableTranscript');
    const options = document.getElementById('transcriptOptions');
    options.style.display = checkbox.checked ? 'block' : 'none';
}

function toggleAdvancedOptions() {
    const advancedOptions = document.getElementById('advancedOptions');
    const toggleBtn = document.getElementById('advancedToggle');

    if (advancedOptions.classList.contains('hidden')) {
        advancedOptions.classList.remove('hidden');
        toggleBtn.textContent = 'Transcription Settings ▲';
    } else {
        advancedOptions.classList.add('hidden');
        toggleBtn.textContent = 'Transcription Settings ▼';
    }
}

function toggleGearPopover() {
    const popover = document.getElementById('gearPopover');
    popover.classList.toggle('hidden');
}

function toggleAiConfig() {
    const panel = document.getElementById('aiConfigPanel');
    panel.classList.toggle('hidden');
}

function updateAiModelDisplay() {
    const modelSelect = document.getElementById('llmModel');
    const display = document.getElementById('aiModelDisplay');
    if (modelSelect && display) {
        const selectedOption = modelSelect.options[modelSelect.selectedIndex];
        // Extract just the model name (before the parenthetical)
        const text = selectedOption.text.split(' (')[0];
        display.textContent = text;
    }
}

// Close popovers on outside click
document.addEventListener('click', function(e) {
    // Gear popover
    const popover = document.getElementById('gearPopover');
    const gearBtn = document.querySelector('.gear-btn');
    if (popover && !popover.classList.contains('hidden') &&
        !popover.contains(e.target) && !gearBtn.contains(e.target)) {
        popover.classList.add('hidden');
    }

    // AI config panel
    const aiPanel = document.getElementById('aiConfigPanel');
    const aiToggle = document.querySelector('.ai-config-toggle');
    if (aiPanel && !aiPanel.classList.contains('hidden') &&
        !aiPanel.contains(e.target) && aiToggle && !aiToggle.contains(e.target)) {
        aiPanel.classList.add('hidden');
    }
});

/* ============================================
   FILE SELECTION
   ============================================ */

function updateSelectionStatus() {
    const count = selectedFiles.length;
    const submitBtn = document.getElementById('submitBtn');

    if (count > 0) {
        // Always enable Transcribe when files are selected — overwrite is decided at submission
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Transcribe';
        }
        announceToScreenReader(`${count} file${count > 1 ? 's' : ''} selected`);
        calculateEstimatesAuto();
    } else {
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = 'Transcribe';
            submitBtn.classList.remove('completed');
        }
        // Show 0 cost estimate when no files selected
        updateUnifiedStatus('0 files • 0:00 • $0.00', false);
    }
}

// Group B: Select All in Current Folder
function selectAllInFolder() {
    selectedFiles = [];
    currentFolder = currentPath; // Lock to current folder
    document.querySelectorAll('.browser-file:not([style*="display: none"]) input[type="checkbox"]').forEach(cb => {
        cb.checked = true;
        const filePath = cb.value;
        if (!selectedFiles.includes(filePath)) {
            selectedFiles.push(filePath);
        }
        cb.closest('.browser-file').classList.add('selected');
    });
    updateSelectionStatus();
    if (selectedFiles.length > 0) {
        const fileText = selectedFiles.length === 1 ? 'file' : 'files';
        showToast('success', `Selected ${selectedFiles.length} ${fileText} in this folder`);
        // Auto-load keyterms for the first selected file
        loadKeytermsForSelection();
    }
}

// Legacy function for backward compatibility
function selectAll() {
    selectAllInFolder();
}

function selectNone() {
    selectedFiles = [];
    currentFolder = currentPath; // Reset folder scope
    document.querySelectorAll('.browser-file input[type="checkbox"]').forEach(cb => {
        cb.checked = false;
        cb.closest('.browser-file').classList.remove('selected');
    });
    // Clear keyterms when clearing selection
    clearKeytermField();
    updateSelectionStatus();
    // showToast('info', 'Selection cleared'); // Disabled
}

function clearSelection() {
    selectNone();
}

/* ============================================
   COST ESTIMATION
   ============================================ */

async function calculateEstimatesAuto() {
    if (selectedFiles.length === 0) {
        updateUnifiedStatus('', false);
        return;
    }

    try {
        const response = await fetch('/api/estimate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ files: selectedFiles })
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();

        // Add LLM keyterm cost if applicable
        let llmCost = 0;
        const keytermField = document.getElementById('keyterms');
        if (keytermField && keytermField.value.trim()) {
            // Estimate LLM cost for all selected files
            llmCost = await estimateLLMCostForBatch(selectedFiles);
        }

        data.llm_cost = llmCost;
        data.total_cost = data.estimated_cost_usd + llmCost;

        displayEstimates(data);

    } catch (error) {
        console.error('Estimate error:', error);
        updateUnifiedStatus('', false);
    }
}

function displayEstimates(data) {
    function formatDuration(seconds) {
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = Math.floor(seconds % 60);
        if (h > 0) {
            return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
        }
        return `${m}:${String(s).padStart(2, '0')}`;
    }

    const fileText = data.total_files === 1 ? 'file' : 'files';
    const totalCost = data.total_cost !== undefined ? data.total_cost : data.estimated_cost_usd;
    const costStr = totalCost < 0.01 ? totalCost.toFixed(4) : totalCost.toFixed(2);
    const statusText = `${data.total_files} ${fileText} • ${formatDuration(data.total_duration_seconds)} • $${costStr}`;
    updateUnifiedStatus(statusText, false);
}

async function estimateLLMCostForBatch(files) {
    // This is a rough estimation based on typical transcript sizes
    // Claude Sonnet pricing: ~$3 per million input tokens, ~$15 per million output tokens
    // GPT pricing: ~$2.50 per million input tokens, ~$10 per million output tokens

    const provider = document.getElementById('llmProvider')?.value || 'anthropic';
    const model = document.getElementById('llmModel')?.value || 'claude-sonnet-4-6';

    try {
        // Make parallel requests to estimate cost for each file
        const costPromises = files.map(async (file) => {
            try {
                const response = await fetch('/api/keyterms/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        video_path: file,
                        provider: provider,
                        model: model,
                        estimate_only: true
                    })
                });

                if (!response.ok) return 0;

                const data = await response.json();
                return data.estimated_cost || 0;
            } catch (error) {
                console.error(`Failed to estimate LLM cost for ${file}:`, error);
                return 0;
            }
        });

        const costs = await Promise.all(costPromises);
        return costs.reduce((sum, cost) => sum + cost, 0);
    } catch (error) {
        console.error('Failed to estimate LLM costs:', error);
        return 0;
    }
}

/* ============================================
   BATCH SUBMISSION
   ============================================ */

async function submitBatch() {
    const selectedFilesList = Array.from(
        document.querySelectorAll('.browser-file input[type="checkbox"]:checked')
    ).map(cb => cb.value);

    if (selectedFilesList.length === 0) {
        showToast('warning', 'Please select at least one file');
        return;
    }
    
    // Check if any selected files already have subtitles — prompt via dialog
    const filesWithSubtitles = Array.from(
        document.querySelectorAll('.browser-file input[type="checkbox"]:checked')
    ).filter(cb => {
        const fileItem = cb.closest('.browser-file');
        const statusIndicator = fileItem.querySelector('.item-status[data-status="complete"]');
        return statusIndicator !== null;
    }).length;

    let forceRegenerate = false;
    if (filesWithSubtitles > 0) {
        const action = await showOverwriteDialog(filesWithSubtitles, selectedFilesList.length);
        if (action === 'cancel') return;
        if (action === 'overwrite') forceRegenerate = true;
    }

    const modelRadio = document.querySelector('input[name="model"]:checked');
    const model = modelRadio ? modelRadio.value : 'nova-3';
    let language = document.getElementById('language').value;
    let detectLanguage = false;

    // Handle special language dropdown values
    if (language === 'auto') {
        detectLanguage = true;
        language = 'en'; // Deepgram ignores language when detect_language=true, but needs a value
    }
    // "multi" is sent as-is — Deepgram uses language="multi" for code-switching

    // Get profanity filter value from radio buttons
    const profanityFilterRadio = document.querySelector('input[name="profanityFilter"]:checked');
    const profanityFilter = profanityFilterRadio ? profanityFilterRadio.value : 'off';

    const enableTranscript = document.getElementById('enableTranscript').checked;
    const saveRawJson = document.getElementById('saveRawJson').checked;

    // Nova-3 Quality Enhancement parameters
    const numerals = document.getElementById('numerals')?.checked || false;
    // NOTE: fillerWords checkbox is now "Remove filler words" so we need to reverse the logic
    const removeFillerWords = document.getElementById('fillerWords')?.checked || false;
    const fillerWords = !removeFillerWords; // Backend expects true to INCLUDE them
    const measurements = document.getElementById('measurements')?.checked || false;

    // Advanced Transcript Features
    const diarization = document.getElementById('diarization')?.checked || false;
    const utterances = document.getElementById('utterances')?.checked || false;
    const paragraphs = document.getElementById('paragraphs')?.checked || false;

    // Tier 1: New transcription features
    const dictation = document.getElementById('dictation')?.checked || false;
    const multichannel = document.getElementById('multichannel')?.checked || false;

    // Redaction: collect selected redact types
    const redactEnabled = document.getElementById('redact')?.checked || false;
    const redactTypes = [];
    if (redactEnabled) {
        if (document.getElementById('redactPci')?.checked) redactTypes.push('pci');
        if (document.getElementById('redactPii')?.checked) redactTypes.push('pii');
        if (document.getElementById('redactNumbers')?.checked) redactTypes.push('numbers');
    }

    // Find & replace
    const replaceEnabled = document.getElementById('findReplace')?.checked || false;
    const replaceTerms = [];
    if (replaceEnabled) {
        const replaceText = document.getElementById('replaceTerms')?.value.trim() || '';
        replaceText.split('\n').forEach(line => {
            const trimmed = line.trim();
            if (trimmed && trimmed.includes(':')) replaceTerms.push(trimmed);
        });
    }

    // Utterance split threshold (only when utterances enabled)
    let uttSplit = null;
    if (utterances) {
        const uttSplitSlider = document.getElementById('uttSplit');
        if (uttSplitSlider) {
            const val = parseFloat(uttSplitSlider.value);
            if (val !== 0.8) uttSplit = val; // Only send non-default
        }
    }

    // Tier 2: Audio Intelligence (English only)
    const sentiment = document.getElementById('sentiment')?.checked || false;
    const summarize = document.getElementById('summarize')?.checked || false;
    const topics = document.getElementById('topics')?.checked || false;
    const intents = document.getElementById('intents')?.checked || false;
    const detectEntities = document.getElementById('detectEntities')?.checked || false;
    const enableSearch = document.getElementById('enableSearch')?.checked || false;
    const searchTerms = [];
    if (enableSearch) {
        const searchText = document.getElementById('searchTerms')?.value.trim() || '';
        searchText.split(',').forEach(t => {
            const trimmed = t.trim();
            if (trimmed) searchTerms.push(trimmed);
        });
    }

    // Tier 3: Request tag
    const tag = document.getElementById('requestTag')?.value.trim() || '';

    const requestBody = {
        files: selectedFilesList,
        model: model,
        language: language,
        profanity_filter: profanityFilter,
        force_regenerate: forceRegenerate,
        save_raw_json: saveRawJson,
        numerals: numerals,
        filler_words: fillerWords,
        detect_language: detectLanguage,
        measurements: measurements,
        diarization: diarization,
        utterances: utterances,
        paragraphs: paragraphs,
        dictation: dictation,
        multichannel: multichannel
    };

    // Conditional fields (only send when active)
    if (redactTypes.length > 0) requestBody.redact = redactTypes;
    if (replaceTerms.length > 0) requestBody.replace = replaceTerms;
    if (uttSplit !== null) requestBody.utt_split = uttSplit;
    if (sentiment) requestBody.sentiment = true;
    if (summarize) requestBody.summarize = true;
    if (topics) requestBody.topics = true;
    if (intents) requestBody.intents = true;
    if (detectEntities) requestBody.detect_entities = true;
    if (searchTerms.length > 0) requestBody.search = searchTerms;
    if (tag) requestBody.tag = tag;

    const keyTerms = document.getElementById('keyTerms').value.trim();
    if (keyTerms) {
        // Nova-3 supports keyterm prompting for all languages including multilingual
        requestBody.keyterms = keyTerms.split(',').map(t => t.trim()).filter(t => t.length > 0);
        // Auto-save keyterms whenever they are provided
        requestBody.auto_save_keyterms = true;
    }

    if (enableTranscript) {
        requestBody.enable_transcript = true;
    }

    // Save settings if "Remember my last settings" is enabled
    const rememberCheckbox = document.getElementById('rememberSettings');
    if (rememberCheckbox && rememberCheckbox.checked) {
        saveCurrentSettings();
    }

    const submitBtn = document.getElementById('submitBtn');
    submitBtn.disabled = true;
    submitBtn.classList.remove('completed');

    // Keep the cost estimate visible (don't update status bar)

    try {
        const response = await fetch('/api/submit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        currentBatchId = data.batch_id;

        announceToScreenReader(`Processing ${data.enqueued} files`);

        // Show cancel button
        const cancelBtn = document.getElementById('cancelBtn');
        if (cancelBtn) cancelBtn.style.display = '';

        startJobMonitoring(currentBatchId);

    } catch (error) {
        console.error('Submit error:', error);
        showToast('error', `Failed to start: ${error.message}`);
        updateUnifiedStatus('Error starting batch', false);
        document.getElementById('submitBtn').disabled = false;
    }
}

/* ============================================
   JOB MONITORING
   ============================================ */

function startJobMonitoring(batchId) {
    if (pollInterval) {
        clearInterval(pollInterval);
    }
    if (eventSource) {
        eventSource.close();
    }

    pollCount = 0;

    eventSource = new EventSource('/api/progress');
    eventSource.addEventListener('ping', function(e) {
        // Connection is alive
    });

    pollInterval = setInterval(() => checkJobStatus(batchId), 3000);
    checkJobStatus(batchId);
}

function retryStatusCheck() {
    if (currentBatchId) {
        pollCount = 0;
        startJobMonitoring(currentBatchId);
    }
}

async function checkJobStatus(batchId) {
    try {
        pollCount++;

        // Client-side polling watchdog: stop after MAX_POLL_COUNT polls
        if (pollCount > MAX_POLL_COUNT) {
            clearInterval(pollInterval);
            if (eventSource) {
                eventSource.close();
            }
            document.getElementById('submitBtn').disabled = false;
            updateUnifiedStatus('Job may be stuck — polling stopped after 10 minutes. Click to retry.', false);
            const statusText = document.getElementById('statusText');
            if (statusText) {
                statusText.style.cursor = 'pointer';
                statusText.onclick = retryStatusCheck;
            }
            announceToScreenReader('Polling stopped. Job may be stuck.');
            return;
        }

        const response = await fetch(`/api/job/${batchId}`);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        updateJobDisplay(data);

        if (data.state === 'SUCCESS' || data.state === 'FAILURE' || data.state === 'REVOKED' || data.state === 'TIMEOUT') {
            clearInterval(pollInterval);
            if (eventSource) {
                eventSource.close();
            }
            document.getElementById('submitBtn').disabled = false;

            if (data.state === 'SUCCESS') {
                const results = data.data?.results || [];
                const successful = results.filter(r => r.status === 'ok').length;
                const skipped = results.filter(r => r.status === 'skipped').length;
                const failed = results.filter(r => r.status === 'error').length;

                updateUnifiedStatus(`Complete: ${successful} processed, ${skipped} skipped, ${failed} failed`, false);
                showToast('success', 'Batch complete');
                announceToScreenReader('Batch processing completed');

                // After 10 seconds, reset button and optionally clear files
                setTimeout(() => {
                    const submitBtn = document.getElementById('submitBtn');
                    if (submitBtn) {
                        submitBtn.classList.remove('completed');
                        submitBtn.textContent = 'Transcribe';
                    }

                    // Check if auto-clear is enabled (default: true)
                    const autoClearEnabled = localStorage.getItem('autoClearFiles') !== 'false';
                    if (autoClearEnabled) {
                        // Clear file selections
                        selectNone();
                        // Refresh the current directory to show updated subtitle indicators
                        browseDirectories(currentPath);
                    }
                }, 10000);
            } else if (data.state === 'FAILURE') {
                // Extract actual error message from children if available
                let errorMsg = 'Batch failed';
                if (data.children) {
                    const failedChild = data.children.find(c => c.error);
                    if (failedChild) {
                        errorMsg = `Failed: ${failedChild.error}`;
                    }
                } else if (data.data?.error) {
                    errorMsg = `Failed: ${data.data.error}`;
                }
                updateUnifiedStatus(errorMsg, false);
                showToast('error', errorMsg);
                announceToScreenReader('Batch processing failed');
            } else if (data.state === 'REVOKED') {
                updateUnifiedStatus('Cancelled', false);
                showToast('info', 'Job cancelled');
                announceToScreenReader('Job cancelled');
            } else if (data.state === 'TIMEOUT') {
                const elapsed = data.elapsed_seconds ? Math.round(data.elapsed_seconds / 60) : '?';
                updateUnifiedStatus(`Timed out after ${elapsed} min — some tasks may still be running. Click to re-check.`, false);
                const statusText = document.getElementById('statusText');
                if (statusText) {
                    statusText.style.cursor = 'pointer';
                    statusText.onclick = retryStatusCheck;
                }
                showToast('error', 'Batch timed out');
                announceToScreenReader('Batch processing timed out');
            }
        }

    } catch (error) {
        console.error('Status check error:', error);
    }
}

async function cancelJob() {
    if (!currentBatchId) return;

    if (!confirm('Are you sure you want to cancel this job?')) {
        return;
    }

    try {
        const response = await fetch(`/api/job/${currentBatchId}/cancel`, {
            method: 'POST'
        });

        if (response.ok) {
            showToast('info', 'Job cancelled');
            announceToScreenReader('Job cancelled');
            // Cancel button hide is handled by updateJobDisplay() on REVOKED state
        }
    } catch (error) {
        console.error('Cancel error:', error);
        showToast('error', 'Failed to cancel job');
    }
}

// Stage-to-label map for human-readable progress
const STAGE_LABELS = {
    'checking': 'Checking...',
    'extracting_audio': 'Extracting audio...',
    'transcribing': 'Transcribing...',
    'generating_srt': 'Generating subtitles...',
    'saving_keyterms': 'Saving keyterms...',
    'generating_transcript': 'Generating transcript...',
    'saving_raw_json': 'Saving debug data...',
    'saving_intelligence': 'Saving intelligence...',
};

// Stage-to-progress map: estimated % through a single task
const STAGE_PROGRESS = {
    'checking': 5,
    'extracting_audio': 15,
    'transcribing': 50,
    'generating_srt': 85,
    'saving_keyterms': 90,
    'generating_transcript': 90,
    'saving_raw_json': 95,
    'saving_intelligence': 95,
};

function updateJobDisplay(data) {
    const submitBtn = document.getElementById('submitBtn');
    const cancelBtn = document.getElementById('cancelBtn');

    if (data.state === 'PENDING' || data.state === 'STARTED') {
        // Add pulsing animation to button and change text
        if (submitBtn) {
            submitBtn.classList.add('processing');
            submitBtn.classList.remove('completed');
            submitBtn.textContent = 'Processing';
        }
        if (cancelBtn) cancelBtn.style.display = '';

        // Show per-file progress with stage-level granularity
        if (data.children && data.children.length > 0) {
            const total = data.children.length;
            const completed = data.children.filter(c => c.state === 'SUCCESS').length;
            const failed = data.children.filter(c => c.state === 'FAILURE').length;
            const done = completed + failed;

            // Find the currently processing child
            const processing = data.children.find(c => c.state === 'PROGRESS' || c.state === 'STARTED');
            const stage = processing?.stage || '';
            const stagePercent = STAGE_PROGRESS[stage] || 0;
            const currentFile = processing?.current_file || processing?.filename || '';

            // Blend task-level and stage-level progress
            const perTaskSlice = 100 / total;
            const percent = Math.round((done / total * 100) + (stagePercent / 100 * perTaskSlice));

            // Build status message with stage label
            const stageLabel = STAGE_LABELS[stage] || '';
            let statusMsg;
            if (total === 1) {
                // Single file: just show stage and filename
                statusMsg = stageLabel && currentFile
                    ? `${stageLabel} — ${currentFile}`
                    : stageLabel || currentFile || 'Processing...';
            } else {
                // Multi-file: show counter, stage, and filename
                statusMsg = stageLabel && currentFile
                    ? `Processing ${done}/${total} — ${stageLabel} — ${currentFile}`
                    : currentFile
                        ? `Processing ${done}/${total}: ${currentFile}`
                        : `Processing ${done}/${total} files`;
            }

            updateUnifiedStatus(statusMsg, true, percent);
        }
    } else if (data.state === 'SUCCESS') {
        updateUnifiedStatus('Complete', false);
        if (cancelBtn) cancelBtn.style.display = 'none';
        // Remove pulsing animation and add completed state
        if (submitBtn) {
            submitBtn.classList.remove('processing');
            submitBtn.classList.add('completed');
            submitBtn.textContent = 'Done!';
        }
    } else if (data.state === 'FAILURE') {
        updateUnifiedStatus('Batch failed', false);
        if (cancelBtn) cancelBtn.style.display = 'none';
        if (submitBtn) {
            submitBtn.classList.remove('processing');
            submitBtn.classList.remove('completed');
        }
    } else if (data.state === 'REVOKED') {
        if (cancelBtn) cancelBtn.style.display = 'none';
    } else if (data.state === 'TIMEOUT') {
        if (cancelBtn) cancelBtn.style.display = 'none';
        if (submitBtn) {
            submitBtn.classList.remove('processing');
            submitBtn.classList.remove('completed');
            submitBtn.textContent = 'Transcribe';
        }
    }
}

/* ============================================
   LLM KEYTERM GENERATION
   ============================================ */

/**
 * Get the path of the currently selected video file
 */
function getCurrentVideoPath() {
    // Find the first checked file input
    const checkedFile = document.querySelector('.browser-file input[type="checkbox"]:checked');
    if (checkedFile) {
        return checkedFile.value;
    }
    return null;
}

/**
 * Update spinner text with custom message
 */
function updateSpinnerText(message) {
    // Since showSpinner doesn't exist yet, we'll use toast for now
    // In a real implementation, you'd modify the actual spinner element
    console.log('Spinner update:', message);
}

/**
 * Show a message to the user (uses existing showToast)
 */
function showMessage(message, type = 'info', options = {}) {
    return showToast(type, message, options);
}

/**
 * Show spinner with message
 */
function showSpinner(message) {
    // Disable the generate button
    const generateBtn = document.getElementById('generateKeytermsBtn');
    if (generateBtn) {
        generateBtn.disabled = true;
        generateBtn.classList.add('processing');
        generateBtn.classList.remove('completed');
        generateBtn.textContent = message;
    }
    showMessage(message, 'info');
}

/**
 * Hide spinner
 */
function hideSpinner() {
    // Re-enable the generate button
    const generateBtn = document.getElementById('generateKeytermsBtn');
    if (generateBtn) {
        generateBtn.disabled = false;
        generateBtn.classList.remove('processing');
        generateBtn.textContent = 'Generate Keyterms';
    }
}

/**
 * Update the keyterm cost estimate display
 */
async function updateKeytermCostEstimate() {
    const costElement = document.getElementById('keytermCostEstimate');

    if (!costElement) {
        console.error('keytermCostEstimate element not found');
        return;
    }

    // Get the current video path
    const videoPath = getCurrentVideoPath();

    if (!videoPath) {
        costElement.textContent = 'Est. cost: $0.00';
        costElement.style.color = 'var(--text-tertiary)';
        return;
    }

    const provider = document.getElementById('llmProvider').value;
    const model = document.getElementById('llmModel').value;

    try {
        costElement.textContent = 'Calculating...';
        costElement.style.color = 'var(--text-tertiary)';
        const estimate = await fetchCostEstimate(videoPath, provider, model);
        costElement.textContent = `Est. cost: $${estimate.estimated_cost.toFixed(4)}`;
        costElement.style.color = 'var(--text-secondary)';
    } catch (error) {
        console.error('Failed to estimate cost:', error);
        costElement.textContent = 'Unable to estimate cost';
        costElement.style.color = 'var(--text-tertiary)';
    }
}

/**
 * Fetch cost estimate for keyterm generation
 */
async function fetchCostEstimate(videoPath, provider, model) {
    const response = await fetch('/api/keyterms/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            video_path: videoPath,
            provider: provider,
            model: model,
            estimate_only: true
        })
    });
    
    if (!response.ok) {
        throw new Error('Cost estimation failed');
    }
    
    return await response.json();
}

/**
 * Poll generation status
 */
async function pollGenerationStatus(taskId) {
    let pollCount = 0;
    const maxPolls = 90; // 90 polls × 2s = 3 minute timeout
    const interval = setInterval(async () => {
        pollCount++;
        try {
            const response = await fetch(`/api/keyterms/generate/status/${taskId}`);
            const data = await response.json();

            // Handle HTTP errors or missing state (corrupted task)
            if (!response.ok || (!data.state && data.error)) {
                clearInterval(interval);
                hideSpinner();
                if (generatingToast) {
                    generatingToast.classList.remove('show');
                    setTimeout(() => generatingToast.remove(), 300);
                    generatingToast = null;
                }
                showMessage(`❌ Generation failed: ${data.error || 'Unknown server error'}`, 'error');
                return;
            }

            // Timeout guard — stop polling after 3 minutes
            if (pollCount >= maxPolls) {
                clearInterval(interval);
                hideSpinner();
                if (generatingToast) {
                    generatingToast.classList.remove('show');
                    setTimeout(() => generatingToast.remove(), 300);
                    generatingToast = null;
                }
                showMessage('❌ Generation timed out after 3 minutes', 'error');
                return;
            }

            if (data.state === 'SUCCESS') {
                clearInterval(interval);

                // Show completed state
                const generateBtn = document.getElementById('generateKeytermsBtn');
                if (generateBtn) {
                    generateBtn.classList.remove('processing');
                    generateBtn.classList.add('completed');
                    generateBtn.disabled = false; // Enable to show full green color
                    generateBtn.textContent = 'Done!';
                }

                // Remove the generating toast
                if (generatingToast) {
                    generatingToast.classList.remove('show');
                    setTimeout(() => generatingToast.remove(), 300);
                    generatingToast = null;
                }

                // Populate keyterms field
                const keytermsInput = document.getElementById('keyTerms');

                // Set flag to prevent input listener from resetting label
                if (keytermsInput._setAutoLoading) {
                    keytermsInput._setAutoLoading(true);
                }

                keytermsInput.value = data.keyterms.join(', ');

                // Reset flag after a brief delay
                setTimeout(() => {
                    if (keytermsInput._setAutoLoading) {
                        keytermsInput._setAutoLoading(false);
                    }
                }, 100);

                // Update label to show generated count
                const keyTermsLabel = document.querySelector('label[for="keyTerms"]');
                if (keyTermsLabel) {
                    keyTermsLabel.textContent = `KEYTERMS (${data.keyterm_count} generated)`;
                    keyTermsLabel.style.color = 'var(--color-green)';
                    keyTermsLabel.setAttribute('data-original-text', 'KEYTERMS');
                }

                // Show success message with cost
                showMessage(
                    `✅ Generated ${data.keyterm_count} keyterms • Cost: $${data.actual_cost.toFixed(3)} • Tokens: ${data.token_count}`,
                    'success'
                );

                // Reset button after 10 seconds
                setTimeout(() => {
                    if (generateBtn) {
                        generateBtn.classList.remove('completed');
                        generateBtn.disabled = false;
                        updateGenerateKeytermButtonState();
                    }
                }, 10000);
            } else if (data.state === 'FAILURE') {
                clearInterval(interval);
                hideSpinner();
                
                // Remove the generating toast
                if (generatingToast) {
                    generatingToast.classList.remove('show');
                    setTimeout(() => generatingToast.remove(), 300);
                    generatingToast = null;
                }
                
                showMessage(`❌ Generation failed: ${data.error}`, 'error');
            } else if (data.state === 'PROGRESS') {
                // Update spinner text with progress
                updateSpinnerText(`Generating keyterms: ${data.stage}...`);
            }
            // Continue polling if PENDING
        } catch (error) {
            clearInterval(interval);
            hideSpinner();
            
            // Remove the generating toast
            if (generatingToast) {
                generatingToast.classList.remove('show');
                setTimeout(() => generatingToast.remove(), 300);
                generatingToast = null;
            }
            
            showMessage(`❌ Error: ${error.message}`, 'error');
        }
    }, 2000); // Poll every 2 seconds
}

/**
 * Check if API keys are configured for LLM providers
 */
async function checkApiKeyStatus() {
    const statusIndicator = document.getElementById('apiKeyStatus');
    const provider = document.getElementById('llmProvider').value;
    const generateBtn = document.getElementById('generateKeytermsBtn');
    
    if (!statusIndicator) return;
    
    // Show checking state
    statusIndicator.className = 'api-key-status checking';
    statusIndicator.setAttribute('data-status', 'Checking API key...');
    
    try {
        const response = await fetch('/api/config');
        const config = await response.json();
        
        // Check if the selected provider has an API key
        let hasKey = false;
        let statusMessage = '';
        
        if (provider === 'anthropic') {
            hasKey = config.anthropic_api_key_configured || false;
            statusMessage = hasKey ? 'Anthropic API key configured' : 'Anthropic API key missing';
        } else if (provider === 'openai') {
            hasKey = config.openai_api_key_configured || false;
            statusMessage = hasKey ? 'OpenAI API key configured' : 'OpenAI API key missing';
        } else if (provider === 'google') {
            hasKey = config.google_api_key_configured || false;
            statusMessage = hasKey ? 'Gemini API key configured' : 'Gemini API key missing';
        }
        
        // Update indicator
        if (hasKey) {
            statusIndicator.className = 'api-key-status configured';
            statusIndicator.setAttribute('data-status', statusMessage);
            if (generateBtn) {
                generateBtn.disabled = false;
                generateBtn.style.display = 'inline-flex';
            }
        } else {
            statusIndicator.className = 'api-key-status missing';
            statusIndicator.setAttribute('data-status', statusMessage);
            if (generateBtn) {
                generateBtn.disabled = true;
                generateBtn.style.display = 'none';
                generateBtn.title = `${statusMessage}. Configure in .env file.`;
            }
        }
    } catch (error) {
        console.error('Failed to check API key status:', error);
        statusIndicator.className = 'api-key-status missing';
        statusIndicator.setAttribute('data-status', 'Unable to check API key status');
        if (generateBtn) {
            generateBtn.disabled = true;
            generateBtn.style.display = 'none';
        }
    }
}

/**
 * Update the Generate Keyterms button state based on whether keyterms exist
 */
function updateGenerateKeytermButtonState() {
    const generateBtn = document.getElementById('generateKeytermsBtn');
    const keytermsInput = document.getElementById('keyTerms');
    const languageSelect = document.getElementById('language');

    if (!generateBtn || !keytermsInput) return;

    // Check language availability — keyterms disabled for multi-language only
    const selectedLanguage = languageSelect?.value || 'en';
    const isMultiLanguage = selectedLanguage === 'multi';
    const keytermAvailable = !isMultiLanguage;

    // Remove all state classes
    generateBtn.classList.remove('btn-green', 'btn-blue', 'btn-orange');

    if (!keytermAvailable) {
        generateBtn.disabled = true;
        generateBtn.textContent = 'Generate Keyterms';
    } else {
        generateBtn.disabled = false;
        generateBtn.classList.add('btn-blue');
        generateBtn.textContent = 'Generate Keyterms';
    }
}

// Keyterm overwrite dialog — returns Promise resolving to 'replace', 'merge', or 'cancel'
function showKeytermOverwriteDialog(keytermCount) {
    return new Promise(resolve => {
        const overlay = document.createElement('div');
        overlay.className = 'dialog-overlay';
        overlay.innerHTML = `
            <div class="dialog-box">
                <div class="dialog-title">Existing Keyterms</div>
                <div class="dialog-message">
                    ${keytermCount} existing keyterm${keytermCount === 1 ? '' : 's'} will be affected.
                </div>
                <div class="dialog-actions">
                    <button class="btn-primary" data-action="replace">Replace All</button>
                    <button class="btn-secondary" data-action="merge">Merge</button>
                    <button class="btn-link" data-action="cancel">Cancel</button>
                </div>
            </div>
        `;

        function cleanup(action) {
            overlay.classList.remove('show');
            setTimeout(() => overlay.remove(), 200);
            resolve(action);
        }

        // Backdrop click = cancel
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) cleanup('cancel');
        });

        // Button clicks
        overlay.querySelectorAll('[data-action]').forEach(btn => {
            btn.addEventListener('click', () => cleanup(btn.dataset.action));
        });

        document.body.appendChild(overlay);
        requestAnimationFrame(() => overlay.classList.add('show'));
    });
}

/**
 * Handle Generate Keyterms button click
 */
async function handleGenerateKeyterms() {
    const videoPath = getCurrentVideoPath();
    if (!videoPath) {
        showMessage('❌ Please select a video first', 'error');
        return;
    }

    const provider = document.getElementById('llmProvider').value;
    const model = document.getElementById('llmModel').value;
    const keytermsInput = document.getElementById('keyTerms');
    const hasKeyterms = keytermsInput?.value.trim().length > 0;

    let preserveExisting = false;

    // If keyterms exist, show overwrite dialog
    if (hasKeyterms) {
        const keytermCount = keytermsInput.value.split(',').filter(k => k.trim().length > 0).length;
        const action = await showKeytermOverwriteDialog(keytermCount);

        if (action === 'cancel') return;
        preserveExisting = (action === 'merge');
    }

    try {
        // Start generation immediately - show persistent toast
        showSpinner('Processing');
        generatingToast = showMessage('Processing', 'info', { persist: true });

        const response = await fetch('/api/keyterms/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                video_path: videoPath,
                provider: provider,
                model: model,
                preserve_existing: preserveExisting
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Generation failed');
        }

        // Poll for completion
        pollGenerationStatus(data.task_id);

    } catch (error) {
        hideSpinner();

        // Remove the generating toast
        if (generatingToast) {
            generatingToast.classList.remove('show');
            setTimeout(() => generatingToast.remove(), 300);
            generatingToast = null;
        }

        showMessage(`❌ Error: ${error.message}`, 'error');
    }
}