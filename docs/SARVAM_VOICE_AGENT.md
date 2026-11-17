# Sarvam AI Pluggable Voice Agent Provider for DAKU

This document details the production-grade integration of **Sarvam AI** into DAKU as a modular, cloud-first Voice Agent provider.

---

## 1. Overview & Architecture

Sarvam AI is integrated as an interchangeable **Voice I/O Provider**, preserving DAKU's central intelligence, multi-pass reasoning, task planning, and permission architecture.

```text
                                  USER MICROPHONE
                                         │
                                         ▼
                                [DAKU Voice Gateway]
                                         │
                                         ▼
                                [Audio Capture / VAD]
                                         │
                                         ▼
                         [Sarvam Saaras STT (saaras:v4)]
                                         │
                       ┌─────────────────┴─────────────────┐
                       │ (Fallback on failure)             │
                       ▼                                   ▼
             [Google Web STT Provider]            [Text Console Input]
                       │                                   │
                       └─────────────────┬─────────────────┘
                                         ▼
                                    [Transcript]
                                         │
                                         ▼
                                [DAKU Brain / Router]
                                         │
                                         ▼
                                   [TaskPlanner]
                                         │
                                         ▼
                               [Permission Manager]
                               (SAFE / CONFIRMATION / BLOCKED)
                                         │
                                         ▼
                             [MCP & Native System Tools]
                                         │
                                         ▼
                                [Result Verifier]
                                         │
                                         ▼
                                     [Response]
                                         │
                                         ▼
                                  [TTS Normalizer]
                        (Indic Script, URLs, Reasoning Strip)
                                         │
                                         ▼
                         [Sarvam Bulbul v3 TTS (shubh)]
                                         │
                       ┌─────────────────┴─────────────────┐
                       │ (Fallback on failure)             │
                       ▼                                   ▼
              [Windows Native SAPI]               [Console Output]
                       │                                   │
                       └─────────────────┬─────────────────┘
                                         ▼
                                  [Audio Playback]
```

### Key Architectural Invariants:
1. **Central Brain Remains DAKU**: Voice is strictly an I/O modality. The DAKU Brain, MultiPass Reasoner, TaskPlanner, and ToolRegistry remain authoritative.
2. **Server-Side Credential Isolation**: `SARVAM_API_KEY` is strictly server-side / environment-based. It is **never** embedded in the Windows client or exposed over public APIs.
3. **Pluggable & Interchangeable**: Standardized `STTProvider` and `TTSProvider` base interfaces permit runtime swapping between Sarvam, Google STT, Windows SAPI, and text console fallbacks.
4. **Zero Local AI Footprint**: Retains DAKU's ultra-low RAM footprint (< 25 MB on Windows 11 client) with zero local neural weights.

---

## 2. Configuration & Environment Variables

Configure Sarvam AI using environment variables in `.env` or system environment:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `SARVAM_API_KEY` | *(None)* | **Required**. Sarvam AI API subscription key. |
| `SARVAM_BASE_URL` | `https://api.sarvam.ai` | Base API endpoint for Sarvam services. |
| `SARVAM_STT_MODEL` | `saaras:v4` | Sarvam STT model (`saaras:v4`, `saaras:v3`). |
| `SARVAM_STT_MODE` | `transcribe` | STT mode: `transcribe`, `translate`, `verbatim`, `translit`, `codemix`. |
| `SARVAM_LANGUAGE` | `hi-IN` | Default BCP-47 language code (e.g. `hi-IN`, `en-IN`, `bn-IN`, `ta-IN`). |
| `SARVAM_TTS_MODEL` | `bulbul:v3` | Sarvam TTS model (`bulbul:v3`). |
| `SARVAM_TTS_SPEAKER` | `shubh` | Voice persona (`shubh`, `aditya`, `ritu`, `priya`, `neha`, etc.). |
| `SARVAM_TTS_PACE` | `1.0` | Speech pace multiplier (`0.5` to `2.0`). |
| `SARVAM_TTS_TEMPERATURE` | `0.6` | Generation temperature (`0.01` to `1.0`). |
| `SARVAM_LLM_MODEL` | `sarvam-105b-conversations` | Conversational model (`sarvam-105b-conversations`, `sarvam-105b`). |
| `DAKU_STT_PROVIDER` | `sarvam` | Active STT provider (`sarvam`, `google_stt`, `mic`, `text_fallback`). |
| `DAKU_TTS_PROVIDER` | `sarvam` | Active TTS provider (`sarvam`, `windows_sapi`, `text_fallback`). |
| `DAKU_VOICE_STORE_AUDIO` | `false` | Privacy flag. If `false`, audio is never permanently saved. |
| `DAKU_VOICE_STORE_TRANSCRIPTS` | `false` | Privacy flag. If `false`, transcripts are never logged or stored. |
| `SARVAM_REQUEST_TIMEOUT` | `15.0` | HTTP request timeout in seconds. |
| `SARVAM_MAX_RETRIES` | `3` | Maximum bounded retries for transient errors. |
| `SARVAM_BACKOFF_FACTOR` | `0.5` | Exponential backoff factor in seconds. |

---

## 3. Speech-To-Text: Sarvam Saaras v4 (`voice/providers/sarvam_stt.py`)

### Capabilities:
- Communicates with `POST https://api.sarvam.ai/speech-to-text`.
- Accepts 16-bit PCM WAV, MP3, BytesIO, or file path.
- Standard-library RFC 7578 multipart/form-data encoder (no `requests` dependency required).
- Supports all 5 Saaras output modes:
  - `transcribe`: Standard natural transcription.
  - `translate`: Direct translation to English.
  - `verbatim`: Word-for-word including speech fillers.
  - `translit`: Transliteration into Latin script.
  - `codemix`: Optimized for mixed Hindi-English speech.

