import os
import asyncio
import struct
import math
import json
import pyaudio
import websockets
from dotenv import load_dotenv
from google import genai
from google.genai import types
from image_gen import generate_card, card_to_base64

# Load .env from project root (one level up from backend/)
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

api_key = os.environ.get('GEMINI_API_KEY')

if not api_key:
    print("Error: GEMINI_API_KEY not found. Add it to the .env file in the project root.")
    exit(1)

print("API key loaded")

SYSTEM_PROMPT = """You are a communication coach called Say It Better.
The user will talk messily about something they need
to say to someone — a professor, boss, friend, doctor,
anyone. They will ramble, hesitate, and circle around
what they actually mean.

Listen to everything — their words, their tone, their
emotion, what they keep coming back to.

When they stop talking, respond with exactly three
things spoken naturally:

1. Say "Here's what's really going on:" then one
sentence summary of their situation.

2. Say "Here's exactly what to say:" then give
word-for-word what to say — natural, human,
appropriate for the relationship and tone detected.

3. Say "One tip:" then one delivery tip based on
their emotional tone.

Keep response under 30 seconds. Be warm but direct.
Never ask clarifying questions. Never say you are an AI."""

TEXT_SYSTEM_PROMPT = """You are Say It Better. The user has typed a messy
description of something they need to communicate
to someone who is physically sitting with them
right now in person.

Read their message. Understand the situation,
the relationship, and the emotional context.

Now speak DIRECTLY to the other person — not to
the user who typed. You are speaking out loud
to whoever is listening.

Start with exactly: "Hi, I wanted to share
something with you."

Then deliver the message in 3 to 4 sentences.
Natural, warm, human, appropriate for the
relationship described.

Rules:
- Speak directly TO the other person
- Do not address the user who typed
- Do not explain what you are doing
- Do not say you are an AI
- Do not use the words "the user" or "they said"
- Keep it under 20 seconds of speaking"""

MODEL = "gemini-2.5-flash-native-audio-latest"

# Audio settings
INPUT_RATE = 16000
OUTPUT_RATE = 24000
CHANNELS = 1
FORMAT = pyaudio.paInt16
CHUNK = 1024
SILENCE_THRESHOLD = 500   # RMS below this is silence
SILENCE_DURATION = 2.0    # seconds of silence before stopping


def extract_exact_words(transcript: str) -> str | None:
    lower = transcript.lower()
    start_marker = "here's exactly what to say:"
    end_marker = "one tip:"
    start = lower.find(start_marker)
    if start == -1:
        return None
    start += len(start_marker)
    end = lower.find(end_marker, start)
    if end == -1:
        text = transcript[start:].strip()
    else:
        text = transcript[start:end].strip()
    return text if text else None


async def run_voice_session() -> str | None:
    """Run one voice session. Returns exact_words or None."""
    client = genai.Client(api_key=api_key, http_options={"api_version": "v1alpha"})

    config = types.LiveConnectConfig(
        system_instruction=SYSTEM_PROMPT,
        response_modalities=["AUDIO"],
        output_audio_transcription=types.AudioTranscriptionConfig(),
    )

    pa = pyaudio.PyAudio()

    input_stream = pa.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=INPUT_RATE,
        input=True,
        frames_per_buffer=CHUNK,
    )

    output_stream = pa.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=OUTPUT_RATE,
        output=True,
        frames_per_buffer=CHUNK,
    )

    exact_words = None

    try:
        async with client.aio.live.connect(model=MODEL, config=config) as session:
            print("Connected to Live API")
            print("Speak now... (silence for 2 seconds stops recording)")

            stop_event = asyncio.Event()
            loop = asyncio.get_event_loop()

            async def send_task():
                silence_start = None
                while not stop_event.is_set():
                    chunk = await loop.run_in_executor(
                        None, input_stream.read, CHUNK, False
                    )
                    count = len(chunk) // 2
                    shorts = struct.unpack(f"{count}h", chunk)
                    rms = math.sqrt(sum(s * s for s in shorts) / count)
                    if rms < SILENCE_THRESHOLD:
                        if silence_start is None:
                            silence_start = loop.time()
                        elif loop.time() - silence_start >= SILENCE_DURATION:
                            print("Silence detected, stopping recording.")
                            stop_event.set()
                            break
                    else:
                        silence_start = None

                    await session.send_realtime_input(
                        audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
                    )

            async def receive_task():
                transcript_parts = []
                async for response in session.receive():
                    if response.data:
                        output_stream.write(response.data)
                    sc = response.server_content
                    if sc:
                        if sc.output_transcription and sc.output_transcription.text:
                            transcript_parts.append(sc.output_transcription.text)
                        if sc.turn_complete:
                            break
                return "".join(transcript_parts)

            _, transcript = await asyncio.gather(send_task(), receive_task())

            print(f"\nFull transcript: {transcript}")
            exact_words = extract_exact_words(transcript)
            if exact_words:
                print(f"\nexact_words: {exact_words}")
            else:
                print("\nexact_words: (not found in transcript)")
    finally:
        input_stream.stop_stream()
        input_stream.close()
        output_stream.stop_stream()
        output_stream.close()
        pa.terminate()

    return exact_words


