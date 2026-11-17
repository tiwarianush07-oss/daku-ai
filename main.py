"""
DAKU — Personal Voice AI Agent
Phase 1: Voice MVP (Microphone / Text -> STT -> Cloud Brain -> TTS -> Spoken Response)
Optimized for ultra-low memory & CPU on Windows 11.
"""

import os
import sys
import time
from pathlib import Path

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from brain.router import Brain
from config.settings import settings
from voice.stt import SpeechToTextEngine
from voice.tts import TextToSpeechEngine


def print_banner():
    print("=" * 60)
    print("                DAKU — PERSONAL VOICE AI AGENT        ")
    print("               PHASE 2: LOCAL COMPUTER AGENT          ")
    print("=" * 60)
    print(f"Mode          : {settings.DAKU_MODE}")
    print(f"Model Provider: {settings.MODEL_PROVIDER} ({settings.MODEL_NAME})")
    print(f"TTS Provider  : {settings.TTS_PROVIDER} ({settings.TTS_VOICE_NAME})")
    print(f"STT Provider  : {settings.STT_PROVIDER}")
    print(f"API Key Status: {'Configured (Live Cloud)' if settings.has_api_key() else 'Offline Demo Mode'}")
    print("-" * 60)
    if not settings.has_api_key():
        print("DAKU is running in offline demo mode. Configure an AI provider to enable cloud intelligence.")
    print("Commands      : Press [Enter] to speak/type, or type 'exit' to quit.")
    print("=" * 60)


def main():
    if "--hud" in sys.argv:
        import threading
        import webbrowser
        from server.daku_server import create_server
        port = settings.DAKU_SERVER_PORT
        host = settings.DAKU_SERVER_HOST
        server = create_server(host=host, port=port)
        hud_url = f"http://{host}:{port}/hud"
        print("=" * 60)
        print("       DAKU — SOLAR SWARM HUD VISUAL INTERFACE       ")
        print("=" * 60)
        print(f"[DAKU] Opening Solar HUD at {hud_url}...")
        threading.Timer(0.8, lambda: webbrowser.open(hud_url)).start()
        server.start(blocking=True)
        return

    print_banner()

    tts = TextToSpeechEngine(
        provider=settings.TTS_PROVIDER,
        voice_name=settings.TTS_VOICE_NAME,
        rate=settings.TTS_RATE,
    )
    stt = SpeechToTextEngine(provider=settings.STT_PROVIDER)

    from voice.confirmation import VoiceConfirmationHandler
    from tools.permissions import PermissionManager
    from tools.registry import ToolRegistry

    voice_handler = VoiceConfirmationHandler(tts=tts, stt=stt)
    perm_mgr = PermissionManager(voice_handler=voice_handler)
    registry = ToolRegistry(permission_manager=perm_mgr)
    brain = Brain(tool_registry=registry)

    # Initial friendly startup greeting (silent in text mode or spoken if requested)
    print("\n[DAKU] Ready. Press [Enter] to talk with DAKU.")

    while True:
        try:
            # Push-to-talk trigger
            trigger = input("\n[Press Enter to talk / 'q' to quit]: ")
            if trigger.strip().lower() in ("q", "quit", "exit"):
                print("[DAKU] Goodbye!")
                tts.speak("Goodbye!")
                break

            # Acknowledge prompt
            print("[DAKU] Yes?")
            
            # Listen / input
            user_input = stt.listen(prompt_text="I'm listening...")
            if not user_input or not user_input.strip():
                print("[DAKU] No input detected.")
                continue

            if user_input.strip().lower() in ("exit", "quit", "q", "bye"):
                print("[DAKU] Goodbye!")
                tts.speak("Goodbye!")
                break

            print(f"[DAKU Thinking] Processing '{user_input}'...")
            start_time = time.time()
            reply = brain.think(user_input)
            elapsed = time.time() - start_time

            print(f"[DAKU ({elapsed:.2f}s)]: {reply}")
            
            # Voice response output
            tts.speak(reply)

        except KeyboardInterrupt:
            print("\n[DAKU] Session terminated by user.")
            break
        except Exception as e:
            print(f"[DAKU Error] {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "doctor":
            from doctor import run_doctor
            remote_flag = "--remote" in sys.argv
            sys.exit(0 if run_doctor(remote_mode=remote_flag) else 1)
        elif cmd == "client":
            import client
            sys.argv.pop(1)
            client.main()
            sys.exit(0)
        elif cmd == "server":
            import server.daku_server as ds
            sys.argv.pop(1)
            ds.main()
            sys.exit(0)
        elif cmd in ("hud", "desktop-hud"):
            from ui.desktop_hud import main as hud_main
            sys.argv.pop(1)
            hud_main()
            sys.exit(0)
    main()
