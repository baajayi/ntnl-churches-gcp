// CTS Floating Widget JavaScript - Self-contained Shadow DOM implementation
// Combines compact floating behavior with full chat functionality for CTS
// Can be dropped on any webpage without conflicts

// Script loading verification
console.log('📜 CTS Widget Script Loaded Successfully');
console.log('🕐 Load time:', new Date().toISOString());
console.log('🌍 Origin:', window.location.origin);

// Global variables
let isExpanded = false;
let chatHistory = [];
let originalWidgetBottom = null;
let keyboardVisible = false;

// Shadow DOM and widget references
let shadowRoot = null;
let widgetContainer = null;

// DOM elements - will be initialized when DOM loads (now within shadow DOM)
let widget = null;
let queryInput = null;
let chatInterface = null;
let chatMessages = null;
let promptInput = null;
let askButton = null;
let sidebar = null;
let sidebarOverlay = null;
let menuToggle = null;
let aboutPanel = null;
let aboutClose = null;
let aboutMeLink = null;

// Apply critical styles to widget container to ensure it stays above all page elements
function applyContainerStyles(container) {
    console.log('🎨 Applying critical container styles to ensure maximum visibility');

    const criticalStyles = {
        'position': 'fixed !important',
        'z-index': '2147483647 !important',
        'pointer-events': 'none !important',
        'top': 'auto !important',
        'left': 'auto !important',
        'right': 'auto !important',
        'bottom': 'auto !important',
        'width': 'auto !important',
        'height': 'auto !important',
        'margin': '0 !important',
        'padding': '0 !important',
        'border': 'none !important',
        'background': 'transparent !important',
        'overflow': 'visible !important',
        'clip': 'auto !important',
        'clip-path': 'none !important',
        'mask': 'none !important',
        'filter': 'none !important',
        'opacity': '1 !important',
        'visibility': 'visible !important',
        'display': 'block !important'
    };

    Object.entries(criticalStyles).forEach(([property, value]) => {
        container.style.setProperty(property, value, 'important');
        const cleanValue = value.replace(' !important', '');
        if (property === 'z-index') {
            container.style.zIndex = '2147483647';
        } else if (property === 'position') {
            container.style.position = 'fixed';
        }
    });

    const inlineCSS = Object.entries(criticalStyles)
        .map(([prop, val]) => `${prop}: ${val}`)
        .join('; ');
    container.setAttribute('style', inlineCSS + '; ' + (container.getAttribute('style') || ''));

    container.style.setProperty('--widget-z-index', '2147483647', 'important');
    container.style.setProperty('z-index', 'var(--widget-z-index, 2147483647)', 'important');

    const computedStyle = window.getComputedStyle(container);
    const actualZIndex = computedStyle.zIndex;
    const actualPosition = computedStyle.position;

    console.log('✅ Container styles applied:', {
        'z-index': actualZIndex,
        'position': actualPosition
    });

    if (actualZIndex !== '2147483647' || actualPosition !== 'fixed') {
        console.warn('⚠️ Critical container styles may not have applied correctly:', {
            expected: { zIndex: '2147483647', position: 'fixed' },
            actual: { zIndex: actualZIndex, position: actualPosition }
        });
    }
}

// Ensure container is positioned optimally in DOM
function ensureOptimalDOMPosition(container) {
    console.log('📍 Checking DOM position for optimal stacking...');

    try {
        if (container.parentElement !== document.body) {
            console.log('🚀 Moving container to document.body for optimal positioning...');
            document.body.appendChild(container);
            console.log('✅ Container moved to end of body');
        }

        console.log('📊 Container DOM info:', {
            parentElement: container.parentElement?.tagName,
            parentId: container.parentElement?.id,
            siblingCount: container.parentElement?.children.length
        });
    } catch (error) {
        console.error('Error checking DOM position:', error);
    }
}

// Periodically enforce critical container styles
function enforceContainerStyles() {
    if (!widgetContainer) return;

    const computedStyle = window.getComputedStyle(widgetContainer);
    if (computedStyle.zIndex !== '2147483647' || computedStyle.position !== 'fixed') {
        console.log('⚠️ Container styles overridden, re-applying...');
        applyContainerStyles(widgetContainer);
    }
}

// Initialize Shadow DOM and create widget structure
function initializeShadowDOM() {
    try {
        if (!HTMLElement.prototype.attachShadow) {
            console.warn('Shadow DOM not supported. Falling back to regular DOM.');
            return false;
        }

        widgetContainer = document.getElementById('ctsChatWidget');
        if (!widgetContainer) {
            console.error('Widget container #ctsChatWidget not found in DOM');
            return false;
        }

        console.log('🔨 Creating Shadow DOM for CTS widget...');
        shadowRoot = widgetContainer.attachShadow({ mode: 'open' });

        if (!shadowRoot) {
            console.error('❌ Failed to create Shadow DOM root');
            return false;
        }

        const widgetHTML = `
            <div class="cts-chat-widget" id="ctsChatWidgetInner" style="opacity: 0; transition: opacity 0.3s ease;">
                <div class="cts-widget-content">
                    <div class="cts-widget-header">
                        <span>🤖 Ask CTS Assistant</span>
                        <button class="cts-widget-close" id="cts-widget-close-btn">×</button>
                    </div>
                    <div class="cts-widget-body">
                        <div class="cts-widget-help" id="ctsWidgetHelp">
                            <div class="cts-help-text">
                                Hi! I'm CTS Assistant, your AI helper. I can assist with questions and provide information. Here are a couple of examples of what you can ask me:
                            </div>
                            <div class="cts-help-examples">
                                <div class="cts-help-example">
                                    "What services does CTS offer?"
                                </div>
                                <div class="cts-help-example">
                                    "Can you help me understand your programs?"
                                </div>
                            </div>
                            <div class="cts-help-cta">
                                Try it out!
                            </div>
                        </div>
                        <form class="cts-widget-form" id="ctsWidgetForm">
                            <input type="text"
                                   id="ctsQueryInput"
                                   class="cts-widget-input"
                                   placeholder="Type your question here..."
                                   autocomplete="off">
                            <button type="submit" class="cts-widget-send">Send</button>
                        </form>
                    </div>
                </div>
            </div>
        `;

        shadowRoot.innerHTML = widgetHTML;
        loadShadowCSS();
        widgetContainer.style.display = 'block';
        applyContainerStyles(widgetContainer);
        ensureOptimalDOMPosition(widgetContainer);
        widgetContainer.innerHTML = '';
        console.log('Shadow DOM widget initialization complete');
        return true;
    } catch (error) {
        console.error('Error initializing Shadow DOM widget:', error);
        return false;
    }
}

