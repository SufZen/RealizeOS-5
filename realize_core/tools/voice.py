"""
Voice tools — speech-to-text (STT) and text-to-speech (TTS).

STT: Groq Whisper API (fast, cheap transcription)
TTS: ElevenLabs API (natural voice synthesis)

Configure in .env:
  GROQ_API_KEY=gsk_...
  ELEVENLABS_API_KEY=...
  ELEVENLABS_VOICE_ID=... (optional, defaults to Rachel)
"""
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def is_stt_available() -> bool:
    """Check if speech-to-text is configured."""
    return bool(os.getenv("GROQ_API_KEY", ""))


def is_tts_available() -> bool:
    """Check if text-to-speech is configured."""
    return bool(os.getenv("ELEVENLABS_API_KEY", ""))


async def transcribe_audio(audio_path: Path, language: str = "en") -> dict:
    """
    Transcribe audio to text using Groq Whisper API.

    Args:
        audio_path: Path to audio file (mp3, wav, m4a, webm, ogg)
        language: Language code (default: en)

    Returns:
        {text: str, duration: float, error: str}
    """
    api_key = os.getenv("GROQ_API_KEY", "")
    if not api_key:
        return {"error": "GROQ_API_KEY not configured"}

    if not audio_path.exists():
        return {"error": f"Audio file not found: {audio_path}"}

    try:
        import httpx

        async with httpx.AsyncClient(timeout=60) as client:
            with open(audio_path, "rb") as f:
                resp = await client.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"file": (audio_path.name, f, "audio/mpeg")},
                    data={"model": "whisper-large-v3", "language": language},
                )

            if resp.status_code == 200:
                data = resp.json()
                return {
                    "text": data.get("text", ""),
                    "duration": data.get("duration", 0),
                }
            else:
                return {"error": f"Groq API error: {resp.status_code} {resp.text[:200]}"}

    except ImportError:
        return {"error": "httpx not installed"}
    except Exception as e:
        return {"error": str(e)[:200]}


async def synthesize_speech(
    text: str,
    output_path: Path = None,
    voice_id: str = "",
) -> dict:
    """
    Convert text to speech using ElevenLabs API.

    Args:
        text: Text to synthesize
        output_path: Where to save the audio file (default: temp file)
        voice_id: ElevenLabs voice ID (default: from env or Rachel)

    Returns:
        {audio_path: str, size: int, error: str}
    """
    api_key = os.getenv("ELEVENLABS_API_KEY", "")
    if not api_key:
        return {"error": "ELEVENLABS_API_KEY not configured"}

    voice_id = voice_id or os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

    if not output_path:
        import tempfile
        output_path = Path(tempfile.mktemp(suffix=".mp3"))

    try:
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers={
                    "xi-api-key": api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "text": text[:5000],
                    "model_id": "eleven_multilingual_v2",
                    "voice_settings": {
                        "stability": 0.5,
                        "similarity_boost": 0.75,
                    },
                },
            )

            if resp.status_code == 200:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(resp.content)
                return {
                    "audio_path": str(output_path),
                    "size": output_path.stat().st_size,
                }
            else:
                return {"error": f"ElevenLabs API error: {resp.status_code} {resp.text[:200]}"}

    except ImportError:
        return {"error": "httpx not installed"}
    except Exception as e:
        return {"error": str(e)[:200]}


def get_voice_status() -> dict:
    """Get voice integration status."""
    return {
        "stt": {
            "configured": is_stt_available(),
            "provider": "groq_whisper",
            "description": "Speech-to-text transcription",
        },
        "tts": {
            "configured": is_tts_available(),
            "provider": "elevenlabs",
            "description": "Text-to-speech synthesis",
        },
    }
