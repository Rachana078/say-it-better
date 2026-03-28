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

Open naturally for the relationship — casual
and warm for a friend, respectful for a
professor or boss, gentle for family.
Do NOT use a fixed opening line.

Deliver the message in 3 to 4 sentences.
Natural, human, appropriate for the
relationship and emotional tone detected.

Rules:
- Speak directly TO the other person
- Do not address the user who typed
- Do not explain what you are doing
- Do not say you are an AI
- Do not use the words "the user" or "they said"
- Keep it under 20 seconds of speaking"""

DECIDE_SYSTEM_PROMPT = """You are a sharp, warm, honest friend. The user
is going to talk to you about a decision they
are struggling with.

Listen carefully. Ask natural follow up questions
that get to the heart of what they actually want.
Push back gently when they contradict themselves.
Notice when their energy changes.

After 2-3 exchanges when you have enough context,
give them your honest opinion. Be direct. Tell them
what you think they should do and why. Don't hedge.
Don't give pros and cons lists. Just be real with them
like a trusted friend would be.

Never say you are an AI. Just be present and human."""

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


async def run_decide_conversation() -> None:
    """Continuous real-time voice conversation for decide mode.
    Runs until cancelled (user clicks stop / WebSocket closes)."""
    client = genai.Client(api_key=api_key, http_options={"api_version": "v1alpha"})

    config = types.LiveConnectConfig(
        system_instruction=DECIDE_SYSTEM_PROMPT,
        response_modalities=["AUDIO"],
    )

    pa = pyaudio.PyAudio()
    input_stream = pa.open(
        format=FORMAT, channels=CHANNELS, rate=INPUT_RATE,
        input=True, frames_per_buffer=CHUNK,
    )
    output_stream = pa.open(
        format=FORMAT, channels=CHANNELS, rate=OUTPUT_RATE,
        output=True, frames_per_buffer=CHUNK,
    )

    loop = asyncio.get_event_loop()
    opener_done = asyncio.Event()

    async def send_audio():
        await session.send_client_content(
            turns=types.Content(
                parts=[types.Part(text="Open with one short warm line to invite them to share — like 'Hey, what's going on?' or 'What's on your mind?' — then wait.")],
                role="user"
            ),
            turn_complete=True
        )
        # Wait for opener to finish before mic starts — prevents barge-in on own greeting
        await opener_done.wait()
        while True:
            chunk = await loop.run_in_executor(None, input_stream.read, CHUNK, False)
            await session.send_realtime_input(
                audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
            )

    async def receive_audio():
        while True:
            async for response in session.receive():
                if response.data:
                    output_stream.write(response.data)
                sc = response.server_content
                if sc and sc.turn_complete:
                    if not opener_done.is_set():
                        opener_done.set()
            # Generator ended after one turn — re-enter for next turn
            await asyncio.sleep(0.05)

    try:
        async with client.aio.live.connect(model=MODEL, config=config) as session:
            print("Decide conversation started — waiting for user to end session")
            await asyncio.gather(send_audio(), receive_audio())
    finally:
        # Stop input stream first to unblock any read running in executor thread,
        # then give it a moment to return before we terminate PyAudio.
        try:
            input_stream.stop_stream()
        except Exception:
            pass
        await asyncio.sleep(0.1)
        try:
            input_stream.close()
            output_stream.stop_stream()
            output_stream.close()
            pa.terminate()
        except Exception:
            pass


async def handle_client(websocket):
    print(f"Frontend connected: {websocket.remote_address}")
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                mode = data.get("mode")
            except (json.JSONDecodeError, AttributeError):
                mode = "voice" if message == "start" else None

            if mode not in ("voice", "text", "decide"):
                continue

            print(f"Received mode: {mode}")

            try:
                await websocket.send(json.dumps({"status": "thinking"}))

                if mode == "voice":
                    session_task = asyncio.create_task(run_voice_session())
                elif mode == "text":
                    text_input = data.get("message", "")
                    session_task = asyncio.create_task(run_text_mode(text_input))
                else:
                    session_task = asyncio.create_task(run_decide_conversation())

                close_task = asyncio.create_task(websocket.wait_closed())
                done, pending = await asyncio.wait(
                    [session_task, close_task],
                    return_when=asyncio.FIRST_COMPLETED
                )
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass

                if close_task in done:
                    print("Session cancelled by client")
                    return

                result = session_task.result()

                exact_words = result
                await websocket.send(json.dumps({
                    "status": "done",
                    "exact_words": exact_words or None
                }))

            except Exception as e:
                print(f"Session error: {e}")
                try:
                    await websocket.send(json.dumps({
                        "status": "error",
                        "message": str(e)
                    }))
                except Exception:
                    pass

    except websockets.exceptions.ConnectionClosed:
        print("Frontend disconnected")


async def main():
    print("WebSocket server starting on ws://localhost:8765")
    async with websockets.serve(handle_client, "localhost", 8765):
        print("Ready — waiting for frontend to connect")
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down.")