// Load CSS into Shadow DOM
function loadShadowCSS() {
    console.log('🎨 Loading comprehensive inline CSS for Shadow DOM...');
    const styleElement = document.createElement('style');
    styleElement.textContent = getInlineCSS();
    shadowRoot.appendChild(styleElement);

    const widgetInner = shadowRoot.getElementById('ctsChatWidgetInner');
    if (widgetInner) {
        widgetInner.style.opacity = '1';
    }

    console.log('✅ Self-contained CSS loaded successfully');
}

// Comprehensive inline CSS
function getInlineCSS() {
    return `
        @import url('https://fonts.googleapis.com/css2?family=Figtree:wght@300;400;500;600;700&display=swap');

        :host {
            --widget-font-family: 'Figtree', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            --chat-font-family: 'Figtree', Arial, sans-serif;
            --primary-color: #0A6AAC;
            --primary-dark: #124264;
            --spacing-sm: 8px;
            --spacing-md: 12px;
            --spacing-lg: 16px;
            --spacing-xl: 20px;
        }

        /* Reset and alignment */
        .cts-chat-widget,
        .cts-chat-widget *,
        .cts-chat-widget .user-message,
        .cts-chat-widget .ai-message,
        .cts-chat-widget .message,
        .cts-chat-widget .message-content,
        .cts-chat-widget .cts-help-text,
        .cts-chat-widget .cts-help-example,
        .cts-chat-widget .cts-help-cta,
        .cts-chat-widget .cts-widget-body,
        .cts-chat-widget .cts-widget-help,
        .cts-chat-widget .cts-help-examples,
        .cts-chat-widget p,
        .cts-chat-widget div,
        .cts-chat-widget span,
        .cts-chat-widget input,
        .cts-chat-widget textarea,
        .cts-about-panel,
        .cts-about-panel *,
        .cts-about-panel .cts-about-content,
        .cts-about-panel .cts-about-content p,
        .cts-about-panel .cts-about-content h2,
        .cts-about-panel .cts-about-content h3,
        .cts-about-panel .cts-example-prompt,
        .cts-about-panel .cts-examples {
            text-align: left;
            box-sizing: border-box;
        }

        .cts-chat-header,
        .cts-chat-header * {
            text-align: inherit;
        }

        .cts-chat-header label,
        #cts-chat-label {
            text-align: right;
        }

        .cts-ask-button,
        #cts-ask-button {
            text-align: center;
        }

        /* Main widget container */
        .cts-chat-widget {
            position: fixed;
            bottom: 20px;
            right: 20px;
            width: 270px;
            max-width: calc(100vw - 40px);
            background: #fafafa;
            border-radius: 10px;
            box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
            font-family: var(--widget-font-family);
            overflow: hidden;
            border: 1px solid #e0e0e0;
            z-index: 2147483647 !important;
            contain: layout style paint;
            pointer-events: auto !important;
        }

        .cts-chat-widget .cts-chat-interface {
            display: none;
        }

        .cts-sidebar {
            display: none;
        }

        /* Widget header */
        .cts-widget-header {
            background: var(--primary-color);
            padding: 10px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            color: white;
            font-weight: 600;
            font-size: 12px;
            border-bottom: 1px solid #e0e0e0;
            font-family: var(--widget-font-family);
            min-height: 36px;
        }

        .cts-widget-header span {
            flex: 1;
            text-align: left;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }

        .cts-widget-close {
            background: none;
            border: none;
            color: white;
            font-size: 14px;
            cursor: pointer;
            padding: 2px 4px;
            border-radius: 3px;
            transition: background 0.2s;
            font-family: var(--widget-font-family);
            width: 20px;
            height: 20px;
            flex-shrink: 0;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .cts-widget-close:hover {
            background: rgba(255, 255, 255, 0.2);
        }

        /* Widget content container */
        .cts-widget-content {
            display: flex;
            flex-direction: column;
            height: 100%;
            overflow: hidden;
        }

        /* Widget body */
        .cts-widget-body {
            padding: 8px 10px 10px 12px;
            color: #333;
            font-family: var(--widget-font-family);
            flex: 1;
            display: flex;
            flex-direction: column;
            min-height: 0;
        }

        /* Help section */
        .cts-widget-help {
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.3s ease;
            margin-bottom: 0;
        }

        .cts-chat-widget:hover .cts-widget-help {
            max-height: 200px;
            margin-bottom: 12px;
        }

        .cts-help-text {
            font-size: 11px;
            line-height: 1.4;
            margin-bottom: 6px;
            color: #555;
        }

        .cts-help-examples {
            margin-bottom: 6px;
        }

        .cts-help-example {
            background: #f0f0f0;
            padding: 4px 6px;
            margin: 3px 0;
            border-radius: 4px;
            font-size: 10px;
            font-style: italic;
            color: #666;
            border-left: 2px solid var(--primary-color);
        }

        .cts-help-cta {
            font-size: 11px;
            font-weight: 600;
            color: var(--primary-color);
        }

        /* Initial form */
        .cts-widget-form {
            display: flex;
            gap: 8px;
            align-items: center;
            width: 100%;
            margin: 0;
        }

        .cts-widget-input {
            flex: 1;
            min-width: 0;
            padding: 6px 10px 6px 8px;
            border: 1px solid #ddd;
            border-radius: 25px;
            font-size: 12px;
            outline: none;
            background: white;
            color: #333;
            box-shadow: inset 0 1px 3px rgba(0,0,0,0.05);
        }

        .cts-widget-input::placeholder {
            color: #999;
            font-style: italic;
            font-size: 10px;
        }

        .cts-widget-input:focus {
            border-color: var(--primary-color);
            box-shadow: 0 0 0 2px rgba(10, 106, 172, 0.1);
        }

        .cts-widget-send {
            background: var(--primary-color);
            border: none;
            padding: 6px 8px;
            border-radius: 20px;
            color: white;
            cursor: pointer;
            font-weight: 600;
            font-size: 11px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            flex-shrink: 0;
            width: 50px;
            min-width: 50px;
        }

        .cts-widget-send:hover {
            background: var(--primary-dark);
            transform: translateY(-1px);
            box-shadow: 0 4px 8px rgba(0,0,0,0.15);
        }

        .cts-widget-send:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            background: var(--primary-color);
        }

        /* Chat Interface */
        .cts-chat-interface {
            display: flex;
            width: 100%;
            height: 100%;
            background: #f8f9fa;
            font-family: var(--chat-font-family);
            position: relative;
            contain: layout style;
            overflow: hidden;
        }

        /* Sidebar */
        .cts-sidebar {
            position: absolute;
            left: 0;
            top: 0;
            height: 100%;
            width: 240px;
            z-index: 30;
            transform: translateX(-100%);
            transition: transform 0.3s ease;
            box-shadow: 2px 0 8px rgba(0,0,0,0.1);
            background-color: #e9e9e9;
            overflow-y: auto;
            padding: 10px;
            contain: layout style paint;
            pointer-events: auto;
        }

        .cts-sidebar.open {
            transform: translateX(0);
            pointer-events: auto;
        }

        /* Sidebar overlay */
        .cts-sidebar-overlay {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0, 0, 0, 0.5);
            opacity: 0;
            visibility: hidden;
            display: none;
            transition: opacity 0.3s ease, visibility 0.3s ease;
            z-index: 15;
            pointer-events: none;
        }

        .cts-sidebar-overlay.visible {
            pointer-events: auto;
            opacity: 1;
            visibility: visible;
            display: block;
        }

        .cts-chat-interface .cts-sidebar.open ~ .cts-sidebar-overlay {
            left: 240px;
            width: calc(100% - 240px);
        }

        .cts-menu-toggle {
            display: flex;
            align-items: center;
            justify-content: center;
            position: absolute;
            top: 50%;
            left: 20px;
            transform: translateY(-50%);
            z-index: 35;
            background-color: var(--primary-color);
            color: white;
            border: none;
            width: 40px;
            height: 40px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 16px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
            transition: all 0.3s ease;
        }

        .cts-menu-toggle:hover {
            background-color: var(--primary-dark);
            transform: translateY(-50%) scale(1.05);
        }

        .cts-menu-toggle.hidden {
            opacity: 0;
            visibility: hidden;
            pointer-events: none;
        }

        .cts-sidebar-content {
            width: 100%;
            height: 100%;
            overflow-y: auto;
            padding: 15px 10px;
        }

        .cts-sidebar-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }

        .cts-sidebar-content h3 {
            font-size: 14px;
            margin-bottom: 0;
            color: #262626;
            border-bottom: 2px solid #34495e;
            padding-bottom: 8px;
            font-weight: 600;
            flex: 1;
        }

        .cts-sidebar-close {
            background: none;
            border: none;
            font-size: 20px;
            cursor: pointer;
            color: #666;
            width: 30px;
            height: 30px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.3s ease;
            margin-left: 10px;
            flex-shrink: 0;
        }

        .cts-sidebar-close:hover {
            background-color: #f0f0f0;
            color: #333;
        }

        .cts-sidebar-content ul {
            list-style: none;
            padding: 0;
            margin: 0;
        }

        .cts-sidebar-content li {
            margin-bottom: 10px;
        }

        .cts-canned-prompt {
            color: #ffffff;
            text-decoration: none;
            display: block;
            padding: 12px 14px;
            background-color: var(--primary-color);
            border-radius: 6px;
            transition: all 0.3s ease;
            font-size: 12px;
            line-height: 1.4;
            min-height: 40px;
            display: flex;
            align-items: center;
        }

        .cts-canned-prompt:hover {
            background-color: var(--primary-dark);
            transform: translateY(-1px);
            box-shadow: 0 2px 6px rgba(0,0,0,0.2);
        }

        #cts-about-me-button {
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #bdc3c7;
        }

        #cts-about-me-button .cts-canned-prompt {
            background-color: var(--primary-color);
            font-weight: 600;
        }

        /* Main chat area */
        .cts-main-chat {
            flex: 1;
            display: flex;
            flex-direction: column;
            background-color: #ffffff;
            overflow: hidden;
            min-height: 0;
        }

        .cts-chat-header {
            background-color: #e9e9e9;
            color: #262626;
            flex-shrink: 0;
            padding: 15px 20px 15px 75px;
            border-bottom: 1px solid #ddd;
            position: relative;
        }

        .cts-chat-header label {
            font-size: 16px;
            font-weight: 600;
            margin: 0;
        }

        .cts-chat-messages {
            flex: 1;
            padding: 15px;
            overflow-y: auto;
            background-color: #f8f9fa;
            min-height: 0;
            overflow-x: hidden;
        }

        /* Message styles */
        .cts-message {
            margin-bottom: 15px;
            animation: fadeIn 0.3s ease;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .cts-user-message {
            display: flex;
            justify-content: flex-end;
        }

        .cts-user-message .cts-message-content {
            background-color: #0a6aac;
            color: white;
            padding: 12px 16px;
            border-radius: 18px 18px 4px 18px;
            max-width: 85%;
            word-wrap: break-word;
            font-size: 13px;
        }

        .cts-ai-message {
            display: flex;
            justify-content: flex-start;
        }

        .cts-ai-message .cts-message-content {
            background-color: #ecf0f1;
            color: #2c3e50;
            padding: 12px 16px;
            border-radius: 18px 18px 18px 4px;
            max-width: 85%;
            word-wrap: break-word;
            line-height: 1.5;
            font-size: 13px;
        }

        .cts-ai-message .cts-message-content h1,
        .cts-ai-message .cts-message-content h2,
        .cts-ai-message .cts-message-content h3 {
            margin-top: 12px;
            margin-bottom: 8px;
            color: #2c3e50;
            font-size: 14px;
        }

        .cts-ai-message .cts-message-content p {
            margin-bottom: 10px;
            line-height: 1.6;
        }

        .cts-ai-message .cts-message-content ul,
        .cts-ai-message .cts-message-content ol {
            margin-left: 16px;
            margin-bottom: 10px;
        }

        .cts-ai-message .cts-message-content code {
            background-color: #f8f9fa;
            padding: 2px 4px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            font-size: 0.85em;
            color: #e74c3c;
        }

        /* Input section */
        .cts-input-section {
            display: flex;
            flex-direction: column;
            padding: 15px;
            background-color: white;
            border-top: 1px solid #ddd;
            gap: 12px;
            align-items: stretch;
            flex-shrink: 0;
        }

        .cts-prompt-input {
            width: 100%;
            padding: 12px 14px;
            border: 2px solid #bdc3c7;
            border-radius: 6px;
            font-size: 14px;
            resize: vertical;
            min-height: 45px;
            max-height: 120px;
            outline: none;
        }

        .cts-prompt-input:focus {
            border-color: #0A6AAC;
            box-shadow: 0 0 0 3px rgba(10, 106, 172, 0.1);
        }

        .cts-ask-button {
            background-color: var(--primary-color);
            color: white;
            border: none;
            padding: 12px 20px;
            border-radius: 6px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            min-height: 45px;
            width: 100%;
        }

        .cts-ask-button:hover {
            background-color: var(--primary-dark);
            transform: translateY(-1px);
        }

        .cts-ask-button:disabled {
            background-color: #bdc3c7;
            cursor: not-allowed;
            transform: none;
        }

        /* Footer */
        .cts-embed-footer {
            background-color: #e9e9e9;
            color: #262626;
            text-align: center;
            padding: 10px;
            border-top: 1px solid #e9e9e9;
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 15px;
            flex-wrap: wrap;
            flex-shrink: 0;
            font-size: 12px;
        }

        #cts-solace-link {
            color: #262626;
            text-decoration: none;
            font-weight: 600;
            transition: color 0.3s ease;
            display: flex;
            align-items: center;
            gap: 4px;
        }

        #cts-solace-link:hover {
            color: var(--primary-color);
        }

        #cts-privacy-faq {
            font-size: 10px;
            color: #7f8c8d;
            text-decoration: none;
            cursor: pointer;
            transition: color 0.3s ease;
        }

        #cts-privacy-faq:hover {
            color: var(--primary-color);
            text-decoration: underline;
        }

        /* Loading and error states */
        .cts-loading-message {
            font-style: italic;
            color: #7f8c8d;
        }

        .cts-error-message {
            color: #e74c3c;
            font-weight: bold;
        }

        /* About Me Panel */
        .cts-about-panel {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0,0,0,0.8);
            z-index: 2147483647 !important;
            opacity: 0;
            visibility: hidden;
            transform: translateX(-100%);
            transition: transform 0.3s ease-out, opacity 0.3s ease-out, visibility 0.3s ease-out;
            border-radius: 10px;
            overflow: hidden;
            contain: layout style paint;
        }

        .cts-about-panel.visible {
            transform: translateX(0);
            opacity: 1;
            visibility: visible;
        }

        .cts-about-content {
            position: absolute;
            top: 0;
            left: 0;
            width: 85%;
            height: 100%;
            background-color: white;
            padding: 25px 20px;
            overflow-y: auto;
            box-shadow: 2px 0 15px rgba(0,0,0,0.3);
            border-right: 1px solid #ddd;
            border-radius: 10px 0 0 10px;
        }

        .cts-about-close {
            position: absolute;
            top: 15px;
            right: 15px;
            background: none;
            border: none;
            font-size: 20px;
            cursor: pointer;
            color: #666;
            width: 30px;
            height: 30px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.3s ease;
        }

        .cts-about-close:hover {
            background-color: #f0f0f0;
            color: #333;
        }

        .cts-about-content h2 {
            color: var(--primary-color);
            margin-bottom: 15px;
            font-size: 20px;
        }

        .cts-about-content p {
            margin-bottom: 12px;
            line-height: 1.6;
            color: #333;
            font-size: 14px;
        }

        .cts-examples {
            background-color: #f8f9fa;
            padding: 15px;
            border-radius: 6px;
            margin: 15px 0;
        }

        .cts-example-prompt {
            background-color: #e9ecef;
            padding: 10px;
            border-radius: 4px;
            margin: 8px 0;
            font-style: italic;
            border-left: 4px solid var(--primary-color);
        }

        /* Widget states - expanded */
        .cts-chat-widget.expanded {
            width: var(--widget-width, 450px);
            height: var(--widget-height, min(680px, calc(100vh - 80px)));
            min-width: 320px;
            min-height: 400px;
            max-width: calc(100vw - 40px);
            max-height: calc(100vh - 80px);
            overflow: hidden;
            position: fixed;
            bottom: 20px;
            right: 20px;
            left: auto;
            top: auto;
            transform-origin: bottom right;
            contain: layout style paint;
            z-index: 2147483647 !important;
            transition: width 0.3s ease, height 0.3s ease;
        }

        /* Very small screens */
        @media (max-width: 480px) {
            .cts-chat-widget {
                bottom: 10px;
                right: 10px;
                width: calc(100vw - 20px);
                max-width: calc(100vw - 20px);
            }

            .cts-chat-widget.expanded {
                width: calc(100vw - 20px);
                height: calc(100vh - 80px);
                min-width: 260px;
                min-height: 350px;
                bottom: 10px;
                right: 10px;
                left: auto;
                top: auto;
                transform-origin: bottom right;
            }

            .cts-chat-interface {
                height: 100%;
            }

            .cts-chat-header {
                padding: 12px 15px 12px 70px;
            }

            .cts-menu-toggle {
                left: 15px;
                width: 36px;
                height: 36px;
                font-size: 14px;
            }

            .cts-about-content {
                width: 95%;
                padding: 20px 15px;
            }

            .cts-input-section {
                padding: 10px;
                gap: 8px;
            }
        }

        /* Small screens */
        @media (min-width: 356px) and (max-width: 768px) {
            .cts-chat-widget {
                bottom: 15px;
                right: 15px;
                width: 270px;
                max-width: calc(100vw - 30px);
            }

            .cts-chat-widget.expanded {
                width: calc(100vw - 30px);
                height: calc(100vh - 80px);
                min-width: 280px;
                min-height: 400px;
                bottom: 15px;
                right: 15px;
                left: auto;
                top: auto;
                transform-origin: bottom right;
            }

            .cts-chat-interface {
                height: 100%;
            }

            .cts-input-section {
                padding: 10px;
                gap: 8px;
            }
        }

        /* Desktop */
        @media (min-width: 769px) {
            .cts-chat-widget.expanded {
                width: 450px;
                height: min(680px, calc(100vh - 80px));
                bottom: 20px;
                right: 20px;
                left: auto;
                top: auto;
            }
        }

        .cts-chat-widget.expanded .cts-widget-help {
            display: none;
        }

        .cts-chat-widget.expanded .cts-widget-form {
            display: none;
        }

        .cts-chat-widget.expanded .cts-chat-interface {
            display: flex;
        }

        .cts-chat-widget.expanded .cts-sidebar {
            display: block;
        }

        @media (prefers-reduced-motion: reduce) {
            .cts-chat-widget,
            .cts-chat-widget *,
            .cts-about-panel,
            .cts-about-panel * {
                animation-duration: 0.01ms;
                animation-iteration-count: 1;
                transition-duration: 0.01ms;
            }
        }

        /* --- Mobile keyboard support & viewport-safe sizing --- */
        @supports (height: 1dvh) {
          /* Use dynamic viewport units when supported */
          .cts-chat-widget.expanded {
            height: min(680px, calc(100dvh - 80px));
          }
        }

        /* Applied while the on-screen keyboard is visible */
        .cts-chat-widget.keyboard-up {
          /* --vvh is set from JS to visualViewport.height (or innerHeight fallback) */
          max-height: calc(var(--vvh, 100vh) - 20px) !important;
          /* --keyboard-bottom is set from JS to keep widget above keyboard */
          bottom: var(--keyboard-bottom, 10px) !important;
        }

        /* Make sure content remains usable when space is tight */
        .cts-chat-widget.keyboard-up .cts-chat-messages {
          overscroll-behavior: contain;
        }

        /* Respect iOS safe-area when bottom-inset exists */
        @supports (padding: env(safe-area-inset-bottom)) {
          .cts-chat-widget.keyboard-up .cts-input-section {
            padding-bottom: calc(10px + env(safe-area-inset-bottom));
          }
        }
    `;
}

