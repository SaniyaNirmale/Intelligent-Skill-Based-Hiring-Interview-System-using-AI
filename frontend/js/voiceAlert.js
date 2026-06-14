/**
 * voiceAlert.js  ─  Proctoring Voice Alert System
 * ─────────────────────────────────────────────────────────────────────────────
 * Uses the browser's Web Speech API (SpeechSynthesis) to speak proctoring
 * alerts out loud so the student hears them in addition to seeing them.
 *
 * Features:
 *  • Queue-based: multiple alerts don't overlap — they are spoken in order
 *  • Priority interruption: CRITICAL alerts cancel any ongoing speech immediately
 *  • Configurable voice, rate, pitch, volume
 *  • Graceful fallback (silent if SpeechSynthesis not supported)
 *  • Visual + audio in sync
 *
 * Usage:
 *   VoiceAlert.speak("Your message here");
 *   VoiceAlert.speak("Critical!", { priority: 'critical' });
 *   VoiceAlert.setVoice('female');
 */

const VoiceAlert = (() => {
    // ── Config ──────────────────────────────────────────────────────────────
    const DEFAULT_CONFIG = {
        rate:    1.0,    // 0.1–10
        pitch:   1.0,    // 0–2
        volume:  1.0,    // 0–1
        lang:    'en-US',
        // 'auto' | 'female' | 'male' — picks best available system voice
        voiceGender: 'female'
    };

    let config = { ...DEFAULT_CONFIG };
    let voiceList = [];
    let selectedVoice = null;
    let queue = [];
    let speaking = false;

    // ── Load voices (async in Chrome) ───────────────────────────────────────
    function _loadVoices() {
        voiceList = window.speechSynthesis?.getVoices() || [];
        _pickVoice();
    }

    function _pickVoice() {
        if (!voiceList.length) return;

        const lang = config.lang.toLowerCase();

        // Try to match preferred gender first
        const genderHints = {
            female: ['female', 'woman', 'zira', 'samantha', 'victoria', 'karen', 'moira', 'fiona', 'google us english', 'google uk english female', 'microsoft zira'],
            male:   ['male', 'man', 'david', 'mark', 'daniel', 'google uk english male', 'microsoft david', 'microsoft mark']
        };

        const hints = genderHints[config.voiceGender] || [];

        // 1. Try to match gender hint in an English voice
        let found = voiceList.find(v =>
            v.lang.toLowerCase().startsWith('en') &&
            hints.some(h => v.name.toLowerCase().includes(h))
        );

        // 2. Fallback: any English voice
        if (!found) found = voiceList.find(v => v.lang.toLowerCase().startsWith('en'));

        // 3. Fallback: whatever is default
        if (!found) found = voiceList.find(v => v.default) || voiceList[0];

        selectedVoice = found || null;
    }

    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
        _loadVoices();
        window.speechSynthesis.onvoiceschanged = _loadVoices;
    }

    // ── Internal speak engine ───────────────────────────────────────────────
    function _processQueue() {
        if (speaking || queue.length === 0) return;
        const { text, options } = queue.shift();
        speaking = true;

        const utter = new SpeechSynthesisUtterance(text);
        utter.rate   = options.rate   ?? config.rate;
        utter.pitch  = options.pitch  ?? config.pitch;
        utter.volume = options.volume ?? config.volume;
        utter.lang   = options.lang   ?? config.lang;

        if (selectedVoice) utter.voice = selectedVoice;

        utter.onend = utter.onerror = () => {
            speaking = false;
            _processQueue();
        };

        window.speechSynthesis.speak(utter);
    }

    // ── Public API ──────────────────────────────────────────────────────────
    return {
        /**
         * Speak a message aloud.
         * @param {string} text   — what to say
         * @param {object} opts   — optional overrides: { priority, rate, pitch, volume }
         *   priority: 'normal' (default) | 'critical' (cancels current speech immediately)
         */
        speak(text, opts = {}) {
            if (!('speechSynthesis' in window)) return; // silent fallback

            if (opts.priority === 'critical') {
                window.speechSynthesis.cancel();
                queue = [];
                speaking = false;
            }

            queue.push({ text, options: opts });
            _processQueue();
        },

        /** Stop all speech immediately */
        stop() {
            if (!('speechSynthesis' in window)) return;
            window.speechSynthesis.cancel();
            queue = [];
            speaking = false;
        },

        /** Change voice gender: 'female' | 'male' | 'auto' */
        setVoice(gender) {
            config.voiceGender = gender;
            _pickVoice();
        },

        /** Update global config */
        configure(opts = {}) {
            config = { ...config, ...opts };
            _pickVoice();
        },

        /** Returns true if browser supports SpeechSynthesis */
        isSupported() {
            return 'speechSynthesis' in window;
        }
    };
})();

window.VoiceAlert = VoiceAlert;
