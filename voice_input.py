import os
import assemblyai as aai
from dotenv import load_dotenv
import edge_tts
import asyncio
import tempfile

load_dotenv()

aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")


def transcribe_audio(audio_bytes: bytes) -> str:
    transcriber = aai.Transcriber()
    transcript = transcriber.transcribe(audio_bytes)

    if transcript.status == aai.TranscriptStatus.error:
        raise RuntimeError(f"Transcription failed: {transcript.error}")

    return transcript.text or ""

TTS_VOICE = "en-US-AriaNeural"


async def _synthesize(text: str, output_path: str) -> None:
    communicate = edge_tts.Communicate(text, TTS_VOICE)
    await communicate.save(output_path)


def text_to_speech(text: str) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        output_path = tmp.name

    asyncio.run(_synthesize(text, output_path))

    with open(output_path, "rb") as f:
        audio_bytes = f.read()

    os.remove(output_path)
    return audio_bytes