// Close widget
function closeWidget() {
    if (isExpanded) {
        collapseWidget();
    } else {
        widget.style.display = 'none';
    }
}

// Handle form submission from compact widget
function handleCTSSubmit(event) {
    event.preventDefault();
    const query = queryInput.value.trim();
    if (!query) return;

    // Always expand and keep it expanded
    expandWidget();

    addMessage(query, true, '', 'user-with-loading');
    sendQuery(query);
    queryInput.value = '';
}

// Detect if we're on a very small screen
function isVerySmallScreen() {
    return window.innerWidth <= 480;
}

// Detect if we're on a mobile device
function isMobileDevice() {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) ||
           ('ontouchstart' in window) ||
           (navigator.maxTouchPoints > 0);
}

// Handle mobile keyboard visibility changes
function handleKeyboardVisibility() {
    if (!widget || !isMobileDevice()) return;

    // Store original bottom position if not already stored
    if (originalWidgetBottom === null) {
        const computedStyle = window.getComputedStyle(widget);
        originalWidgetBottom = computedStyle.bottom;
    }

    // Use Visual Viewport API if available (modern browsers)
    if (window.visualViewport) {
        const handleViewportChange = () => {
            const viewportHeight = window.visualViewport.height;
            const windowHeight = window.innerHeight;
            const keyboardHeight = windowHeight - viewportHeight;
            const keyboardIsVisible = keyboardHeight > 150; // threshold to detect keyboard

            if (keyboardIsVisible && !keyboardVisible) {
                // Keyboard appeared
                keyboardVisible = true;
                adjustWidgetForKeyboard(keyboardHeight);
            } else if (!keyboardIsVisible && keyboardVisible) {
                // Keyboard disappeared
                keyboardVisible = false;
                restoreWidgetPosition();
            }

            // Keep CSS var fresh even if state didn't flip
            if (widget) {
                widget.style.setProperty('--vvh', `${viewportHeight}px`);
            }
        };

        window.visualViewport.addEventListener('resize', handleViewportChange);
        window.visualViewport.addEventListener('scroll', handleViewportChange);
        return;
    }

    // Fallback for older browsers
    let initialViewportHeight = window.innerHeight;
    const handleResize = () => {
        const currentHeight = window.innerHeight;
        const heightDifference = initialViewportHeight - currentHeight;
        const keyboardIsVisible = heightDifference > 150; // threshold to detect keyboard

        if (keyboardIsVisible && !keyboardVisible) {
            keyboardVisible = true;
            adjustWidgetForKeyboard(heightDifference);
        } else if (!keyboardIsVisible && keyboardVisible) {
            keyboardVisible = false;
            restoreWidgetPosition();
        }
    };

    window.addEventListener('resize', handleResize);

    // Additional focus/blur detection for input elements
    const handleInputFocus = () => {
        setTimeout(() => {
            if (isMobileDevice()) {
                const currentHeight = window.innerHeight;
                const heightDifference = initialViewportHeight - currentHeight;
                if (heightDifference > 150 && !keyboardVisible) {
                    keyboardVisible = true;
                    adjustWidgetForKeyboard(heightDifference);
                }
            }
        }, 300); // delay to allow keyboard to appear
    };

    const handleInputBlur = () => {
        setTimeout(() => {
            if (keyboardVisible) {
                const currentHeight = window.innerHeight;
                const heightDifference = initialViewportHeight - currentHeight;
                if (heightDifference <= 150) {
                    keyboardVisible = false;
                    restoreWidgetPosition();
                }
            }
        }, 300);
    };

    // Add listeners to input elements
    if (queryInput) {
        queryInput.addEventListener('focus', handleInputFocus);
        queryInput.addEventListener('blur', handleInputBlur);
    }

    // Store the listener functions globally to add to expanded widget later
    window.ctsKeyboardHandlers = {
        handleInputFocus,
        handleInputBlur
    };
}

