/**
 * Virtual Recipe Box & Planner - Theme & Color Customizer Engine
 * Supports custom primary/hover/accent/tint colors, preset palettes,
 * background pattern choices, instant live preview, and cross-page persistence.
 */

(function () {
    const STORAGE_KEY = 'app_custom_theme';

    const PRESETS = {
        'classic-rose': {
            id: 'classic-rose',
            name: 'Classic Rose',
            primary: '#FF6B81',
            hover: '#E85B70',
            accent: '#F7CAC9',
            tint: '#FFE8EE',
            darkPrimary: '#FE9BA3',
            pattern: 'floral'
        },
        'sage-green': {
            id: 'sage-green',
            name: 'Sage & Forest',
            primary: '#2E7D32',
            hover: '#1B5E20',
            accent: '#A5D6A7',
            tint: '#E8F5E9',
            darkPrimary: '#81C784',
            pattern: 'floral'
        },
        'ocean-blue': {
            id: 'ocean-blue',
            name: 'Ocean Breeze',
            primary: '#1976D2',
            hover: '#1565C0',
            accent: '#90CAF9',
            tint: '#E3F2FD',
            darkPrimary: '#64B5F6',
            pattern: 'floral'
        },
        'sunset-amber': {
            id: 'sunset-amber',
            name: 'Sunset Terracotta',
            primary: '#E65100',
            hover: '#BF360C',
            accent: '#FFCC80',
            tint: '#FFF3E0',
            darkPrimary: '#FFB74D',
            pattern: 'floral'
        },
        'berry-purple': {
            id: 'berry-purple',
            name: 'Berry Lavender',
            primary: '#7B1FA2',
            hover: '#4A148C',
            accent: '#CE93D8',
            tint: '#F3E5F5',
            darkPrimary: '#BA68C8',
            pattern: 'floral'
        },
        'warm-mocha': {
            id: 'warm-mocha',
            name: 'Warm Mocha',
            primary: '#6D4C41',
            hover: '#4E342E',
            accent: '#BCAAA4',
            tint: '#EFEBE9',
            darkPrimary: '#A1887F',
            pattern: 'floral'
        },
        'teal-cyan': {
            id: 'teal-cyan',
            name: 'Teal Lagoon',
            primary: '#00897B',
            hover: '#00695C',
            accent: '#80CBC4',
            tint: '#E0F2F1',
            darkPrimary: '#4DB6AC',
            pattern: 'floral'
        },
        'slate-charcoal': {
            id: 'slate-charcoal',
            name: 'Modern Slate',
            primary: '#37474F',
            hover: '#263238',
            accent: '#90A4AE',
            tint: '#ECEFF1',
            darkPrimary: '#B0BEC5',
            pattern: 'clean'
        }
    };

    // Color math helpers
    function hexToRgb(hex) {
        let cleanHex = hex.replace('#', '');
        if (cleanHex.length === 3) {
            cleanHex = cleanHex.split('').map(c => c + c).join('');
        }
        const num = parseInt(cleanHex, 16);
        return {
            r: (num >> 16) & 255,
            g: (num >> 8) & 255,
            b: num & 255
        };
    }

    function rgbToHex(r, g, b) {
        return '#' + [r, g, b].map(x => {
            const clamped = Math.max(0, Math.min(255, Math.round(x)));
            return clamped.toString(16).padStart(2, '0');
        }).join('').toUpperCase();
    }

    function blendWithWhite(hex, weight) {
        const rgb = hexToRgb(hex);
        return rgbToHex(
            rgb.r + (255 - rgb.r) * weight,
            rgb.g + (255 - rgb.g) * weight,
            rgb.b + (255 - rgb.b) * weight
        );
    }

    function darkenColor(hex, factor = 0.15) {
        const rgb = hexToRgb(hex);
        return rgbToHex(
            rgb.r * (1 - factor),
            rgb.g * (1 - factor),
            rgb.b * (1 - factor)
        );
    }

    function lightenColor(hex, factor = 0.28) {
        const rgb = hexToRgb(hex);
        return rgbToHex(
            rgb.r + (255 - rgb.r) * factor,
            rgb.g + (255 - rgb.g) * factor,
            rgb.b + (255 - rgb.b) * factor
        );
    }

    function getPatternCSS(patternName, primaryHex) {
        const encodedColor = encodeURIComponent(blendWithWhite(primaryHex, 0.35));
        if (patternName === 'clean') {
            return 'none';
        }
        if (patternName === 'dots') {
            return `url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 20 20"><circle cx="2" cy="2" r="1.5" fill="${encodedColor}" opacity="0.25"/></svg>')`;
        }
        if (patternName === 'grid') {
            return `url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="30" height="30" viewBox="0 0 30 30"><path d="M 30 0 L 0 0 0 30" fill="none" stroke="${encodedColor}" stroke-width="0.75" opacity="0.2"/></svg>')`;
        }
        // Default floral / circle sparkles
        return `url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" opacity="0.12"><circle cx="20" cy="20" r="5" fill="${encodedColor}" /><circle cx="80" cy="80" r="5" fill="${encodedColor}" /><circle cx="20" cy="80" r="5" fill="${encodedColor}" /><circle cx="80" cy="20" r="5" fill="${encodedColor}" /></svg>')`;
    }

    function loadThemeConfig() {
        try {
            const saved = localStorage.getItem(STORAGE_KEY);
            if (saved) {
                return JSON.parse(saved);
            }
        } catch (e) {
            console.error('Failed to load theme from localStorage', e);
        }
        return { ...PRESETS['classic-rose'] };
    }

    function saveThemeConfig(config) {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
        } catch (e) {
            console.error('Failed to save theme to localStorage', e);
        }
    }

    function applyThemeCSS(config) {
        const isDark = document.body && document.body.classList.contains('dark-mode');
        const primary = config.primary || '#FF6B81';
        const hover = config.hover || darkenColor(primary, 0.15);
        const accent = config.accent || blendWithWhite(primary, 0.5);
        const tint = config.tint || blendWithWhite(primary, 0.88);
        const darkPrimary = config.darkPrimary || lightenColor(primary, 0.28);
        const darkHover = darkenColor(darkPrimary, 0.15);
        const patternCSS = getPatternCSS(config.pattern || 'floral', primary);

        // 1. Direct inline CSS variables on documentElement (highest CSS specificity)
        const root = document.documentElement;
        if (root && root.style) {
            root.style.setProperty('--primary-pink', isDark ? darkPrimary : primary);
            root.style.setProperty('--button-hover', isDark ? darkHover : hover);
            root.style.setProperty('--accent-pink', accent);
            root.style.setProperty('--light-pink', isDark ? 'rgba(255,255,255,0.12)' : tint);
            root.style.setProperty('--tag-bg', isDark ? 'rgba(255,255,255,0.12)' : tint);
            root.style.setProperty('--tag-color', isDark ? darkPrimary : primary);
            root.style.setProperty('--floral-pattern', patternCSS);
        }

        if (document.body) {
            document.body.style.backgroundImage = patternCSS;
        }

        // 2. High-specificity stylesheet with !important rules
        let styleTag = document.getElementById('custom-theme-styles');
        if (!styleTag) {
            styleTag = document.createElement('style');
            styleTag.id = 'custom-theme-styles';
            (document.head || document.documentElement).appendChild(styleTag);
        } else {
            // Re-append to ensure it remains at the end of head
            if (styleTag.parentNode) {
                styleTag.parentNode.appendChild(styleTag);
            }
        }

        styleTag.textContent = `
            :root, html, body {
                --primary-pink: ${primary} !important;
                --button-hover: ${hover} !important;
                --accent-pink: ${accent} !important;
                --light-pink: ${tint} !important;
                --tag-bg: ${tint} !important;
                --tag-color: ${primary} !important;
                --floral-pattern: ${patternCSS} !important;
            }
            body.dark-mode {
                --primary-pink: ${darkPrimary} !important;
                --button-hover: ${darkHover} !important;
                --accent-pink: ${accent} !important;
                --tag-bg: rgba(255, 255, 255, 0.12) !important;
                --tag-color: ${darkPrimary} !important;
            }
            .theme-btn-customizer {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                background: rgba(255, 255, 255, 0.22);
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 0.4);
                padding: 4px 12px;
                border-radius: 20px;
                cursor: pointer;
                font-size: 0.85em;
                font-weight: 600;
                transition: all 0.2s ease;
                backdrop-filter: blur(4px);
                text-decoration: none;
                box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
            }
            .theme-btn-customizer:hover {
                background: rgba(255, 255, 255, 0.35);
                transform: translateY(-1px);
                box-shadow: 0 2px 5px rgba(0, 0, 0, 0.15);
            }
        `;
    }

    // Apply saved theme immediately on load
    const initialConfig = loadThemeConfig();
    applyThemeCSS(initialConfig);

    // Watch for dark mode changes on body
    function setupDarkModeObserver() {
        if (!document.body) return;
        const observer = new MutationObserver((mutations) => {
            for (const mutation of mutations) {
                if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
                    applyThemeCSS(loadThemeConfig());
                }
            }
        });
        observer.observe(document.body, { attributes: true, attributeFilter: ['class'] });
    }

    // Modal UI Generation
    function createThemeModal() {
        if (document.getElementById('theme-studio-modal')) return;

        const modal = document.createElement('div');
        modal.id = 'theme-studio-modal';
        modal.style.cssText = `
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0, 0, 0, 0.6);
            z-index: 99999;
            overflow-y: auto;
            backdrop-filter: blur(4px);
            align-items: center;
            justify-content: center;
            padding: 20px;
            box-sizing: border-box;
        `;

        modal.innerHTML = `
            <div style="
                background: var(--card-background, #fff);
                color: var(--text-color, #333);
                border: 1px solid var(--border-color, #ddd);
                border-radius: 16px;
                max-width: 580px;
                width: 100%;
                box-shadow: 0 16px 40px rgba(0,0,0,0.3);
                padding: 24px;
                position: relative;
                box-sizing: border-box;
                animation: themeModalPop 0.2s cubic-bezier(0.16, 1, 0.3, 1);
            ">
                <style>
                    @keyframes themeModalPop {
                        from { transform: scale(0.95); opacity: 0; }
                        to { transform: scale(1); opacity: 1; }
                    }
                    .theme-preset-grid {
                        display: grid;
                        grid-template-columns: repeat(auto-fill, minmax(115px, 1fr));
                        gap: 10px;
                        margin: 15px 0 20px;
                    }
                    .theme-preset-card {
                        border: 2px solid var(--border-color, #e0e0e0);
                        border-radius: 12px;
                        padding: 10px 8px;
                        cursor: pointer;
                        text-align: center;
                        transition: all 0.2s ease;
                        background: var(--background-color, #fff);
                        color: var(--text-color, #333);
                    }
                    .theme-preset-card:hover {
                        transform: translateY(-2px);
                        border-color: var(--primary-pink);
                        box-shadow: 0 4px 10px rgba(0,0,0,0.1);
                    }
                    .theme-preset-card.active {
                        border-color: var(--primary-pink);
                        box-shadow: 0 0 0 2px var(--primary-pink);
                    }
                    .theme-color-row {
                        display: flex;
                        align-items: center;
                        justify-content: space-between;
                        margin-bottom: 12px;
                        gap: 12px;
                        padding: 8px 12px;
                        border-radius: 10px;
                        background: var(--background-color, #f9f9f9);
                        border: 1px solid var(--border-color, #eee);
                    }
                    .theme-color-row input[type="color"] {
                        border: none;
                        width: 36px;
                        height: 36px;
                        border-radius: 8px;
                        cursor: pointer;
                        background: none;
                        padding: 0;
                    }
                    .theme-color-row input[type="text"] {
                        width: 85px;
                        font-family: monospace;
                        text-transform: uppercase;
                        font-size: 0.9em;
                        padding: 6px;
                        border: 1px solid var(--border-color, #ccc);
                        border-radius: 6px;
                        background: var(--card-background, #fff);
                        color: var(--text-color, #333);
                        text-align: center;
                    }
                    .pattern-btn-group {
                        display: flex;
                        gap: 8px;
                        flex-wrap: wrap;
                        margin-top: 8px;
                    }
                    .pattern-btn {
                        flex: 1;
                        min-width: 90px;
                        padding: 8px 12px;
                        border: 1px solid var(--border-color, #ccc);
                        border-radius: 8px;
                        background: var(--background-color, #fff);
                        color: var(--text-color, #333);
                        cursor: pointer;
                        font-size: 0.85em;
                        font-weight: 600;
                        transition: all 0.2s ease;
                    }
                    .pattern-btn.active {
                        background: var(--primary-pink);
                        color: white;
                        border-color: var(--primary-pink);
                    }
                </style>

                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                    <h2 style="margin:0; font-size:1.35em; display:flex; align-items:center; gap:8px; color:var(--primary-pink);">
                        🎨 Theme & Color Studio
                    </h2>
                    <button id="theme-modal-close" style="
                        background:none; border:none; font-size:1.4em; cursor:pointer; color:var(--text-color); opacity:0.7; padding:4px 8px;
                    ">&times;</button>
                </div>

                <p style="margin:0 0 12px; font-size:0.9em; opacity:0.85;">
                    Personalize your website colors! Select a curated palette or customize your own. Changes apply instantly and persist across all pages.
                </p>

                <!-- Preset Palettes -->
                <div style="font-weight:bold; font-size:0.92em; color:var(--primary-pink);">Curated Palettes:</div>
                <div class="theme-preset-grid" id="theme-presets-container"></div>

                <!-- Custom Colors -->
                <div style="margin-top:14px; border-top:1px dashed var(--border-color); padding-top:14px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                        <div style="font-weight:bold; font-size:0.92em; color:var(--primary-pink);">Custom Color Pickers:</div>
                        <button id="theme-auto-calc-btn" style="
                            font-size:0.8em; background:var(--background-color); color:var(--text-color); border:1px solid var(--border-color); padding:4px 10px; border-radius:12px; cursor:pointer; font-weight:600;
                        " title="Automatically calculate matching hover, highlight, and tint colors based on Primary">✨ Auto-Generate Palette</button>
                    </div>

                    <div class="theme-color-row">
                        <div>
                            <strong>Primary Color</strong>
                            <div style="font-size:0.8em; opacity:0.75;">Header bar, titles, primary buttons</div>
                        </div>
                        <div style="display:flex; align-items:center; gap:8px;">
                            <input type="color" id="theme-picker-primary" value="#FF6B81">
                            <input type="text" id="theme-hex-primary" maxlength="7" value="#FF6B81">
                        </div>
                    </div>

                    <div class="theme-color-row">
                        <div>
                            <strong>Button Hover</strong>
                            <div style="font-size:0.8em; opacity:0.75;">Hover state on buttons & active tabs</div>
                        </div>
                        <div style="display:flex; align-items:center; gap:8px;">
                            <input type="color" id="theme-picker-hover" value="#E85B70">
                            <input type="text" id="theme-hex-hover" maxlength="7" value="#E85B70">
                        </div>
                    </div>

                    <div class="theme-color-row">
                        <div>
                            <strong>Accent / Highlight</strong>
                            <div style="font-size:0.8em; opacity:0.75;">Borders, badges, and card accents</div>
                        </div>
                        <div style="display:flex; align-items:center; gap:8px;">
                            <input type="color" id="theme-picker-accent" value="#F7CAC9">
                            <input type="text" id="theme-hex-accent" maxlength="7" value="#F7CAC9">
                        </div>
                    </div>

                    <div class="theme-color-row">
                        <div>
                            <strong>Soft Tint</strong>
                            <div style="font-size:0.8em; opacity:0.75;">Tag backgrounds and subtle highlights</div>
                        </div>
                        <div style="display:flex; align-items:center; gap:8px;">
                            <input type="color" id="theme-picker-tint" value="#FFE8EE">
                            <input type="text" id="theme-hex-tint" maxlength="7" value="#FFE8EE">
                        </div>
                    </div>
                </div>

                <!-- Background Pattern -->
                <div style="margin-top:14px; border-top:1px dashed var(--border-color); padding-top:12px;">
                    <div style="font-weight:bold; font-size:0.92em; color:var(--primary-pink);">Background Pattern:</div>
                    <div class="pattern-btn-group" id="theme-patterns-container">
                        <button class="pattern-btn" data-pattern="floral">✨ Floral Sparkle</button>
                        <button class="pattern-btn" data-pattern="dots">⚪ Subtle Dots</button>
                        <button class="pattern-btn" data-pattern="grid">📐 Clean Grid</button>
                        <button class="pattern-btn" data-pattern="clean">⬛ Solid Clean</button>
                    </div>
                </div>

                <!-- Action Buttons -->
                <div style="margin-top:20px; display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap;">
                    <button id="theme-reset-btn" style="
                        background: transparent; color: #e53935; border: 1px solid #e53935; padding: 8px 16px; border-radius: 20px; font-weight: 600; cursor: pointer; transition: all 0.2s; font-size:0.9em;
                    ">Reset to Default</button>
                    
                    <button id="theme-save-btn" style="
                        background: var(--primary-pink); color: white; border: none; padding: 9px 24px; border-radius: 20px; font-weight: bold; cursor: pointer; transition: all 0.2s; box-shadow: 0 4px 10px rgba(0,0,0,0.15); font-size:0.95em;
                    ">Done</button>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        // Bind events
        initModalEvents(modal);
    }

    function initModalEvents(modal) {
        const closeBtn = document.getElementById('theme-modal-close');
        const saveBtn = document.getElementById('theme-save-btn');
        const resetBtn = document.getElementById('theme-reset-btn');
        const autoCalcBtn = document.getElementById('theme-auto-calc-btn');
        const presetsContainer = document.getElementById('theme-presets-container');
        const patternsContainer = document.getElementById('theme-patterns-container');

        let currentConfig = loadThemeConfig();

        function syncInputs(config) {
            document.getElementById('theme-picker-primary').value = config.primary || '#FF6B81';
            document.getElementById('theme-hex-primary').value = config.primary || '#FF6B81';

            document.getElementById('theme-picker-hover').value = config.hover || '#E85B70';
            document.getElementById('theme-hex-hover').value = config.hover || '#E85B70';

            document.getElementById('theme-picker-accent').value = config.accent || '#F7CAC9';
            document.getElementById('theme-hex-accent').value = config.accent || '#F7CAC9';

            document.getElementById('theme-picker-tint').value = config.tint || '#FFE8EE';
            document.getElementById('theme-hex-tint').value = config.tint || '#FFE8EE';

            // Preset cards active state
            document.querySelectorAll('.theme-preset-card').forEach(card => {
                card.classList.toggle('active', card.dataset.presetId === config.id);
            });

            // Pattern buttons active state
            document.querySelectorAll('.pattern-btn').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.pattern === (config.pattern || 'floral'));
            });
        }

        // Render Presets
        presetsContainer.innerHTML = Object.values(PRESETS).map(p => `
            <div class="theme-preset-card ${currentConfig.id === p.id ? 'active' : ''}" data-preset-id="${p.id}">
                <div style="display:flex; justify-content:center; gap:4px; margin-bottom:6px;">
                    <span style="width:16px; height:16px; border-radius:50%; background:${p.primary}; display:inline-block; border:1px solid rgba(0,0,0,0.15);"></span>
                    <span style="width:16px; height:16px; border-radius:50%; background:${p.accent}; display:inline-block; border:1px solid rgba(0,0,0,0.15);"></span>
                    <span style="width:16px; height:16px; border-radius:50%; background:${p.tint}; display:inline-block; border:1px solid rgba(0,0,0,0.15);"></span>
                </div>
                <div style="font-size:0.82em; font-weight:600;">${p.name}</div>
            </div>
        `).join('');

        // Preset Click
        presetsContainer.addEventListener('click', (e) => {
            const card = e.target.closest('.theme-preset-card');
            if (!card) return;
            const presetId = card.dataset.presetId;
            if (PRESETS[presetId]) {
                currentConfig = { ...PRESETS[presetId] };
                syncInputs(currentConfig);
                applyThemeCSS(currentConfig);
                saveThemeConfig(currentConfig);
            }
        });

        // Color Picker & Hex Pair sync helper
        function setupColorSync(pickerId, hexId, key) {
            const picker = document.getElementById(pickerId);
            const hex = document.getElementById(hexId);

            picker.addEventListener('input', (e) => {
                const val = e.target.value.toUpperCase();
                hex.value = val;
                currentConfig[key] = val;
                currentConfig.id = 'custom';
                applyThemeCSS(currentConfig);
                saveThemeConfig(currentConfig);
                syncInputs(currentConfig);
            });

            hex.addEventListener('input', (e) => {
                let val = e.target.value;
                if (!val.startsWith('#')) val = '#' + val;
                if (/^#[0-9A-F]{6}$/i.test(val)) {
                    picker.value = val;
                    currentConfig[key] = val.toUpperCase();
                    currentConfig.id = 'custom';
                    applyThemeCSS(currentConfig);
                    saveThemeConfig(currentConfig);
                    syncInputs(currentConfig);
                }
            });
        }

        setupColorSync('theme-picker-primary', 'theme-hex-primary', 'primary');
        setupColorSync('theme-picker-hover', 'theme-hex-hover', 'hover');
        setupColorSync('theme-picker-accent', 'theme-hex-accent', 'accent');
        setupColorSync('theme-picker-tint', 'theme-hex-tint', 'tint');

        // Auto-Generate palette from primary
        autoCalcBtn.addEventListener('click', () => {
            const primary = currentConfig.primary || '#FF6B81';
            currentConfig.hover = darkenColor(primary, 0.15);
            currentConfig.accent = blendWithWhite(primary, 0.5);
            currentConfig.tint = blendWithWhite(primary, 0.88);
            currentConfig.darkPrimary = lightenColor(primary, 0.28);
            currentConfig.id = 'custom';
            syncInputs(currentConfig);
            applyThemeCSS(currentConfig);
            saveThemeConfig(currentConfig);
        });

        // Pattern selection
        patternsContainer.addEventListener('click', (e) => {
            const btn = e.target.closest('.pattern-btn');
            if (!btn) return;
            currentConfig.pattern = btn.dataset.pattern;
            syncInputs(currentConfig);
            applyThemeCSS(currentConfig);
            saveThemeConfig(currentConfig);
        });

        // Reset
        resetBtn.addEventListener('click', () => {
            currentConfig = { ...PRESETS['classic-rose'] };
            syncInputs(currentConfig);
            applyThemeCSS(currentConfig);
            saveThemeConfig(currentConfig);
        });

        // Close / Done
        function closeModal() {
            modal.style.display = 'none';
        }

        closeBtn.addEventListener('click', closeModal);
        saveBtn.addEventListener('click', closeModal);
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });

        // Open handler
        window.openThemeModal = function () {
            currentConfig = loadThemeConfig();
            syncInputs(currentConfig);
            modal.style.display = 'flex';
        };
    }

    // Initialize when DOM is ready
    function init() {
        applyThemeCSS(loadThemeConfig());
        setupDarkModeObserver();
        createThemeModal();

        // Check if header exists and add theme button if not present
        const themeSwitchWrappers = document.querySelectorAll('.theme-switch-wrapper');
        themeSwitchWrappers.forEach(wrapper => {
            if (!wrapper.querySelector('.theme-btn-customizer')) {
                const btn = document.createElement('button');
                btn.className = 'theme-btn-customizer';
                btn.type = 'button';
                btn.innerHTML = '🎨 Theme';
                btn.title = 'Customize website colors & theme';
                btn.addEventListener('click', () => {
                    if (window.openThemeModal) window.openThemeModal();
                });
                wrapper.insertBefore(btn, wrapper.firstChild);
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
