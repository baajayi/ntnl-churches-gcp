class SolaceAIWidget extends HTMLElement {
    constructor() {
        super();
        this.attachShadow({ mode: 'open' });
        // Auto-detect API endpoint based on environment
        const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
        const defaultEndpoint = isLocal
            ? 'http://localhost:5000/query'
            : 'http://multitenant-rag-dev.eba-jpwpckan.us-east-1.elasticbeanstalk.com/query';
        // Configurable API endpoint with auto-detect fallback
        this.apiEndpoint = this.getAttribute('api-endpoint') || defaultEndpoint;
        this.tenantId = this.getAttribute('tenant-id') || 'cts';
        this.widgetTitle = this.getAttribute('widget-title') || 'Ask CTS Assistant:';
        this.aboutTitle = this.getAttribute('about-title') || 'Hello, I\'m CTS Assistant!';
    }

    static get observedAttributes() {
        return ['api-endpoint', 'tenant-id', 'widget-title', 'about-title'];
    }

    attributeChangedCallback(name, oldValue, newValue) {
        if (oldValue !== newValue) {
            switch (name) {
                case 'api-endpoint':
                    const isLocal = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';
                    const defaultEndpoint = isLocal
                        ? 'http://localhost:5000/query'
                        : 'http://multitenant-rag-dev.eba-jpwpckan.us-east-1.elasticbeanstalk.com/query';
                    this.apiEndpoint = newValue || defaultEndpoint;
                    break;
                case 'tenant-id':
                    this.tenantId = newValue || 'cts';
                    break;
                case 'widget-title':
                    this.widgetTitle = newValue || 'Ask CTS Assistant:';
                    this.updateWidgetTitle();
                    break;
                case 'about-title':
                    this.aboutTitle = newValue || 'Hello, I\'m CTS Assistant!';
                    this.updateAboutTitle();
                    break;
            }
        }
    }

    connectedCallback() {
        try {
            this.render();
            this.setupEventListeners();
            this.checkForQueryParameter();
        } catch (error) {
            console.error('Widget initialization error:', error);
            this.renderErrorState();
        }
    }

    disconnectedCallback() {
        // Clean up global event listeners
        if (this.keydownHandler) {
            document.removeEventListener('keydown', this.keydownHandler);
        }
        if (this.resizeHandler) {
            window.removeEventListener('resize', this.resizeHandler);
        }
    }

    render() {
        this.shadowRoot.innerHTML = `
            <style>
                /* Mobile-First Responsive Design for CTS Embed */
                /* Reset and base styles */
                * {
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }

                /* Mobile-first base styles (320px+) */
                :host {
                    font-family: 'Figtree', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
                    background-color: #f8f9fa;
                    font-size: clamp(14px, 4vw, 16px);
                    line-height: 1.5;
                    display: block;
                    height: 600px;
                    width: 100%;
                    max-width: 100%;
                    border-radius: 8px;
                    overflow: hidden;
                    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                    position: relative;
                    z-index: 1;
                }

                /* Import Figtree font */
                @import url('https://fonts.googleapis.com/css2?family=Figtree:wght@300;400;500;600;700&display=swap');

                /* Main container - mobile first */
                #ai-assistant-container {
                    display: flex;
                    flex-direction: column;
                    height: 100%;
                    position: relative;
                    background-color: #ffffff;
                }

                /* Mobile menu toggle button */
                #menu-toggle {
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    background-color: #0A6AAC;
                    color: white;
                    border: none;
                    width: 40px;
                    height: 40px;
                    border-radius: 8px;
                    cursor: pointer;
                    font-size: 16px;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.2);
                    transition: all 0.3s ease;
                    margin-right: 15px;
                    flex-shrink: 0;
                }

                #menu-toggle:hover {
                    background-color: #124264;
                    transform: scale(1.05);
                }

                #menu-toggle.hidden {
                    opacity: 0;
                    visibility: hidden;
                    pointer-events: none;
                }

                /* Sidebar - mobile first (hidden by default) */
                #sidebar {
                    position: absolute;
                    top: 0;
                    left: -280px;
                    width: 280px;
                    height: 100%;
                    background-color: #e9e9e9;
                    padding: 70px 20px 20px;
                    overflow-y: auto;
                    z-index: 3;
                    transition: left 0.3s ease;
                    box-shadow: 2px 0 10px rgba(0,0,0,0.1);
                }

                #sidebar.open {
                    left: 0;
                }

                /* Sidebar overlay for mobile */
                #sidebar-overlay {
                    position: absolute;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 100%;
                    background-color: rgba(0,0,0,0.5);
                    z-index: 2;
                    opacity: 0;
                    visibility: hidden;
                    transition: all 0.3s ease;
                }

                #sidebar-overlay.visible {
                    opacity: 1;
                    visibility: visible;
                }

                .sidebar-header {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 20px;
                }

                #sidebar-title {
                    font-size: clamp(16px, 5vw, 18px);
                    margin-bottom: 0;
                    color: #262626;
                    border-bottom: 2px solid #34495e;
                    padding-bottom: 10px;
                    font-weight: 600;
                    flex: 1;
                }

                .sidebar-close {
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

                .sidebar-close:hover {
                    background-color: #f0f0f0;
                    color: #333;
                }

                #canned-prompts-list {
                    list-style: none;
                }

                #canned-prompts-list li {
                    margin-bottom: 12px;
                }

                .canned-prompt {
                    color: #ffffff;
                    text-decoration: none;
                    display: block;
                    padding: 14px 16px;
                    background-color: #0A6AAC;
                    border-radius: 8px;
                    transition: all 0.3s ease;
                    font-size: clamp(13px, 3.5vw, 14px);
                    line-height: 1.4;
                    min-height: 44px;
                    display: flex;
                    align-items: center;
                    cursor: pointer;
                }

                .canned-prompt:hover {
                    background-color: #124264;
                    transform: translateY(-1px);
                    box-shadow: 0 2px 8px rgba(0,0,0,0.2);
                }

                /* About Me button */
                #about-me-button {
                    margin-top: 20px;
                    padding-top: 20px;
                    border-top: 1px solid #bdc3c7;
                }

                #about-me-button .canned-prompt {
                    background-color: #0A6AAC;
                    font-weight: 600;
                }

                #about-me-button .canned-prompt:hover {
                    background-color: #124264;
                }

                /* Main chat area - mobile first */
                #main-chat {
                    flex: 1;
                    display: flex;
                    flex-direction: column;
                    background-color: #ffffff;
                    margin-left: 0;
                    overflow-y: auto;
                    max-height: 100%;
                    transition: margin-left 0.3s ease;
                }

                #chat-header {
                    background-color: #e9e9e9;
                    color: #262626;
                    flex-shrink: 0;
                    padding: 15px 20px;
                    border-bottom: 1px solid #ddd;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    position: relative;
                }

                #chat-label {
                    font-size: clamp(16px, 5vw, 18px);
                    font-weight: 600;
                    flex: 1;
                    text-align: center;
                }

                #chat-messages {
                    flex: 1;
                    padding: 15px 15px 3em;
                    overflow-y: auto;
                    background-color: #f8f9fa;
                    min-height: 0;
                    overflow-x: hidden;
                }

                .message {
                    margin-bottom: 15px;
                    animation: fadeIn 0.3s ease;
                }

                @keyframes fadeIn {
                    from { opacity: 0; transform: translateY(10px); }
                    to { opacity: 1; transform: translateY(0); }
                }

                .user-message {
                    display: flex;
                    justify-content: flex-end;
                }

                .user-message .message-content {
                    background-color: #0A6AAC;
                    color: white;
                    padding: 12px 16px;
                    border-radius: 18px 18px 4px 18px;
                    max-width: 85%;
                    word-wrap: break-word;
                    font-size: clamp(13px, 3.5vw, 14px);
                }

                .ai-message {
                    display: flex;
                    justify-content: flex-start;
                }

                .ai-message .message-content {
                    background-color: #ecf0f1;
                    color: #2c3e50;
                    padding: 12px 16px;
                    border-radius: 18px 18px 18px 4px;
                    max-width: 85%;
                    word-wrap: break-word;
                    line-height: 1.5;
                    font-size: clamp(13px, 3.5vw, 14px);
                }

                /* Markdown styling for AI responses */
                .ai-message .message-content h1,
                .ai-message .message-content h2,
                .ai-message .message-content h3 {
                    margin-top: 12px;
                    margin-bottom: 8px;
                    color: #2c3e50;
                    font-size: clamp(14px, 4vw, 16px);
                }

                .ai-message .message-content p {
                    margin-bottom: 10px;
                    line-height: 1.6;
                }

                .ai-message .message-content ul,
                .ai-message .message-content ol {
                    margin-left: 16px;
                    margin-bottom: 10px;
                }

                .ai-message .message-content code {
                    background-color: #f8f9fa;
                    padding: 2px 4px;
                    border-radius: 3px;
                    font-family: 'Courier New', monospace;
                    font-size: 0.85em;
                    color: #e74c3c;
                }

                /* Input section - mobile optimized */
                #input-section {
                    display: flex;
                    flex-direction: column;
                    padding: 15px;
                    flex-shrink: 0;
                    background-color: white;
                    border-top: 1px solid #ddd;
                    gap: 12px;
                }

                #prompt-input {
                    width: 100%;
                    padding: 14px 16px;
                    border: 2px solid #bdc3c7;
                    border-radius: 8px;
                    font-size: clamp(14px, 4vw, 16px);
                    font-family: inherit;
                    resize: vertical;
                    min-height: 50px;
                    max-height: 120px;
                }

                #prompt-input:focus {
                    outline: none;
                    border-color: #0A6AAC;
                    box-shadow: 0 0 0 3px rgba(10, 106, 172, 0.1);
                }

                #ask-button {
                    background-color: #0A6AAC;
                    color: white;
                    border: none;
                    padding: 14px 24px;
                    border-radius: 8px;
                    font-size: clamp(14px, 4vw, 16px);
                    font-weight: 600;
                    cursor: pointer;
                    transition: all 0.3s ease;
                    min-height: 44px;
                    width: 100%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    text-align: center;
                }

                #ask-button:hover {
                    background-color: #124264;
                    transform: translateY(-1px);
                }

                #ask-button:disabled {
                    background-color: #bdc3c7;
                    cursor: not-allowed;
                    transform: none;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    text-align: center;
                }

                /* About Me Panel */
                #about-panel {
                    position: absolute;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 100%;
                    background-color: rgba(0,0,0,0.8);
                    z-index: 4;
                    opacity: 0;
                    visibility: hidden;
                    transition: all 0.3s ease;
                }

                #about-panel.visible {
                    opacity: 1;
                    visibility: visible;
                }

                #about-content {
                    position: absolute;
                    top: 0;
                    left: 0;
                    width: 85%;
                    height: 100%;
                    background-color: white;
                    padding: 30px 25px;
                    overflow-y: auto;
                    transform: translateX(-100%);
                    transition: transform 0.3s ease;
                    box-shadow: 2px 0 20px rgba(0,0,0,0.3);
                    border-right: 1px solid #ddd;
                }

                #about-panel.visible #about-content {
                    transform: translateX(0);
                }

                #about-close {
                    position: absolute;
                    top: 15px;
                    right: 15px;
                    background: none;
                    border: none;
                    font-size: 24px;
                    cursor: pointer;
                    color: #666;
                    width: 35px;
                    height: 35px;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    transition: all 0.3s ease;
                }

                #about-close:hover {
                    background-color: #f0f0f0;
                    color: #333;
                }

                #about-content h2 {
                    color: #0A6AAC;
                    margin-bottom: 20px;
                    font-size: clamp(18px, 6vw, 24px);
                }

                #about-content p {
                    margin-bottom: 15px;
                    line-height: 1.6;
                    color: #333;
                    font-size: clamp(14px, 4vw, 16px);
                }

                #about-content .examples {
                    background-color: #f8f9fa;
                    padding: 20px;
                    border-radius: 8px;
                    margin: 20px 0;
                }

                #about-content .example-prompt {
                    background-color: #e9ecef;
                    padding: 12px;
                    border-radius: 6px;
                    margin: 10px 0;
                    font-style: italic;
                    border-left: 4px solid #0A6AAC;
                }

                /* Footer */
                #embed-footer {
                    background-color: #e9e9e9;
                    color: #262626;
                    text-align: center;
                    padding: 1em;
                    flex-shrink: 0;
                    border-top: 1px solid #e9e9e9;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    gap: 20px;
                    flex-wrap: wrap;
                    min-height: 40px;
                }

                #solace-link {
                    color: #262626;
                    text-decoration: none;
                    font-size: clamp(13px, 3.5vw, 14px);
                    font-weight: 600;
                    transition: color 0.3s ease;
                    display: flex;
                    align-items: center;
                    gap: 4px;
                }

                #solace-link:hover {
                    color: #0A6AAC;
                }

                #solace-privacy-faq {
                    font-size: clamp(10px, 2.5vw, 11px);
                    color: #7f8c8d;
                    text-decoration: none;
                    transition: color 0.3s ease;
                }

                #solace-privacy-faq:hover {
                    color: #0A6AAC;
                }

                /* Loading and error states */
                .loading-message {
                    font-style: italic;
                    color: #7f8c8d;
                }

                .error-message {
                    color: #e74c3c;
                    font-weight: bold;
                }

                /* Tablet breakpoint (768px+) */
                @media (min-width: 768px) {
                    #menu-toggle {
                        display: none;
                    }

                    #ai-assistant-container {
                        flex-direction: row;
                    }

                    #sidebar {
                        position: static;
                        width: 300px;
                        height: 100%;
                        padding: 20px;
                        left: 0;
                        box-shadow: none;
                    }

                    #sidebar-overlay {
                        display: none;
                    }

                    .sidebar-close {
                        display: none;
                    }

                    #input-section {
                        flex-direction: row;
                        padding: 20px;
                    }

                    #ask-button {
                        width: auto;
                        min-width: 100px;
                    }

                    #chat-header {
                        padding: 15px 20px;
                        flex-shrink: 0;
                    }

                    #chat-messages {
                        padding: 20px;
                    }

                    .user-message .message-content,
                    .ai-message .message-content {
                        max-width: 80%;
                    }

                    #about-content {
                        width: 80%;
                        padding: 40px;
                    }
                }

                /* Desktop breakpoint (1024px+) */
                @media (min-width: 1024px) {
                    #sidebar {
                        width: 320px;
                    }

                    .sidebar-close {
                        display: none;
                    }

                    .user-message .message-content,
                    .ai-message .message-content {
                        max-width: 75%;
                    }

                    #about-content {
                        width: 70%;
                        max-width: 500px;
                        padding: 50px;
                    }
                }

                /* Reduced motion preference */
                @media (prefers-reduced-motion: reduce) {
                    * {
                        animation-duration: 0.01ms !important;
                        animation-iteration-count: 1 !important;
                        transition-duration: 0.01ms !important;
                    }
                }
            </style>

            <!-- Sidebar overlay for mobile -->
            <div id="sidebar-overlay"></div>

            <div id="ai-assistant-container">
                <!-- Left sidebar with canned prompts -->
                <div id="sidebar">
                    <div class="sidebar-header">
                        <h3 id="sidebar-title">Quick Prompts</h3>
                        <button id="sidebar-close" class="sidebar-close" aria-label="Close sidebar">×</button>
                    </div>
                    <ul id="canned-prompts-list">
                        <li>
                            <a href="#" class="canned-prompt"
                               data-prompt="Tell me about Christ the Servant Church">
                                About Christ the Servant
                            </a>
                        </li>
                        <li>
                            <a href="#" class="canned-prompt"
                               data-prompt="What worship services do you offer?">
                                Worship Services
                            </a>
                        </li>
                        <li>
                            <a href="#" class="canned-prompt"
                               data-prompt="How can I get involved in the church?">
                                Getting Involved
                            </a>
                        </li>
                    </ul>

                    <!-- About Me button -->
                    <div id="about-me-button">
                        <a href="#" class="canned-prompt" id="about-me-link">
                            About Me
                        </a>
                    </div>
                </div>

                <!-- Main chat interface -->
                <div id="main-chat">
                    <div id="chat-header">
                        <button id="menu-toggle" aria-label="Toggle menu">☰</button>
                        <label for="prompt-input" id="chat-label">${this.widgetTitle}</label>
                    </div>

                    <div id="chat-messages">
                        <!-- Chat messages will appear here -->
                    </div>

                    <div id="input-section">
                        <textarea id="prompt-input" placeholder="Type your question here..." rows="3"></textarea>
                        <button id="ask-button">Ask</button>
                    </div>

                    <div id="embed-footer">
                        <a href="https://www.wearesolace.com" target="_blank" rel="noopener noreferrer" id="solace-link">
                            🌱 Powered by Solace
                        </a>
                        <a href="mailto:support@wearesolace.com" target="_blank" rel="noopener noreferrer" id="solace-privacy-faq">Beta - Feedback and Support</a>
                        <a href="https://wearesolace.com/privacy/" target="_blank" rel="noopener noreferrer" id="solace-privacy-faq">Privacy Policy</a>
                    </div>
                </div>

                <!--  Panel - Inside Container for Proper Containment -->
                <div id="about-panel">
                    <div id="about-content">
                        <button id="about-close" aria-label="Close about panel">×</button>
                        <h2 id="about-title">${this.aboutTitle}</h2>
                        <p>Hello! I'm CTS Assistant, your AI helper. I can answer many kinds of questions and provide information to help you. Just type your question into the prompt and we can have a conversation about it!</p>

                        <div class="examples">
                            <p><strong>Here are a couple examples of the sorts of things you can ask:</strong></p>

                            <div class="example-prompt">
                                "Tell me about Christ the Servant Church and its mission"
                            </div>

                            <div class="example-prompt">
                                "What worship services and programs do you offer?"
                            </div>
                        </div>

                        <p>You can also use the Quick Prompts on the left as a starting point or just to try out talking with me. Give it a go!</p>
                    </div>
                </div>
            </div>
        `;
    }

    setupEventListeners() {
        // Get elements from shadow DOM
        const menuToggle = this.shadowRoot.getElementById('menu-toggle');
        const sidebar = this.shadowRoot.getElementById('sidebar');
        const sidebarOverlay = this.shadowRoot.getElementById('sidebar-overlay');
        const aboutPanel = this.shadowRoot.getElementById('about-panel');
        const aboutClose = this.shadowRoot.getElementById('about-close');
        const aboutMeLink = this.shadowRoot.getElementById('about-me-link');
        const promptInput = this.shadowRoot.getElementById('prompt-input');
        const askButton = this.shadowRoot.getElementById('ask-button');
        const chatMessages = this.shadowRoot.getElementById('chat-messages');

        // Mobile menu functionality
        if (menuToggle) {
            menuToggle.addEventListener('click', () => this.toggleMobileMenu());
        }

        if (sidebarOverlay) {
            sidebarOverlay.addEventListener('click', () => this.closeMobileMenu());
        }

        // Sidebar close button
        const sidebarClose = this.shadowRoot.getElementById('sidebar-close');
        if (sidebarClose) {
            sidebarClose.addEventListener('click', () => this.closeMobileMenu());
        }

        // About Me panel functionality
        if (aboutMeLink) {
            aboutMeLink.addEventListener('click', (e) => {
                e.preventDefault();
                this.showAboutPanel();
                this.closeMobileMenu();
            });
        }

        if (aboutClose) {
            aboutClose.addEventListener('click', () => this.hideAboutPanel());
        }

        if (aboutPanel) {
            aboutPanel.addEventListener('click', (e) => {
                if (e.target === aboutPanel) {
                    this.hideAboutPanel();
                }
            });
        }

        // Keyboard navigation with proper cleanup
        this.keydownHandler = (e) => {
            if (e.key === 'Escape') {
                if (aboutPanel.classList.contains('visible')) {
                    this.hideAboutPanel();
                } else if (sidebar.classList.contains('open')) {
                    this.closeMobileMenu();
                }
            }
        };
        document.addEventListener('keydown', this.keydownHandler);

        // Handle window resize - close mobile menu if window becomes large
        this.resizeHandler = () => {
            if (window.innerWidth >= 768) {
                this.closeMobileMenu();
            }
        };
        window.addEventListener('resize', this.resizeHandler);

        // Canned prompt functionality
        this.shadowRoot.querySelectorAll('.canned-prompt').forEach(link => {
            if (link.id === 'about-me-link') return;

            link.addEventListener('click', (e) => {
                e.preventDefault();
                const prompt = link.getAttribute('data-prompt');
                if (prompt) {
                    promptInput.value = prompt;
                    this.closeMobileMenu();
                    promptInput.focus();
                }
            });
        });

        // Chat functionality
        if (askButton) {
            askButton.addEventListener('click', (e) => {
                e.preventDefault();
                this.sendQuery();
            });
        }

        if (promptInput) {
            promptInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendQuery();
                }
            });
        }
    }

    toggleMobileMenu() {
        const sidebar = this.shadowRoot.getElementById('sidebar');
        const sidebarOverlay = this.shadowRoot.getElementById('sidebar-overlay');
        const menuToggle = this.shadowRoot.getElementById('menu-toggle');
        const isOpen = sidebar.classList.contains('open');

        if (isOpen) {
            this.closeMobileMenu();
        } else {
            sidebar.classList.add('open');
            sidebarOverlay.classList.add('visible');
            if (menuToggle) {
                menuToggle.classList.add('hidden');
            }
        }
    }

    closeMobileMenu() {
        const sidebar = this.shadowRoot.getElementById('sidebar');
        const sidebarOverlay = this.shadowRoot.getElementById('sidebar-overlay');
        const menuToggle = this.shadowRoot.getElementById('menu-toggle');

        sidebar.classList.remove('open');
        sidebarOverlay.classList.remove('visible');
        if (menuToggle) {
            menuToggle.classList.remove('hidden');
        }
    }

    showAboutPanel() {
        const aboutPanel = this.shadowRoot.getElementById('about-panel');
        const aboutClose = this.shadowRoot.getElementById('about-close');
        aboutPanel.classList.add('visible');
        aboutClose.focus();
    }

    hideAboutPanel() {
        const aboutPanel = this.shadowRoot.getElementById('about-panel');
        const aboutMeLink = this.shadowRoot.getElementById('about-me-link');
        aboutPanel.classList.remove('visible');
        aboutMeLink.focus();
    }

    addMessage(message, isUser = false, messageClass = '') {
        const chatMessages = this.shadowRoot.getElementById('chat-messages');
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${isUser ? 'user-message' : 'ai-message'} ${messageClass}`;
        messageDiv.innerHTML = `<div class="message-content">${message}</div>`;
        chatMessages.appendChild(messageDiv);

        return messageDiv;
    }

    async sendQuery() {
        const promptInput = this.shadowRoot.getElementById('prompt-input');
        const askButton = this.shadowRoot.getElementById('ask-button');
        const chatMessages = this.shadowRoot.getElementById('chat-messages');

        if (!promptInput || !askButton || !chatMessages) {
            console.error('Critical elements missing');
            return;
        }

        const query = promptInput.value.trim();

        if (!query) {
            promptInput.focus();
            return;
        }

        // Add user message
        const userMessage = this.addMessage(query, true);

        // Scroll to show the new user message
        setTimeout(() => {
            if (userMessage && chatMessages) {
                const messageTop = userMessage.offsetTop;
                const scrollPosition = Math.max(0, messageTop - 20);
                chatMessages.scrollTo({
                    top: scrollPosition,
                    behavior: 'smooth'
                });
            }
        }, 50);

        // Clear input and disable button
        promptInput.value = '';
        askButton.disabled = true;
        askButton.textContent = 'Thinking...';

        // Show loading
        const loadingMessage = this.addMessage('Thinking...', false, 'loading-message');

        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 second timeout

            const response = await fetch(this.apiEndpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Tenant-ID': this.tenantId
                },
                body: JSON.stringify({ query: query }),
                signal: controller.signal
            });

            clearTimeout(timeoutId);

            if (!response.ok) {
                if (response.status === 429) {
                    throw new Error('Rate limit exceeded. Please wait a moment and try again.');
                } else if (response.status >= 500) {
                    throw new Error('Server error. Please try again later.');
                } else {
                    throw new Error(`Request failed with status ${response.status}`);
                }
            }

            const data = await response.json();

            // Remove loading message
            if (loadingMessage && loadingMessage.parentNode) {
                chatMessages.removeChild(loadingMessage);
            }

            if (!data.success || data.error) {
                this.addMessage(`Error: ${data.error || 'Unknown error'}`, false, 'error-message');
            } else if (data.success && data.answer) {
                // Use basic markdown parsing for now
                const markdownResponse = this.parseMarkdown(data.answer);
                this.addMessage(markdownResponse, false);
            } else {
                this.addMessage('Sorry, I received an unexpected response format.', false, 'error-message');
            }
        } catch (error) {
            console.error('Widget Error:', error);
            // Remove loading message
            if (loadingMessage && loadingMessage.parentNode) {
                chatMessages.removeChild(loadingMessage);
            }

            let errorMessage = 'Sorry, there was an error processing your request. Please try again.';

            if (error.name === 'AbortError') {
                errorMessage = 'Request timed out. Please check your connection and try again.';
            } else if (error.message.includes('Rate limit')) {
                errorMessage = error.message;
            } else if (error.message.includes('Server error')) {
                errorMessage = error.message;
            } else if (!navigator.onLine) {
                errorMessage = 'No internet connection. Please check your connection and try again.';
            }

            this.addMessage(errorMessage, false, 'error-message');
        } finally {
            // Re-enable button
            askButton.disabled = false;
            askButton.textContent = 'Ask';
            promptInput.focus();
        }
    }

    // Basic markdown parsing function
    parseMarkdown(text) {
        if (!text) return '';

        return '<p>' + text
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/\n\n/g, '</p><p>')
            .replace(/\n/g, '<br>') + '</p>';
    }

    checkForQueryParameter() {
        const urlParams = new URLSearchParams(window.location.search);
        const query = urlParams.get('query');

        if (query) {
            const promptInput = this.shadowRoot.getElementById('prompt-input');
            if (promptInput) {
                promptInput.value = decodeURIComponent(query);
                setTimeout(() => {
                    this.sendQuery();
                }, 100);
            }
        }
    }

    updateWidgetTitle() {
        const chatLabel = this.shadowRoot.getElementById('chat-label');
        if (chatLabel) {
            chatLabel.textContent = this.widgetTitle;
        }
    }

    updateAboutTitle() {
        const aboutTitle = this.shadowRoot.getElementById('about-title');
        if (aboutTitle) {
            aboutTitle.textContent = this.aboutTitle;
        }
    }

    renderErrorState() {
        this.shadowRoot.innerHTML = `
            <style>
                :host {
                    display: block;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica Neue', Arial, sans-serif;
                    height: 100%;
                    background-color: #f8f9fa;
                    border: 1px solid #e0e0e0;
                    border-radius: 8px;
                    padding: 20px;
                    text-align: center;
                }
                .error-container {
                    display: flex;
                    flex-direction: column;
                    justify-content: center;
                    align-items: center;
                    height: 100%;
                    min-height: 200px;
                }
                .error-title {
                    color: #e74c3c;
                    font-size: 18px;
                    margin-bottom: 10px;
                }
                .error-message {
                    color: #666;
                    font-size: 14px;
                    margin-bottom: 15px;
                }
                .retry-button {
                    background-color: #0A6AAC;
                    color: white;
                    border: none;
                    padding: 10px 20px;
                    border-radius: 6px;
                    cursor: pointer;
                    font-size: 14px;
                }
                .retry-button:hover {
                    background-color: #124264;
                }
            </style>
            <div class="error-container">
                <div class="error-title">Widget Failed to Load</div>
                <div class="error-message">There was an error initializing the AI assistant widget.</div>
                <button class="retry-button" onclick="window.location.reload()">Reload Page</button>
            </div>
        `;
    }
}

// Define the custom element
customElements.define('solace-ai-widget', SolaceAIWidget);