// Adjust widget position when keyboard appears
function adjustWidgetForKeyboard(keyboardHeight) {
    if (!widget) return;

    const vvp = window.visualViewport;
    const viewportHeight = vvp ? vvp.height : window.innerHeight;
    const viewportOffsetTop = vvp ? vvp.offsetTop || 0 : 0;

    // Base margin above keyboard
    const minBottomMargin = 10;

    // On some browsers (iOS Safari), the layout viewport shifts: include offsetTop
    const proposedBottom = keyboardHeight + viewportOffsetTop + minBottomMargin;

    // Keep full widget on screen
    const rect = widget.getBoundingClientRect();
    const widgetHeight = rect.height || 0;
    const maxBottom = Math.min(
        proposedBottom,
        Math.max(10, (window.innerHeight - widgetHeight - 10))
    );

    // CSS vars consumed by the CSS we added
    widget.style.setProperty('--vvh', `${viewportHeight}px`);
    widget.style.setProperty('--keyboard-bottom', `${maxBottom}px`);

    widget.classList.add('keyboard-up');
    widget.style.transition = 'bottom 0.25s ease';

    // Keep messages visible - only scroll to bottom if not within an enhanced scroll operation
    if (chatMessages && !chatMessages.hasAttribute('data-scroll-pending')) {
        // Check if we have recent AI responses that should be at the top
        const lastMessage = chatMessages.lastElementChild;
        const isAIMessage = lastMessage && lastMessage.classList.contains('cts-ai-message');

        // Only auto-scroll to bottom for user messages or if no recent AI messages
        if (!isAIMessage) {
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
    }

    // Double-check visibility of close button/header
    enforceVisibility();

    console.log(`📱 Keyboard detected → bottom: ${maxBottom}px, vvh: ${viewportHeight}px`);
}

// Restore widget to original position
function restoreWidgetPosition() {
    if (!widget) return;

    widget.classList.remove('keyboard-up');
    widget.style.removeProperty('--keyboard-bottom');
    widget.style.removeProperty('--vvh');

    // Restore original bottom if we captured it
    if (originalWidgetBottom) {
        widget.style.bottom = originalWidgetBottom;
    } else {
        widget.style.removeProperty('bottom');
    }
    widget.style.transition = 'bottom 0.25s ease';

    // Re-assert visibility constraints in case orientation changed
    enforceVisibility();

    console.log('📱 Keyboard hidden → restored widget position');
}

// Expand widget
function expandWidget() {
    if (isExpanded) return;

    isExpanded = true;
    widget.classList.add('expanded');

    if (!chatInterface) {
        createChatInterface();
    }

    if (promptInput) {
        setTimeout(() => promptInput.focus(), 300);
    }

    enforceVisibility();
}

// Create chat interface
function createChatInterface() {
    const widgetBody = widget.querySelector('.cts-widget-body');
    const chatInterfaceHTML = `
        <div id="cts-chat-interface" class="cts-chat-interface">
            <div id="cts-sidebar-overlay" class="cts-sidebar-overlay"></div>
            <div id="cts-sidebar" class="cts-sidebar">
                <div id="cts-sidebar-content" class="cts-sidebar-content">
                    <div class="cts-sidebar-header">
                        <h3 id="cts-sidebar-title">Quick Prompts</h3>
                        <button id="cts-sidebar-close" class="cts-sidebar-close" aria-label="Close sidebar">×</button>
                    </div>
                    <ul id="cts-canned-prompts-list">
                        <li><a href="#" class="cts-canned-prompt" data-prompt="Tell me about Christ the Servant Church">About Christ the Servant</a></li>
                        <li><a href="#" class="cts-canned-prompt" data-prompt="What worship services do you offer?">Worship Services</a></li>
                        <li><a href="#" class="cts-canned-prompt" data-prompt="How can I get involved in the church?">Getting Involved</a></li>
                    </ul>
                    <div id="cts-about-me-button">
                        <a href="#" class="cts-canned-prompt" id="cts-about-me-link">About Me</a>
                    </div>
                </div>
            </div>
            <div id="cts-main-chat" class="cts-main-chat">
                <div id="cts-chat-header" class="cts-chat-header">
                    <button id="cts-menu-toggle" class="cts-menu-toggle" aria-label="Toggle menu">☰</button>
                    <label for="cts-prompt-input" id="cts-chat-label">Ask CTS Assistant:</label>
                </div>
                <div id="cts-chat-messages" class="cts-chat-messages"></div>
                <div id="cts-input-section" class="cts-input-section">
                    <form id="cts-chat-form" class="cts-chat-form">
                        <textarea id="cts-prompt-input" class="cts-prompt-input" placeholder="Type your question here..." rows="2"></textarea>
                        <button type="submit" id="cts-ask-button" class="cts-ask-button">Ask</button>
                    </form>
                </div>
                <div id="cts-embed-footer" class="cts-embed-footer">
                    <a href="https://www.wearesolace.com" target="_blank" rel="noopener noreferrer" id="cts-solace-link">🌱 Powered by Solace</a>
                    <a href="mailto:support@wearesolace.com" target="_blank" rel="noopener noreferrer" id="cts-privacy-faq">Beta - Feedback and Support</a>
                    <a href="https://wearesolace.com/privacy/" target="_blank" rel="noopener noreferrer" id="cts-privacy-faq">Privacy Policy</a>
                </div>
            </div>
            <div id="cts-about-panel" class="cts-about-panel">
                <div id="cts-about-content" class="cts-about-content">
                    <button id="cts-about-close" class="cts-about-close" aria-label="Close about panel">×</button>
                    <h2>Hello, I'm CTS Assistant!</h2>
                    <p>Hello! I'm CTS Assistant, your AI helper. I can answer many kinds of questions and provide information to help you. Just type your question into the prompt and we can have a conversation about it!</p>
                    <div class="cts-examples">
                        <p><strong>Here are a couple examples of the sorts of things you can ask:</strong></p>
                        <div class="cts-example-prompt">"Tell me about Christ the Servant Church and its mission"</div>
                        <div class="cts-example-prompt">"What worship services and programs do you offer?"</div>
                    </div>
                    <p>You can also use the Quick Prompts on the left as a starting point or just to try out talking with me. Give it a go!</p>
                </div>
            </div>
        </div>
    `;

    widgetBody.querySelector('.cts-widget-help').insertAdjacentHTML('afterend', chatInterfaceHTML);

    chatInterface = shadowRoot.getElementById('cts-chat-interface');
    chatMessages = shadowRoot.getElementById('cts-chat-messages');
    promptInput = shadowRoot.getElementById('cts-prompt-input');
    askButton = shadowRoot.getElementById('cts-ask-button');
    sidebar = shadowRoot.getElementById('cts-sidebar');
    menuToggle = shadowRoot.getElementById('cts-menu-toggle');
    sidebarOverlay = shadowRoot.getElementById('cts-sidebar-overlay');
    aboutMeLink = shadowRoot.getElementById('cts-about-me-link');
    aboutPanel = shadowRoot.getElementById('cts-about-panel');
    aboutClose = shadowRoot.getElementById('cts-about-close');

    setupChatEventListeners();
}

// Collapse widget
function collapseWidget() {
    if (!isExpanded) return;

    isExpanded = false;
    widget.classList.remove('expanded');

    if (chatInterface) {
        chatInterface.remove();
        chatInterface = null;
        chatMessages = null;
        promptInput = null;
        askButton = null;
        sidebar = null;
        sidebarOverlay = null;
        menuToggle = null;
        aboutMeLink = null;
    }

    chatHistory = [];

    if (queryInput) {
        setTimeout(() => queryInput.focus(), 300);
    }

    resetWidgetPosition();
}

// Reset widget position
function resetWidgetPosition() {
    if (!widget) return;

    const style = widget.style;
    ['width', 'height', 'top', 'bottom', 'left', 'right', '--widget-width', '--widget-height'].forEach(prop => {
        style.removeProperty(prop);
    });
}

// Add message with enhanced scrolling behavior
function addMessage(message, isUser = false, messageClass = '', scrollBehavior = 'auto') {
    if (!chatMessages) return;

    const messageDiv = document.createElement('div');
    messageDiv.className = `cts-message ${isUser ? 'cts-user-message' : 'cts-ai-message'} ${messageClass}`;
    messageDiv.innerHTML = `<div class="cts-message-content">${message}</div>`;
    chatMessages.appendChild(messageDiv);

    chatHistory.push({ message, isUser, timestamp: Date.now() });

    // Enhanced scrolling logic based on message type and behavior
    if (scrollBehavior === 'user-with-loading') {
        // For user messages: scroll to show the query + space for upcoming "Thinking..." message
        chatMessages.setAttribute('data-scroll-pending', 'true');
        setTimeout(() => {
            messageDiv.scrollIntoView({ behavior: 'smooth', block: 'end' });
            setTimeout(() => chatMessages.removeAttribute('data-scroll-pending'), 300);
        }, 50); // Small delay to ensure DOM is updated
    } else if (scrollBehavior === 'ai-response') {
        // For AI responses: scroll to top of the new response
        console.log('📱 AI Response scroll - applying ai-response behavior');
        chatMessages.setAttribute('data-scroll-pending', 'true');
        setTimeout(() => {
            console.log('📱 Attempting scrollIntoView for AI response');
            // Try scrollIntoView first
            messageDiv.scrollIntoView({ behavior: 'smooth', block: 'start' });

            // Fallback: manual scroll calculation for mobile
            setTimeout(() => {
                if (isMobileDevice()) {
                    const scrollOffset = messageDiv.offsetTop - chatMessages.offsetTop;
                    console.log(`📱 Mobile fallback scroll: offset=${scrollOffset}, target=${Math.max(0, scrollOffset - 10)}`);
                    chatMessages.scrollTo({
                        top: Math.max(0, scrollOffset - 10), // 10px padding from top
                        behavior: 'smooth'
                    });
                }
                chatMessages.removeAttribute('data-scroll-pending');
            }, 100);
        }, 50);
    } else if (scrollBehavior === 'loading-visible') {
        // For loading messages: ensure they're visible below the last user message
        chatMessages.setAttribute('data-scroll-pending', 'true');
        setTimeout(() => {
            messageDiv.scrollIntoView({ behavior: 'smooth', block: 'center' });
            setTimeout(() => chatMessages.removeAttribute('data-scroll-pending'), 300);
        }, 50);
    } else if (isUser) {
        // Default user message behavior: scroll to bottom to show full query
        setTimeout(() => {
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }, 50);
    } else {
        // Default AI message behavior: scroll to start of response
        chatMessages.setAttribute('data-scroll-pending', 'true');
        setTimeout(() => {
            // Try scrollIntoView first
            messageDiv.scrollIntoView({ behavior: 'smooth', block: 'start' });

            // Fallback for mobile: manual scroll calculation
            setTimeout(() => {
                if (isMobileDevice()) {
                    const scrollOffset = messageDiv.offsetTop - chatMessages.offsetTop;
                    chatMessages.scrollTo({
                        top: Math.max(0, scrollOffset - 10), // 10px padding from top
                        behavior: 'smooth'
                    });
                }
                chatMessages.removeAttribute('data-scroll-pending');
            }, 100);
        }, 50);
    }

    return messageDiv;
}

// Send query to API
function sendQuery(query = null) {
    if (!isExpanded) return;

    if (!query) {
        query = promptInput.value.trim();
        if (!query) {
            promptInput.focus();
            return;
        }
        addMessage(query, true, '', 'user-with-loading');
        promptInput.value = '';
    }

    promptInput.disabled = true;
    askButton.disabled = true;
    askButton.textContent = 'Thinking...';

    const loadingMessage = addMessage('Thinking...', false, 'cts-loading-message', 'loading-visible');

    // Auto-detect API endpoint based on environment
    const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
    const apiEndpoint = isLocal
        ? 'http://localhost:5000/query'
        : 'http://multitenant-rag-dev.eba-jpwpckan.us-east-1.elasticbeanstalk.com/query';

    fetch(apiEndpoint, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-Tenant-ID': 'cts'
        },
        body: JSON.stringify({ query }),
        keepalive: true
    })
    .then(response => {
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        return response.json();
    })
    .then(data => {
        if (loadingMessage.parentNode) chatMessages.removeChild(loadingMessage);

        if (!data.success || data.error) {
            addMessage(`Error: ${data.error || 'Unknown error'}`, false, 'cts-error-message', 'ai-response');
        } else if (data.success && data.answer) {
            addMessage(parseMarkdown(data.answer), false, '', 'ai-response');
        } else {
            addMessage('Unexpected response format.', false, 'cts-error-message', 'ai-response');
        }
    })
    .catch(() => {
        if (loadingMessage.parentNode) chatMessages.removeChild(loadingMessage);
        addMessage('Error processing request. Please try again.', false, 'cts-error-message', 'ai-response');
    })
    .finally(() => {
        promptInput.disabled = false;
        askButton.disabled = false;
        askButton.textContent = 'Ask';
        promptInput.focus();
    });
}