### Normalized Output:
```json
{
  "text": "नमस्ते, मैं डाकू हूँ",
  "language": "hi-IN",
  "provider": "sarvam",
  "model": "saaras:v4",
  "request_id": "req-123456",
  "latency_ms": 142.5
}
```

---

## 4. Text-To-Speech: Sarvam Bulbul v3 (`voice/providers/sarvam_tts.py`)

### Capabilities:
- Communicates with `POST https://api.sarvam.ai/text-to-speech`.
- Default model: `bulbul:v3`.
- Default speaker: `shubh`. Supports 30+ verified voices (e.g. `aditya`, `ritu`, `priya`, `neha`, `amit`, `kavya`, `ishita`, `shreya`).
- Strict compliance: Rejects deprecated and unsupported parameters like `pitch` and `loudness`.
- Automatic base64 audio decoding to raw WAV bytes.
- Direct memory playback on Windows via native `winsound.PlaySound` (0 MB RAM, 0 disk I/O).

---

## 5. TTS Normalizer (`voice_agent/normalizer.py`)

Before text is synthesized by Bulbul v3, `TTSNormalizer` applies rule-based cleansing:
1. **Preserves Native Indic Script**: Existing Devanagari, Bengali, Tamil, Telugu characters are preserved without modification.
2. **Contextual Hinglish Normalization**: Converts common conversational Hinglish grammar words into Devanagari script (e.g. *"Aapka order confirm ho gaya hai"* ➔ *"आपका order confirm हो गया है।"*).
3. **Preserves English Technical Terms**: Nouns like `RAM`, `CPU`, `Notepad`, `Chrome`, `Windows`, `PDF`, `GB`, `MB` are kept strictly in English Latin script.
4. **URL & IP Normalization**: Rewrites `https://google.com` to `"google dot com"` and `127.0.0.1` to `"127 point 0 point 0 point 1"`.
5. **Strips Reasoning Artifacts**: Completely removes `<think>...</think>` tags generated by reasoning models.
6. **Strips Tool & Debug Data**: Removes raw JSON dicts (`{"success": true}`), markdown fences (` ``` `), and `[DAKU (...)]` logs.

---

## 6. Multi-Tier Fallback Cascade

DAKU provides automatic failover across all voice modalities:

### STT Cascade:
1. **Sarvam Saaras v4**: Primary Indian-language STT.
2. **Google Web STT**: Automatic cloud fallback on network error, 429, or missing API key.
3. **Console Text Input**: Terminal keyboard fallback if microphone hardware or audio driver fails.

### TTS Cascade:
1. **Sarvam Bulbul v3**: Primary neural Indian-language TTS.
2. **Windows Native SAPI**: Offline, 0 MB RAM system synthesizer (`Microsoft David`, `Microsoft Zira`).
3. **Console Text Print**: Headless fallback for terminal environments.

---

## 7. Security & Privacy Controls

1. **Client Isolation**:
   - The Windows client (`client.py`) never handles `SARVAM_API_KEY`.
   - In client-server deployments, the client streams audio to `/api/voice/transcribe` and receives audio from `/api/voice/synthesize` hosted securely on the remote server.
2. **Secret Redaction**:
   - `_mask_secret()` ensures API keys appear only as `sar...345` in diagnostic logs.
   - Headers and keys are never logged in exception messages.
3. **Permission Enforcement**:
   - Dangerous tool executions (`CONFIRMATION_REQUIRED`) always trigger the voice confirmation handler.
   - Provider failure or audio dropout **never** bypasses user authorization.
4. **Privacy Invariant**:
   - Audio recordings and transcriptions are held only transiently in memory for the duration of the turn.
   - Permanent storage is disabled by default (`DAKU_VOICE_STORE_AUDIO=false`, `DAKU_VOICE_STORE_TRANSCRIPTS=false`).

---

## 8. Verification & Test Suite

### Running Unit Tests (Offline / Mocked):
Unit tests do not require a live API key and run completely offline using mocks:
```bash
py -m unittest tests.test_sarvam_stt tests.test_sarvam_tts tests.test_voice_pipeline tests.test_voice_fallback
```

### Running the Full Regression Suite:
```bash
py -m unittest discover tests
```

### Running Live Tests:
To test against live Sarvam AI endpoints, export `SARVAM_API_KEY` in `.env`:
```bash
$env:SARVAM_API_KEY="your_actual_sarvam_api_key"
py -m unittest tests.test_sarvam_stt -k test_live_sarvam_stt
py -m unittest tests.test_sarvam_tts -k test_live_sarvam_tts
```

---

## 9. Troubleshooting Guide

| Issue | Root Cause | Solution |
| :--- | :--- | :--- |
| `HTTP 401 Unauthorized` | Invalid or expired `SARVAM_API_KEY`. | Verify the key in your [Sarvam AI Dashboard](https://dashboard.sarvam.ai/) and set in `.env`. |
| `HTTP 429 Rate Limit` | API request quota reached. | Bounded backoff retries automatically; check account tier. |
| `No speech detected` | Ambient noise or low microphone gain. | Adjust microphone levels in Windows Settings; fallback to keyboard input is available. |
| `No audio playback` | Audio output muted or driver missing. | SAPI fallback automatically engages. |

---

## 10. Streaming Roadmap

- **Phase 1 (Complete)**: Rock-solid REST STT + REST TTS with base64 audio decoding, automatic retry backoff, and full multi-tier fallback.
- **Phase 2 (Architecture Ready)**: `stream_synthesize()` generator hook enabled for chunked audio playback.
- **Phase 3**: Full low-latency WebSocket duplex audio streaming.
