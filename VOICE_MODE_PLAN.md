# Voice Mode Roadmap

## Phase 1 — Push-to-Talk local conversation

Status: implemented.

- Use `5 + 6` together as the global Push-to-Talk chord.
- Record one utterance only after the chord is pressed.
- Transcribe locally with Whisper, answer through Ollama, and speak through local Piper TTS.
- Make the chord configurable with `HERMES_PUSH_TO_TALK_KEYS`.

## Phase 2 — Safe desktop voice commands

- Classify only allowlisted intents: open a direct HTTPS URL, web search, YouTube search, and stop speaking.
- Ask for spoken confirmation before opening an external URL or a search result.
- Keep regular questions on the existing Ollama conversation path.
- Add an audit log containing the recognized command and selected URL, not raw audio.

## Phase 3 — Voice controls in Web UI

- Add a microphone button with visible recording and transcription states.
- Send recorded audio to a local Whisper endpoint.
- Use the existing WebSocket channel for progress events.
- Require HTTPS or localhost before requesting browser microphone permission.

## Phase 4 — Hands-free interaction

- Add an optional local wake word and a clear on/off indicator.
- Support interruption while the assistant is speaking.
- Add command confirmation preferences and per-command enablement.
- Measure latency, transcription failures, and false wake-ups locally.