// Parse markdown
function parseMarkdown(text) {
    if (!text) return '';
    return text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/`(.*?)`/g, '<code>$1</code>')
        .replace(/\n\n/g, '<br><br>')
        .replace(/\n/g, '<br>');
}

// Mobile menu
function toggleMobileMenu() {
    if (sidebar && sidebarOverlay && menuToggle) {
        const isOpen = sidebar.classList.contains('open');
        if (isOpen) {
            closeMobileMenu();
        } else {
            sidebar.classList.add('open');
            sidebarOverlay.classList.add('visible');
            menuToggle.classList.add('hidden');
        }
    }
}

function closeMobileMenu() {
    if (sidebar && sidebarOverlay && menuToggle) {
        sidebar.classList.remove('open');
        sidebarOverlay.classList.remove('visible');
        menuToggle.classList.remove('hidden');
    }
}

// About panel
function showAboutPanel() {
    if (aboutPanel) {
        aboutPanel.style.display = 'block';
        aboutPanel.style.opacity = '1';
        aboutPanel.style.visibility = 'visible';
        aboutPanel.offsetHeight;
        aboutPanel.classList.add('visible');
        setTimeout(() => aboutClose?.focus(), 100);
    }
}

function hideAboutPanel() {
    if (aboutPanel) {
        aboutPanel.classList.remove('visible');
        setTimeout(() => {
            if (!aboutPanel.classList.contains('visible')) {
                aboutPanel.style.display = 'none';
                aboutPanel.style.opacity = '0';
                aboutPanel.style.visibility = 'hidden';
            }
        }, 300);
        aboutMeLink?.focus();
    }
}