async def run_text_mode(message: str) -> str:
    """Send typed message to Live API, speak it to the other person, return transcript."""
    client = genai.Client(api_key=api_key, http_options={"api_version": "v1alpha"})

    config = types.LiveConnectConfig(
        system_instruction=TEXT_SYSTEM_PROMPT,
        response_modalities=["AUDIO"],
        output_audio_transcription=types.AudioTranscriptionConfig(),
    )

    pa = pyaudio.PyAudio()
    output_stream = pa.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=OUTPUT_RATE,
        output=True,
        frames_per_buffer=CHUNK,
    )

    transcript_parts = []
    try:
        async with client.aio.live.connect(model=MODEL, config=config) as session:
            await session.send_client_content(
                turns=types.Content(
                    parts=[types.Part(text=message)],
                    role="user"
                ),
                turn_complete=True
            )

            async for response in session.receive():
                if response.data:
                    output_stream.write(response.data)
                sc = response.server_content
                if sc:
                    if sc.output_transcription and sc.output_transcription.text:
                        transcript_parts.append(sc.output_transcription.text)
                    if sc.turn_complete:
                        break
    finally:
        output_stream.stop_stream()
        output_stream.close()
        pa.terminate()

    return "".join(transcript_parts)


async def handle_client(websocket):
    print(f"Frontend connected: {websocket.remote_address}")
    try:
        async for message in websocket:
            if message == "test_text":
                test_message = "i need to tell my professor i missed two weeks because of family stuff and i have an assignment due tomorrow"
                print(f"Running text mode test: {test_message}")
                live_output = await run_text_mode(test_message)
                print(f"\nlive_output: {live_output}")
                await websocket.send(json.dumps({"status": "text_done", "live_output": live_output}))
                continue

            if message != "start":
                continue

            print("Received 'start' from frontend")

            try:
                await websocket.send(json.dumps({"status": "thinking"}))

                exact_words = await run_voice_session()

                if not exact_words:
                    await websocket.send(json.dumps({
                        "status": "done",
                        "card": None,
                        "exact_words": None
                    }))
                    continue

                # Generate card
                card_path = None
                card_b64 = None
                try:
                    card_path = generate_card(exact_words, api_key)
                    card_b64 = card_to_base64(card_path)
                    print(f"Card saved to {card_path}")
                except Exception as e:
                    print(f"Card generation failed: {e}")

                await websocket.send(json.dumps({
                    "status": "done",
                    "card": card_b64,
                    "exact_words": exact_words
                }))

            except Exception as e:
                print(f"Session error: {e}")
                await websocket.send(json.dumps({
                    "status": "error",
                    "message": str(e)
                }))

    except websockets.exceptions.ConnectionClosed:
        print("Frontend disconnected")


async def main():
    print("WebSocket server starting on ws://localhost:8765")
    async with websockets.serve(handle_client, "localhost", 8765):
        print("Ready — waiting for frontend to connect")
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
