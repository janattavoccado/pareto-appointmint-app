/**
 * Pareto Booking Widget
 * Embeddable chat widget for restaurant table reservations
 * 
 * Usage:
 * <script src="https://your-domain.com/widget/embed.js"></script>
 * <script>
 *   ParetoBooking.init({
 *     assistantId: 'rest_abc123xyz',
 *     position: 'bottom-right',
 *     primaryColor: '#4CAF50'
 *   });
 * </script>
 */

(function() {
    'use strict';

    // Prevent multiple initializations
    if (window.ParetoBooking && window.ParetoBooking._initialized) {
        console.warn('ParetoBooking widget already initialized');
        return;
    }

    // Widget namespace
    window.ParetoBooking = {
        _initialized: false,
        _config: null,
        _elements: {},
        _state: {
            isOpen: false,
            isRecording: false,
            messages: [],
            sessionId: null,
            mediaRecorder: null,
            audioChunks: []
        },

        // Default configuration
        _defaults: {
            assistantId: null,
            position: 'bottom-right',  // bottom-right, bottom-left
            primaryColor: '#4CAF50',
            textColor: '#ffffff',
            welcomeMessage: 'Hi! I\'m your AI booking assistant. How can I help you today?',
            placeholderText: 'Type your message...',
            buttonText: '📞',
            buttonTooltip: 'Our AI booking assistant will help you to make a reservation. Please first select location by clicking the "Book a Table" button under chosen location.',
            headerTitle: 'Table Reservation',
            language: 'en',
            baseUrl: null  // Auto-detected from script src
        },

        /**
         * Initialize the widget
         */
        init: function(config) {
            if (this._initialized) {
                console.warn('ParetoBooking widget already initialized');
                return;
            }

            // Merge config with defaults
            this._config = Object.assign({}, this._defaults, config);

            // Validate required config
            if (!this._config.assistantId) {
                console.error('ParetoBooking: assistantId is required');
                return;
            }

            // Auto-detect base URL from script src
            if (!this._config.baseUrl) {
                this._config.baseUrl = this._detectBaseUrl();
            }

            // Generate session ID
            this._state.sessionId = this._generateSessionId();

            // Inject styles
            this._injectStyles();

            // Create widget elements
            this._createWidget();

            // Bind events
            this._bindEvents();

            // Add welcome message
            this._addMessage(this._config.welcomeMessage, false);
            
            // Show date buttons immediately since welcome message asks about date
            this._updateQuickActionsVisibility(this._config.welcomeMessage);

            this._initialized = true;
            console.log('ParetoBooking widget initialized for:', this._config.assistantId);
        },

        /**
         * Detect base URL from script tag
         */
        _detectBaseUrl: function() {
            const scripts = document.getElementsByTagName('script');
            for (let i = 0; i < scripts.length; i++) {
                const src = scripts[i].src;
                if (src && src.includes('embed.js')) {
                    // Handle both /widget/embed.js and /static/widget/embed.js paths
                    let baseUrl = src.replace('/static/widget/embed.js', '')
                                     .replace('/widget/embed.js', '');
                    return baseUrl;
                }
            }
            // Fallback
            return 'https://pareto-appointmint-app-5031fcd0012f.herokuapp.com';
        },

        /**
         * Generate unique session ID
         */
        _generateSessionId: function() {
            return 'widget_' + this._config.assistantId + '_' + 
                   Date.now().toString(36) + '_' + 
                   Math.random().toString(36).substr(2, 9);
        },

        /**
         * Inject CSS styles
         */
        _injectStyles: function() {
            const style = document.createElement('style');
            style.id = 'pareto-booking-styles';
            style.textContent = `
                /* Pareto Booking Widget Styles */
                .pb-widget-container {
                    position: fixed;
                    ${this._config.position === 'bottom-left' ? 'left: 20px;' : 'right: 20px;'}
                    bottom: 20px;
                    z-index: 999999;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                }

                .pb-chat-button {
                    width: 60px;
                    height: 60px;
                    border-radius: 50%;
                    background: ${this._config.primaryColor};
                    color: ${this._config.textColor};
                    border: none;
                    cursor: pointer;
                    font-size: 24px;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                    transition: transform 0.3s, box-shadow 0.3s;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                }

                .pb-chat-button {
                    position: relative;
                }

                .pb-chat-button:hover {
                    transform: scale(1.1);
                    box-shadow: 0 6px 20px rgba(0,0,0,0.2);
                }

                .pb-chat-button:hover::after {
                    content: attr(data-tooltip);
                    position: absolute;
                    bottom: 70px;
                    right: 0;
                    background: #333;
                    color: #fff;
                    padding: 12px 16px;
                    border-radius: 8px;
                    font-size: 13px;
                    line-height: 1.4;
                    width: 280px;
                    text-align: left;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                    z-index: 1000;
                    opacity: 1;
                    pointer-events: none;
                }

                .pb-chat-button:hover::before {
                    content: '';
                    position: absolute;
                    bottom: 62px;
                    right: 20px;
                    border: 8px solid transparent;
                    border-top-color: #333;
                    z-index: 1000;
                }

                .pb-chat-button.open::after,
                .pb-chat-button.open::before {
                    display: none;
                }

                .pb-chat-button.open {
                    transform: rotate(90deg);
                }

                .pb-chat-window {
                    position: absolute;
                    ${this._config.position === 'bottom-left' ? 'left: 0;' : 'right: 0;'}
                    bottom: 75px;
                    width: 380px;
                    height: 520px;
                    background: #ffffff;
                    border-radius: 16px;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                    display: none;
                    flex-direction: column;
                    overflow: hidden;
                    animation: pb-slide-up 0.3s ease;
                }

                .pb-chat-window.open {
                    display: flex;
                }

                @keyframes pb-slide-up {
                    from {
                        opacity: 0;
                        transform: translateY(20px);
                    }
                    to {
                        opacity: 1;
                        transform: translateY(0);
                    }
                }

                .pb-chat-header {
                    background: ${this._config.primaryColor};
                    color: ${this._config.textColor};
                    padding: 16px 20px;
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                }

                .pb-chat-header-title {
                    font-size: 16px;
                    font-weight: 600;
                    display: flex;
                    align-items: center;
                    gap: 8px;
                }

                .pb-chat-header-title::before {
                    content: '🍽️';
                }

                .pb-close-btn {
                    background: none;
                    border: none;
                    color: ${this._config.textColor};
                    font-size: 24px;
                    cursor: pointer;
                    padding: 0;
                    line-height: 1;
                    opacity: 0.8;
                    transition: opacity 0.2s;
                }

                .pb-close-btn:hover {
                    opacity: 1;
                }

                .pb-chat-messages {
                    flex: 1;
                    overflow-y: auto;
                    padding: 16px;
                    display: flex;
                    flex-direction: column;
                    gap: 12px;
                    background: #f8f9fa;
                }

                .pb-message {
                    max-width: 85%;
                    padding: 12px 16px;
                    border-radius: 16px;
                    font-size: 14px;
                    line-height: 1.5;
                    animation: pb-fade-in 0.3s ease;
                }

                @keyframes pb-fade-in {
                    from { opacity: 0; transform: translateY(10px); }
                    to { opacity: 1; transform: translateY(0); }
                }

                .pb-message.user {
                    background: ${this._config.primaryColor};
                    color: ${this._config.textColor};
                    align-self: flex-end;
                    border-bottom-right-radius: 4px;
                }

                .pb-message.assistant {
                    background: #ffffff;
                    color: #333333;
                    align-self: flex-start;
                    border-bottom-left-radius: 4px;
                    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                }

                .pb-message.voice {
                    font-style: italic;
                }

                .pb-message.voice::before {
                    content: '🎙️ ';
                }

                .pb-typing-indicator {
                    display: none;
                    align-self: flex-start;
                    padding: 12px 16px;
                    background: #ffffff;
                    border-radius: 16px;
                    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                }

                .pb-typing-indicator.active {
                    display: flex;
                    gap: 4px;
                }

                .pb-typing-dot {
                    width: 8px;
                    height: 8px;
                    background: #999;
                    border-radius: 50%;
                    animation: pb-typing 1.4s infinite;
                }

                .pb-typing-dot:nth-child(2) { animation-delay: 0.2s; }
                .pb-typing-dot:nth-child(3) { animation-delay: 0.4s; }

                @keyframes pb-typing {
                    0%, 60%, 100% { transform: translateY(0); }
                    30% { transform: translateY(-6px); }
                }

                .pb-chat-input-container {
                    padding: 12px 16px;
                    background: #ffffff;
                    border-top: 1px solid #e9ecef;
                    display: flex;
                    gap: 8px;
                    align-items: center;
                }

                .pb-chat-input {
                    flex: 1;
                    padding: 12px 16px;
                    border: 1px solid #e9ecef;
                    border-radius: 24px;
                    font-size: 14px;
                    outline: none;
                    transition: border-color 0.2s;
                }

                .pb-chat-input:focus {
                    border-color: ${this._config.primaryColor};
                }

                .pb-send-btn, .pb-mic-btn {
                    width: 44px;
                    height: 44px;
                    border-radius: 50%;
                    border: none;
                    cursor: pointer;
                    font-size: 18px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    transition: transform 0.2s, background 0.2s;
                }

                .pb-send-btn {
                    background: ${this._config.primaryColor};
                    color: ${this._config.textColor};
                }

                .pb-send-btn:hover {
                    transform: scale(1.05);
                }

                .pb-send-btn:disabled {
                    opacity: 0.5;
                    cursor: not-allowed;
                }

                .pb-mic-btn {
                    background: #28a745;
                    color: white;
                }

                .pb-mic-btn:hover {
                    background: #218838;
                }

                .pb-mic-btn.recording {
                    background: #dc3545;
                    animation: pb-pulse 1s infinite;
                }

                @keyframes pb-pulse {
                    0%, 100% { transform: scale(1); }
                    50% { transform: scale(1.1); }
                }

                .pb-recording-indicator {
                    display: none;
                    align-items: center;
                    gap: 8px;
                    padding: 8px 12px;
                    background: #fff3cd;
                    border-radius: 8px;
                    font-size: 12px;
                    color: #856404;
                }

                .pb-recording-indicator.active {
                    display: flex;
                }

                .pb-recording-dot {
                    width: 8px;
                    height: 8px;
                    background: #dc3545;
                    border-radius: 50%;
                    animation: pb-pulse 1s infinite;
                }

                .pb-powered-by {
                    text-align: center;
                    padding: 8px;
                    font-size: 11px;
                    color: #999;
                    background: #f8f9fa;
                }

                .pb-powered-by a {
                    color: ${this._config.primaryColor};
                    text-decoration: none;
                }

                /* Quick action buttons container */
                .pb-quick-actions {
                    display: none;
                    padding: 8px 16px;
                    background: #f8f9fa;
                    border-top: 1px solid #e9ecef;
                    gap: 8px;
                    flex-wrap: wrap;
                    justify-content: center;
                }

                .pb-quick-actions.active {
                    display: flex;
                }

                /* Date picker buttons */
                .pb-date-picker {
                    display: flex;
                    gap: 6px;
                    flex-wrap: wrap;
                    justify-content: center;
                    width: 100%;
                }

                .pb-date-btn {
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    padding: 8px 12px;
                    background: #ffffff;
                    border: 2px solid #e9ecef;
                    border-radius: 12px;
                    cursor: pointer;
                    transition: all 0.2s;
                    min-width: 58px;
                }

                .pb-date-btn:hover {
                    border-color: ${this._config.primaryColor};
                    background: #f0fff0;
                }

                .pb-date-btn.selected {
                    border-color: ${this._config.primaryColor};
                    background: ${this._config.primaryColor};
                    color: white;
                }

                .pb-date-btn .day-name {
                    font-size: 11px;
                    font-weight: 500;
                    text-transform: uppercase;
                    opacity: 0.8;
                }

                .pb-date-btn .day-num {
                    font-size: 18px;
                    font-weight: 700;
                    line-height: 1.2;
                }

                .pb-date-btn.selected .day-name,
                .pb-date-btn.selected .day-num {
                    color: white;
                }

                /* Guest count buttons */
                .pb-guest-picker {
                    display: flex;
                    gap: 6px;
                    flex-wrap: wrap;
                    justify-content: center;
                    width: 100%;
                }

                .pb-guest-btn {
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    width: 44px;
                    height: 44px;
                    background: #ffffff;
                    border: 2px solid #e9ecef;
                    border-radius: 50%;
                    cursor: pointer;
                    font-size: 16px;
                    font-weight: 600;
                    transition: all 0.2s;
                }

                .pb-guest-btn:hover {
                    border-color: ${this._config.primaryColor};
                    background: #f0fff0;
                }

                .pb-guest-btn.selected {
                    border-color: ${this._config.primaryColor};
                    background: ${this._config.primaryColor};
                    color: white;
                }

                /* Confirm button */
                .pb-confirm-btn {
                    display: none;
                    width: 100%;
                    padding: 14px 24px;
                    background: linear-gradient(135deg, ${this._config.primaryColor}, #2d8f3d);
                    color: white;
                    border: none;
                    border-radius: 12px;
                    font-size: 16px;
                    font-weight: 600;
                    cursor: pointer;
                    transition: all 0.2s;
                    box-shadow: 0 4px 12px rgba(76, 175, 80, 0.3);
                }

                .pb-confirm-btn:hover {
                    transform: translateY(-2px);
                    box-shadow: 0 6px 16px rgba(76, 175, 80, 0.4);
                }

                .pb-confirm-btn.active {
                    display: block;
                }

                .pb-confirm-btn::before {
                    content: '✓ ';
                }

                /* Time picker buttons */
                .pb-time-picker {
                    display: flex;
                    gap: 6px;
                    flex-wrap: wrap;
                    justify-content: center;
                    width: 100%;
                }

                .pb-time-btn {
                    padding: 8px 14px;
                    background: #ffffff;
                    border: 2px solid #e9ecef;
                    border-radius: 20px;
                    cursor: pointer;
                    font-size: 14px;
                    font-weight: 500;
                    transition: all 0.2s;
                }

                .pb-time-btn:hover {
                    border-color: ${this._config.primaryColor};
                    background: #f0fff0;
                }

                .pb-time-btn.selected {
                    border-color: ${this._config.primaryColor};
                    background: ${this._config.primaryColor};
                    color: white;
                }

                /* Mobile responsive */
                @media (max-width: 480px) {
                    .pb-chat-window {
                        width: calc(100vw - 40px);
                        height: calc(100vh - 120px);
                        max-height: 500px;
                    }
                }
            `;
            document.head.appendChild(style);
        },

        /**
         * Create widget DOM elements
         */
        _createWidget: function() {
            // Container
            const container = document.createElement('div');
            container.className = 'pb-widget-container';
            container.id = 'pareto-booking-widget';

            // Chat window
            const chatWindow = document.createElement('div');
            chatWindow.className = 'pb-chat-window';
            chatWindow.innerHTML = `
                <div class="pb-chat-header">
                    <div class="pb-chat-header-title">${this._config.headerTitle}</div>
                    <button class="pb-close-btn" aria-label="Close">&times;</button>
                </div>
                <div class="pb-chat-messages">
                    <div class="pb-typing-indicator">
                        <div class="pb-typing-dot"></div>
                        <div class="pb-typing-dot"></div>
                        <div class="pb-typing-dot"></div>
                    </div>
                </div>
                <div class="pb-recording-indicator">
                    <div class="pb-recording-dot"></div>
                    <span>Recording... <span class="pb-recording-time">0:00</span></span>
                    <button class="pb-cancel-recording" style="margin-left:auto;background:none;border:none;cursor:pointer;">✕</button>
                </div>
                <div class="pb-quick-actions">
                    <div class="pb-date-picker"></div>
                    <div class="pb-time-picker"></div>
                    <div class="pb-guest-picker"></div>
                    <button class="pb-confirm-btn">Confirm Reservation</button>
                </div>
                <div class="pb-chat-input-container">
                    <input type="text" class="pb-chat-input" placeholder="${this._config.placeholderText}" />
                    <button class="pb-mic-btn" title="Voice message"><svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="23"></line><line x1="8" y1="23" x2="16" y2="23"></line></svg></button>
                    <button class="pb-send-btn" title="Send message">➤</button>
                </div>
                <div class="pb-powered-by">
                    Powered by <a href="https://pareto.ai" target="_blank">Pareto AI</a>
                </div>
            `;

            // Chat button
            const chatButton = document.createElement('button');
            chatButton.className = 'pb-chat-button';
            chatButton.innerHTML = this._config.buttonText;
            chatButton.setAttribute('aria-label', 'Open chat');
            chatButton.setAttribute('data-tooltip', this._config.buttonTooltip);

            container.appendChild(chatWindow);
            container.appendChild(chatButton);
            document.body.appendChild(container);

            // Store references
            this._elements = {
                container: container,
                chatWindow: chatWindow,
                chatButton: chatButton,
                messagesContainer: chatWindow.querySelector('.pb-chat-messages'),
                typingIndicator: chatWindow.querySelector('.pb-typing-indicator'),
                input: chatWindow.querySelector('.pb-chat-input'),
                sendBtn: chatWindow.querySelector('.pb-send-btn'),
                micBtn: chatWindow.querySelector('.pb-mic-btn'),
                closeBtn: chatWindow.querySelector('.pb-close-btn'),
                recordingIndicator: chatWindow.querySelector('.pb-recording-indicator'),
                recordingTime: chatWindow.querySelector('.pb-recording-time'),
                cancelRecording: chatWindow.querySelector('.pb-cancel-recording'),
                quickActions: chatWindow.querySelector('.pb-quick-actions'),
                datePicker: chatWindow.querySelector('.pb-date-picker'),
                timePicker: chatWindow.querySelector('.pb-time-picker'),
                guestPicker: chatWindow.querySelector('.pb-guest-picker'),
                confirmBtn: chatWindow.querySelector('.pb-confirm-btn')
            };

            // Initialize quick action buttons
            this._initQuickActions();
        },

        /**
         * Bind event listeners
         */
        _bindEvents: function() {
            const self = this;

            // Toggle chat
            this._elements.chatButton.addEventListener('click', function() {
                self._toggleChat();
            });

            // Close button
            this._elements.closeBtn.addEventListener('click', function() {
                self._toggleChat(false);
            });

            // Send message
            this._elements.sendBtn.addEventListener('click', function() {
                self._sendTextMessage();
            });

            // Enter key
            this._elements.input.addEventListener('keypress', function(e) {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    self._sendTextMessage();
                }
            });

            // Mic button
            this._elements.micBtn.addEventListener('click', function() {
                self._toggleRecording();
            });

            // Cancel recording
            this._elements.cancelRecording.addEventListener('click', function() {
                self._cancelRecording();
            });
        },

        /**
         * Toggle chat window
         */
        _toggleChat: function(forceState) {
            const isOpen = forceState !== undefined ? forceState : !this._state.isOpen;
            this._state.isOpen = isOpen;

            this._elements.chatWindow.classList.toggle('open', isOpen);
            this._elements.chatButton.classList.toggle('open', isOpen);
            this._elements.chatButton.innerHTML = isOpen ? '✕' : this._config.buttonText;

            if (isOpen) {
                this._elements.input.focus();
            }
        },

        /**
         * Add message to chat
         */
        _addMessage: function(text, isUser, isVoice) {
            const message = document.createElement('div');
            message.className = 'pb-message ' + (isUser ? 'user' : 'assistant');
            if (isVoice) message.classList.add('voice');
            message.textContent = text;

            // Insert before typing indicator
            this._elements.messagesContainer.insertBefore(
                message, 
                this._elements.typingIndicator
            );

            // Scroll to bottom
            this._elements.messagesContainer.scrollTop = 
                this._elements.messagesContainer.scrollHeight;

            // Store message
            this._state.messages.push({
                role: isUser ? 'user' : 'assistant',
                content: text,
                timestamp: new Date().toISOString()
            });
        },

        /**
         * Show/hide typing indicator
         */
        _setTyping: function(show) {
            this._elements.typingIndicator.classList.toggle('active', show);
            if (show) {
                this._elements.messagesContainer.scrollTop = 
                    this._elements.messagesContainer.scrollHeight;
            }
        },

        /**
         * Send text message
         */
        _sendTextMessage: async function() {
            var text = this._elements.input.value.trim();
            if (!text) return;

            // Clear input
            this._elements.input.value = '';

            // Add user message
            this._addMessage(text, true);

            // Send to server (this handles disabling inputs, typing indicator, etc.)
            await this._sendToServer(text);
        },

        /**
         * iOS/Safari detection helpers
         */
        _isIOS: function() {
            return /iPad|iPhone|iPod/.test(navigator.userAgent) || 
                   (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
        },

        _isSafari: function() {
            return /^((?!chrome|android).)*safari/i.test(navigator.userAgent);
        },

        /**
         * Get supported MIME type for audio recording
         */
        _getSupportedMimeType: function() {
            var types = [
                'audio/webm;codecs=opus',
                'audio/webm',
                'audio/mp4',
                'audio/ogg;codecs=opus',
                'audio/wav'
            ];
            
            for (var i = 0; i < types.length; i++) {
                if (typeof MediaRecorder !== 'undefined' && 
                    MediaRecorder.isTypeSupported && 
                    MediaRecorder.isTypeSupported(types[i])) {
                    return types[i];
                }
            }
            return 'audio/webm'; // fallback
        },

        /**
         * Toggle voice recording
         */
        _toggleRecording: async function() {
            if (this._state.isRecording) {
                this._stopRecording();
            } else {
                await this._startRecording();
            }
        },

        /**
         * Start voice recording with iOS Safari support
         */
        _startRecording: async function() {
            var self = this;
            try {
                var stream = await navigator.mediaDevices.getUserMedia({ 
                    audio: {
                        echoCancellation: true,
                        noiseSuppression: true,
                        sampleRate: 44100
                    } 
                });
                
                this._state.audioStream = stream;
                
                // Check if MediaRecorder is supported (not on older iOS)
                if (typeof MediaRecorder === 'undefined') {
                    // Fallback for older iOS - use Web Audio API
                    await this._startRecordingWebAudio(stream);
                    return;
                }
                
                // Try to use MediaRecorder with a supported MIME type
                var mimeType = this._getSupportedMimeType();
                console.log('ParetoBooking: Using MIME type:', mimeType);
                
                try {
                    this._state.mediaRecorder = new MediaRecorder(stream, { mimeType: mimeType });
                } catch (e) {
                    console.log('ParetoBooking: MediaRecorder with options failed, trying without:', e);
                    this._state.mediaRecorder = new MediaRecorder(stream);
                }
                
                this._state.audioChunks = [];
                this._state.actualMimeType = mimeType;
                
                this._state.mediaRecorder.ondataavailable = function(event) {
                    if (event.data && event.data.size > 0) {
                        self._state.audioChunks.push(event.data);
                    }
                };
                
                this._state.mediaRecorder.onstop = async function() {
                    stream.getTracks().forEach(function(track) { track.stop(); });
                    
                    if (self._state.audioChunks.length > 0) {
                        var actualMimeType = self._state.mediaRecorder.mimeType || self._state.actualMimeType || 'audio/webm';
                        var audioBlob = new Blob(self._state.audioChunks, { type: actualMimeType });
                        console.log('ParetoBooking: Recording stopped, blob size:', audioBlob.size, 'type:', actualMimeType);
                        await self._sendAudioMessage(audioBlob, actualMimeType);
                    }
                };
                
                this._state.mediaRecorder.onerror = function(event) {
                    console.error('ParetoBooking: MediaRecorder error:', event.error);
                };
                
                // Use timeslice for iOS compatibility
                this._state.mediaRecorder.start(1000);
                this._state.isRecording = true;
                
                this._updateRecordingUI(true);
                
            } catch (error) {
                console.error('ParetoBooking: Microphone access error:', error);
                var errorMsg = 'Could not access microphone. ';
                if (error.name === 'NotAllowedError') {
                    errorMsg += 'Please allow microphone access in your browser settings.';
                    if (this._isIOS()) {
                        errorMsg += '\n\nOn iOS: Go to Settings > Safari > Microphone and enable it for this site.';
                    }
                } else if (error.name === 'NotFoundError') {
                    errorMsg += 'No microphone found on this device.';
                } else {
                    errorMsg += error.message;
                }
                alert(errorMsg);
            }
        },

        /**
         * Fallback recording using Web Audio API for older iOS
         */
        _startRecordingWebAudio: async function(stream) {
            var self = this;
            try {
                var AudioContext = window.AudioContext || window.webkitAudioContext;
                this._state.audioContext = new AudioContext({ sampleRate: 44100 });
                var source = this._state.audioContext.createMediaStreamSource(stream);
                
                // Create a script processor (deprecated but works on older iOS)
                var bufferSize = 4096;
                this._state.audioProcessor = this._state.audioContext.createScriptProcessor(bufferSize, 1, 1);
                this._state.audioData = [];
                
                this._state.audioProcessor.onaudioprocess = function(e) {
                    var channelData = e.inputBuffer.getChannelData(0);
                    self._state.audioData.push(new Float32Array(channelData));
                };
                
                source.connect(this._state.audioProcessor);
                this._state.audioProcessor.connect(this._state.audioContext.destination);
                
                this._state.isRecording = true;
                this._state.useWebAudioFallback = true;
                this._updateRecordingUI(true);
                
            } catch (error) {
                console.error('ParetoBooking: Web Audio API recording failed:', error);
                alert('Voice recording is not supported on this device.');
            }
        },

        /**
         * Create WAV blob from audio data (for Web Audio API fallback)
         */
        _createWavBlob: function(audioData, sampleRate) {
            var length = 0;
            for (var i = 0; i < audioData.length; i++) {
                length += audioData[i].length;
            }
            var buffer = new Float32Array(length);
            var offset = 0;
            for (var i = 0; i < audioData.length; i++) {
                buffer.set(audioData[i], offset);
                offset += audioData[i].length;
            }
            
            // Convert to 16-bit PCM
            var pcmData = new Int16Array(buffer.length);
            for (var i = 0; i < buffer.length; i++) {
                var s = Math.max(-1, Math.min(1, buffer[i]));
                pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
            }
            
            // Create WAV header
            var wavBuffer = new ArrayBuffer(44 + pcmData.length * 2);
            var view = new DataView(wavBuffer);
            
            // RIFF header
            this._writeString(view, 0, 'RIFF');
            view.setUint32(4, 36 + pcmData.length * 2, true);
            this._writeString(view, 8, 'WAVE');
            
            // fmt chunk
            this._writeString(view, 12, 'fmt ');
            view.setUint32(16, 16, true);
            view.setUint16(20, 1, true); // PCM
            view.setUint16(22, 1, true); // Mono
            view.setUint32(24, sampleRate, true);
            view.setUint32(28, sampleRate * 2, true);
            view.setUint16(32, 2, true);
            view.setUint16(34, 16, true);
            
            // data chunk
            this._writeString(view, 36, 'data');
            view.setUint32(40, pcmData.length * 2, true);
            
            // Write PCM data
            var pcmOffset = 44;
            for (var i = 0; i < pcmData.length; i++) {
                view.setInt16(pcmOffset + i * 2, pcmData[i], true);
            }
            
            return new Blob([wavBuffer], { type: 'audio/wav' });
        },

        _writeString: function(view, offset, string) {
            for (var i = 0; i < string.length; i++) {
                view.setUint8(offset + i, string.charCodeAt(i));
            }
        },

        /**
         * Update recording UI
         */
        _updateRecordingUI: function(recording) {
            var self = this;
            if (recording) {
                this._elements.micBtn.classList.add('recording');
                this._elements.micBtn.innerHTML = '⏹';
                this._elements.recordingIndicator.classList.add('active');
                
                // Start timer
                this._state.recordingSeconds = 0;
                this._state.recordingTimer = setInterval(function() {
                    self._state.recordingSeconds++;
                    var minutes = Math.floor(self._state.recordingSeconds / 60);
                    var seconds = self._state.recordingSeconds % 60;
                    self._elements.recordingTime.textContent = 
                        minutes + ':' + seconds.toString().padStart(2, '0');
                }, 1000);
            } else {
                this._elements.micBtn.classList.remove('recording');
                this._elements.micBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="23"></line><line x1="8" y1="23" x2="16" y2="23"></line></svg>';
                this._elements.recordingIndicator.classList.remove('active');
                
                // Stop timer
                if (this._state.recordingTimer) {
                    clearInterval(this._state.recordingTimer);
                    this._state.recordingTimer = null;
                }
            }
        },

        /**
         * Stop voice recording
         */
        _stopRecording: function() {
            var self = this;
            if (this._state.isRecording) {
                if (this._state.useWebAudioFallback) {
                    // Stop Web Audio API recording
                    if (this._state.audioProcessor) {
                        this._state.audioProcessor.disconnect();
                    }
                    if (this._state.audioContext) {
                        this._state.audioContext.close();
                    }
                    
                    // Convert to WAV
                    if (this._state.audioData && this._state.audioData.length > 0) {
                        var wavBlob = this._createWavBlob(this._state.audioData, 44100);
                        this._sendAudioMessage(wavBlob, 'audio/wav');
                    }
                    
                    if (this._state.audioStream) {
                        this._state.audioStream.getTracks().forEach(function(track) { track.stop(); });
                    }
                    
                    this._state.useWebAudioFallback = false;
                } else if (this._state.mediaRecorder && this._state.mediaRecorder.state !== 'inactive') {
                    this._state.mediaRecorder.stop();
                }
            }
            
            this._state.isRecording = false;
            this._updateRecordingUI(false);
        },

        /**
         * Cancel recording
         */
        _cancelRecording: function() {
            this._state.audioChunks = [];
            this._state.audioData = [];
            this._stopRecording();
        },

        /**
         * Send audio message with iOS support
         */
        _sendAudioMessage: async function(audioBlob, mimeType) {
            // Disable inputs
            this._elements.input.disabled = true;
            this._elements.sendBtn.disabled = true;
            this._elements.micBtn.disabled = true;

            // Show typing
            this._setTyping(true);

            // Determine file extension based on MIME type
            var extension = 'webm';
            if (mimeType && mimeType.indexOf('wav') !== -1) extension = 'wav';
            else if (mimeType && mimeType.indexOf('mp4') !== -1) extension = 'mp4';
            else if (mimeType && mimeType.indexOf('ogg') !== -1) extension = 'ogg';

            try {
                var formData = new FormData();
                formData.append('audio', audioBlob, 'recording.' + extension);
                formData.append('assistant_id', this._config.assistantId);
                formData.append('session_id', this._state.sessionId);

                var response = await fetch(this._config.baseUrl + '/widget/chat/audio', {
                    method: 'POST',
                    body: formData
                });

                var data = await response.json();

                this._setTyping(false);

                if (data.success) {
                    // Add transcribed user message
                    this._addMessage(data.transcribed_text, true, true);
                    // Add assistant response
                    this._addMessage(data.response, false);
                } else {
                    this._addMessage('Sorry, I couldn\'t process your voice message. Please try again.', false);
                }
            } catch (error) {
                this._setTyping(false);
                this._addMessage('Sorry, I couldn\'t send your voice message.', false);
                console.error('ParetoBooking audio error:', error);
            }

            // Re-enable inputs
            this._elements.input.disabled = false;
            this._elements.sendBtn.disabled = false;
            this._elements.micBtn.disabled = false;
            this._elements.input.focus();
        },

        /**
         * Initialize quick action buttons
         */
        _initQuickActions: function() {
            var self = this;
            
            // Generate date buttons for next 5 days
            this._generateDateButtons();
            
            // Generate time buttons
            this._generateTimeButtons();
            
            // Generate guest count buttons
            this._generateGuestButtons();
            
            // Confirm button click handler
            this._elements.confirmBtn.addEventListener('click', function() {
                self._sendQuickMessage('confirmed');
                self._hideQuickActions();
            });
        },

        /**
         * Generate date picker buttons for next 5 days
         */
        _generateDateButtons: function() {
            var self = this;
            var datePicker = this._elements.datePicker;
            datePicker.innerHTML = '';
            
            var dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
            var today = new Date();
            
            for (var i = 0; i < 5; i++) {
                var date = new Date(today);
                date.setDate(today.getDate() + i);
                
                var btn = document.createElement('button');
                btn.className = 'pb-date-btn';
                btn.dataset.date = date.toISOString().split('T')[0];
                btn.dataset.dayName = i === 0 ? 'Today' : dayNames[date.getDay()];
                btn.innerHTML = '<span class="day-name">' + (i === 0 ? 'Today' : dayNames[date.getDay()]) + '</span>' +
                               '<span class="day-num">' + date.getDate() + '</span>';
                
                btn.addEventListener('click', function() {
                    // Remove selected from siblings
                    datePicker.querySelectorAll('.pb-date-btn').forEach(function(b) {
                        b.classList.remove('selected');
                    });
                    this.classList.add('selected');
                    
                    // Send the date as a message
                    var dateStr = this.dataset.dayName === 'Today' ? 'today' : this.dataset.dayName + ' ' + this.querySelector('.day-num').textContent;
                    self._sendQuickMessage(dateStr);
                });
                
                datePicker.appendChild(btn);
            }
        },

        /**
         * Generate time picker buttons
         */
        _generateTimeButtons: function() {
            var self = this;
            var timePicker = this._elements.timePicker;
            timePicker.innerHTML = '';
            
            var times = ['12:00', '13:00', '18:00', '19:00', '20:00', '21:00'];
            
            times.forEach(function(time) {
                var btn = document.createElement('button');
                btn.className = 'pb-time-btn';
                btn.dataset.time = time;
                btn.textContent = time;
                
                btn.addEventListener('click', function() {
                    // Remove selected from siblings
                    timePicker.querySelectorAll('.pb-time-btn').forEach(function(b) {
                        b.classList.remove('selected');
                    });
                    this.classList.add('selected');
                    
                    // Send the time as a message
                    self._sendQuickMessage(time);
                });
                
                timePicker.appendChild(btn);
            });
        },

        /**
         * Generate guest count buttons
         */
        _generateGuestButtons: function() {
            var self = this;
            var guestPicker = this._elements.guestPicker;
            guestPicker.innerHTML = '';
            
            for (var i = 1; i <= 8; i++) {
                var btn = document.createElement('button');
                btn.className = 'pb-guest-btn';
                btn.dataset.guests = i;
                btn.textContent = i === 8 ? '8+' : i;
                
                btn.addEventListener('click', function() {
                    // Remove selected from siblings
                    guestPicker.querySelectorAll('.pb-guest-btn').forEach(function(b) {
                        b.classList.remove('selected');
                    });
                    this.classList.add('selected');
                    
                    // Send the guest count as a message
                    var guests = this.dataset.guests;
                    self._sendQuickMessage(guests + (guests === '1' ? ' person' : ' people'));
                });
                
                guestPicker.appendChild(btn);
            }
        },

        /**
         * Send a quick message from button click
         */
        _sendQuickMessage: function(text) {
            // Add user message to chat
            this._addMessage(text, true);
            
            // Send to server
            this._sendToServer(text);
        },

        /**
         * Send message to server (shared by text and quick messages)
         */
        _sendToServer: async function(text) {
            var self = this;
            
            // Disable input
            this._elements.input.disabled = true;
            this._elements.sendBtn.disabled = true;

            // Show typing
            this._setTyping(true);

            try {
                var response = await fetch(this._config.baseUrl + '/widget/chat', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        assistant_id: this._config.assistantId,
                        session_id: this._state.sessionId,
                        message: text
                    })
                });

                var data = await response.json();

                this._setTyping(false);

                if (data.success) {
                    this._addMessage(data.response, false);
                    
                    // Check response to show/hide quick actions
                    this._updateQuickActionsVisibility(data.response);
                } else {
                    this._addMessage('Sorry, I encountered an error. Please try again.', false);
                }
            } catch (error) {
                this._setTyping(false);
                this._addMessage('Sorry, I couldn\'t connect. Please check your connection.', false);
                console.error('ParetoBooking error:', error);
            }

            // Re-enable input
            this._elements.input.disabled = false;
            this._elements.sendBtn.disabled = false;
            this._elements.input.focus();
        },

        /**
         * Update quick actions visibility based on bot response
         */
        _updateQuickActionsVisibility: function(response) {
            var lowerResponse = response.toLowerCase();
            
            // Hide all pickers first
            this._elements.datePicker.style.display = 'none';
            this._elements.timePicker.style.display = 'none';
            this._elements.guestPicker.style.display = 'none';
            this._elements.confirmBtn.classList.remove('active');
            
            // PRIORITY 1: Confirmation questions (check first to avoid false positives from summary text)
            // Look for phrases that indicate asking for confirmation
            if (lowerResponse.includes('everything correct') || 
                lowerResponse.includes('is this correct') ||
                lowerResponse.includes('is that correct') ||
                lowerResponse.includes("say 'confirmed'") ||
                lowerResponse.includes('say confirmed') ||
                lowerResponse.includes('to proceed') ||
                lowerResponse.includes('reservation summary')) {
                this._elements.quickActions.classList.add('active');
                this._elements.confirmBtn.classList.add('active');
            }
            // PRIORITY 2: Time questions (when asking specifically about time)
            else if ((lowerResponse.includes('what time') || 
                      lowerResponse.includes('at what hour') ||
                      lowerResponse.includes('which time')) &&
                     !lowerResponse.includes('summary')) {
                this._elements.quickActions.classList.add('active');
                this._elements.timePicker.style.display = 'flex';
            }
            // PRIORITY 3: Date/when questions (only if not a summary and asking for date)
            else if ((lowerResponse.includes('when would you like') || 
                      lowerResponse.includes('which day') ||
                      lowerResponse.includes('what date')) &&
                     !lowerResponse.includes('summary') &&
                     !lowerResponse.includes('time:')) {
                this._elements.quickActions.classList.add('active');
                this._elements.datePicker.style.display = 'flex';
            }
            // PRIORITY 4: Guest count questions
            else if ((lowerResponse.includes('how many') || 
                      lowerResponse.includes('number of guests') ||
                      lowerResponse.includes('party size')) &&
                     !lowerResponse.includes('summary')) {
                this._elements.quickActions.classList.add('active');
                this._elements.guestPicker.style.display = 'flex';
            }
            else {
                this._elements.quickActions.classList.remove('active');
            }
        },

        /**
         * Hide all quick actions
         */
        _hideQuickActions: function() {
            this._elements.quickActions.classList.remove('active');
            this._elements.datePicker.style.display = 'none';
            this._elements.timePicker.style.display = 'none';
            this._elements.guestPicker.style.display = 'none';
            this._elements.confirmBtn.classList.remove('active');
        },

        /**
         * Destroy widget
         */
        destroy: function() {
            if (this._elements.container) {
                this._elements.container.remove();
            }
            const styles = document.getElementById('pareto-booking-styles');
            if (styles) {
                styles.remove();
            }
            this._initialized = false;
            this._state = {
                isOpen: false,
                isRecording: false,
                messages: [],
                sessionId: null
            };
        }
    };
})();