// Enforce visibility with close button accessibility
function enforceVisibility() {
    if (!widget) return;

    const rect = widget.getBoundingClientRect();
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;

    // Define safe margins to ensure close button accessibility
    const safeMarginTop = 10; // ensure close button not cut off by browser chrome
    const safeMarginRight = 10;
    const safeMarginBottom = 20;
    const safeMarginLeft = 10;

    let needsAdjustment = false;
    const style = widget.style;

    // Check if widget extends beyond viewport boundaries
    if (rect.top < safeMarginTop ||
        rect.bottom > (viewportHeight - safeMarginBottom) ||
        rect.left < safeMarginLeft ||
        rect.right > (viewportWidth - safeMarginRight)) {

        console.log('⚠️ Widget not fully visible, adjusting position...');
        needsAdjustment = true;
    }

    if (needsAdjustment) {
        // Reset positioning to safe defaults
        style.bottom = isVerySmallScreen() ? '10px' : '20px';
        style.right = isVerySmallScreen() ? '10px' : '20px';
        style.left = 'auto';
        style.top = 'auto';

        // Adjust width to ensure it fits within viewport with safe margins
        const maxWidgetWidth = viewportWidth - (safeMarginLeft + safeMarginRight);

        if (isVerySmallScreen()) {
            style.width = `${Math.min(maxWidgetWidth, viewportWidth - 20)}px`;
            style.maxWidth = `${maxWidgetWidth}px`;
        } else {
            const defaultWidth = isExpanded ? 450 : 270;
            const constrainedWidth = Math.min(defaultWidth, maxWidgetWidth);
            style.width = `${constrainedWidth}px`;
            style.maxWidth = `${maxWidgetWidth}px`;
        }

        // Ensure height constraints for expanded widget
        if (isExpanded) {
            const maxWidgetHeight = viewportHeight - (safeMarginTop + safeMarginBottom);
            style.maxHeight = `${maxWidgetHeight}px`;
        }

        console.log(`✅ Widget repositioned within safe boundaries: ${style.width} x ${style.maxHeight || 'auto'}`);
    }
}

// Event listeners
function setupChatEventListeners() {
    const chatForm = shadowRoot.getElementById('cts-chat-form');
    if (chatForm) {
        chatForm.addEventListener('submit', (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (e.stopImmediatePropagation) e.stopImmediatePropagation();
            sendQuery();
        }, { capture: true });
    }

    if (askButton) {
        askButton.addEventListener('click', () => sendQuery());
    }

    if (promptInput) {
        promptInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
                e.preventDefault();
                e.stopPropagation();
                if (e.stopImmediatePropagation) e.stopImmediatePropagation();
                sendQuery();
            }
        }, { capture: true });

        // Add keyboard visibility handlers for mobile
        if (window.ctsKeyboardHandlers && isMobileDevice()) {
            promptInput.addEventListener('focus', window.ctsKeyboardHandlers.handleInputFocus);
            promptInput.addEventListener('blur', window.ctsKeyboardHandlers.handleInputBlur);
        }
    }

    if (menuToggle) {
        menuToggle.addEventListener('click', toggleMobileMenu);
    }

    if (sidebarOverlay) {
        sidebarOverlay.addEventListener('click', e => {
            if (e.target === sidebarOverlay) closeMobileMenu();
        });
    }

    const sidebarClose = shadowRoot.getElementById('cts-sidebar-close');
    if (sidebarClose) {
        sidebarClose.addEventListener('click', closeMobileMenu);
    }

    if (aboutMeLink) {
        aboutMeLink.addEventListener('click', e => {
            e.preventDefault();
            showAboutPanel();
        });
    }

    if (aboutClose) {
        aboutClose.addEventListener('click', hideAboutPanel);
    }

    if (aboutPanel) {
        aboutPanel.addEventListener('click', e => {
            if (e.target === aboutPanel) hideAboutPanel();
        });
    }

    const cannedPrompts = shadowRoot.querySelectorAll('#cts-chat-interface .cts-canned-prompt');
    cannedPrompts.forEach(link => {
        if (link.id === 'cts-about-me-link') return;
        link.addEventListener('click', e => {
            e.preventDefault();
            const prompt = link.getAttribute('data-prompt');
            if (prompt) handleCannedPrompt(prompt);
        });
    });
}

// Handle canned prompts
function handleCannedPrompt(prompt) {
    if (!isExpanded) expandWidget();
    if (promptInput) {
        promptInput.value = prompt;
        promptInput.focus();
    }
    closeMobileMenu();
}

// Initialize widget
document.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 CTS Widget: DOM loaded, initializing...');

    if (!initializeShadowDOM()) {
        console.error('❌ Failed to initialize Shadow DOM.');
        return;
    }

    widget = shadowRoot.getElementById('ctsChatWidgetInner');
    queryInput = shadowRoot.getElementById('ctsQueryInput');

    if (!widget) {
        console.error('CTS widget not found');
        return;
    }

    const compactForm = shadowRoot.getElementById('ctsWidgetForm');
    if (compactForm) {
        compactForm.addEventListener('submit', (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (e.stopImmediatePropagation) e.stopImmediatePropagation();
            handleCTSSubmit(e);
        }, { capture: true });
    }

    if (queryInput && compactForm) {
        queryInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                e.stopPropagation();
                if (e.stopImmediatePropagation) e.stopImmediatePropagation();
                if (typeof compactForm.requestSubmit === 'function') {
                    compactForm.requestSubmit();
                } else {
                    const submitEvent = new Event('submit', { bubbles: true, cancelable: true });
                    compactForm.dispatchEvent(submitEvent);
                }
            }
        }, { capture: true });
    }

    const closeButton = shadowRoot.getElementById('cts-widget-close-btn');
    if (closeButton) {
        closeButton.addEventListener('click', closeWidget);
    }

    shadowRoot.addEventListener('keydown', e => {
        if (e.key === 'Escape') {
            if (aboutPanel && aboutPanel.classList.contains('visible')) {
                hideAboutPanel();
            } else if (sidebar && sidebar.classList.contains('open')) {
                closeMobileMenu();
            } else if (isExpanded) {
                collapseWidget();
            }
        }
    });

    let resizeTimeout;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(() => {
            if (window.innerWidth >= 768) closeMobileMenu();
            if (isExpanded) enforceVisibility();
            enforceContainerStyles();
        }, 250);
    });

    setInterval(enforceContainerStyles, 1000);

    // Initialize keyboard visibility handling for mobile devices
    handleKeyboardVisibility();

    runHealthCheck();
});

// Health check
function runHealthCheck() {
    console.log('🏥 Running CTS Widget Health Check...');

    let containerStyles = {};
    let widgetStyles = {};
    let widgetBounds = {};

    if (widgetContainer) {
        const computedStyle = window.getComputedStyle(widgetContainer);
        containerStyles = {
            zIndex: computedStyle.zIndex,
            position: computedStyle.position
        };
    }

    if (widget) {
        const computedStyle = window.getComputedStyle(widget);
        const rect = widget.getBoundingClientRect();
        widgetStyles = {
            position: computedStyle.position,
            left: computedStyle.left,
            top: computedStyle.top,
            right: computedStyle.right,
            bottom: computedStyle.bottom,
            width: computedStyle.width,
            height: computedStyle.height
        };
        widgetBounds = {
            left: rect.left,
            top: rect.top,
            right: rect.right,
            bottom: rect.bottom,
            width: rect.width,
            height: rect.height
        };
    }

    console.table({
        timestamp: new Date().toISOString(),
        userAgent: navigator.userAgent,
        location: window.location.href,
        shadowDOMSupport: !!HTMLElement.prototype.attachShadow,
        shadowRootExists: !!shadowRoot,
        widgetContainerExists: !!document.getElementById('ctsChatWidget'),
        widgetInitialized: !!widget,
        isExpanded,
        containerStyles,
        widgetStyles,
        widgetBounds,
        viewport: { width: window.innerWidth, height: window.innerHeight }
    });
}

// Export functions
window.ctsWidget = {
    close: closeWidget,
    submit: handleCTSSubmit,
    expand: expandWidget,
    collapse: collapseWidget,
    isExpanded: () => isExpanded,
    getShadowRoot: () => shadowRoot
};
