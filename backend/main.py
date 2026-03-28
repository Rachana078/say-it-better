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
from image_gen import card_to_base64, generate_decide_cards

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

DECIDE_SYSTEM_PROMPT = """You are a decision analyst called Say It Better.
The user is going to talk messily about a decision
they are struggling with. They will contradict
themselves, ramble, and go back and forth.

Listen to everything:
- Which option they mention with more energy and excitement
- Which option they mention flatly or with resignation
- What they keep coming back to without being asked
- What they say last — people bury the truth at the end
- Where their voice hesitates vs flows naturally

After they stop talking ask them exactly one question:
"If the outcome was identical for everyone around you —
same money, same reaction from people who matter —
what would you choose?"

Listen to their answer. Then deliver your verdict.

Start with exactly: "You already know."
Then in 2-3 sentences tell them what they already
decided based on their tone and patterns.
Be confident. Be direct. Do not hedge.
Do not say you are an AI.
Do not give pros and cons.
Just tell them what their voice already said."""

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


def extract_verdict(transcript: str) -> str | None:
    lower = transcript.lower()
    marker = "you already know"
    start = lower.find(marker)
    if start == -1:
        return transcript.strip() if transcript.strip() else None
    return transcript[start:].strip()


async def extract_decide_options(transcript: str) -> tuple[str, str]:
    """Use Gemini text API to extract the two decision options from transcript."""
    client = genai.Client(api_key=api_key)
    response = await client.aio.models.generate_content(
        model="gemini-2.0-flash",
        contents=f"""From this decision coaching session transcript, identify the two options the person was deciding between.

Return exactly two short labels (3-7 words each) in this format:
OPTION_A: [the obligatory/fear-based/should-do option]
OPTION_B: [the desired/exciting/want-to-do option]

If unclear, make a reasonable inference from context.

Transcript:
{transcript}""",
    )
    text = response.text or ""
    option_a, option_b = "Option A", "Option B"
    for line in text.strip().split('\n'):
        if 'OPTION_A:' in line:
            option_a = line.split('OPTION_A:', 1)[1].strip()
        elif 'OPTION_B:' in line:
            option_b = line.split('OPTION_B:', 1)[1].strip()
    return option_a, option_b


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


async def run_decide_session() -> dict:
    """Two-phase decide session. Returns dict with verdict, option_a, option_b."""
    client = genai.Client(api_key=api_key, http_options={"api_version": "v1alpha"})

    config = types.LiveConnectConfig(
        system_instruction=DECIDE_SYSTEM_PROMPT,
        response_modalities=["AUDIO"],
        output_audio_transcription=types.AudioTranscriptionConfig(),
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
    transcript_parts = []

    async def record_until_silence():
        silence_start = None
        while True:
            chunk = await loop.run_in_executor(None, input_stream.read, CHUNK, False)
            count = len(chunk) // 2
            shorts = struct.unpack(f"{count}h", chunk)
            rms = math.sqrt(sum(s * s for s in shorts) / count)
            if rms < SILENCE_THRESHOLD:
                if silence_start is None:
                    silence_start = loop.time()
                elif loop.time() - silence_start >= SILENCE_DURATION:
                    print("Silence detected, moving to next phase.")
                    return
            else:
                silence_start = None
            await session.send_realtime_input(
                audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
            )

    async def receive_until_turn_complete():
        async for response in session.receive():
            if response.data:
                output_stream.write(response.data)
            sc = response.server_content
            if sc:
                if sc.output_transcription and sc.output_transcription.text:
                    transcript_parts.append(sc.output_transcription.text)
                if sc.turn_complete:
                    return

    try:
        async with client.aio.live.connect(model=MODEL, config=config) as session:
            print("Decide phase 1: speak about your decision...")
            await record_until_silence()
            await receive_until_turn_complete()

            print("Decide phase 2: answer the question...")
            await record_until_silence()
            await receive_until_turn_complete()
    finally:
        input_stream.stop_stream()
        input_stream.close()
        output_stream.stop_stream()
        output_stream.close()
        pa.terminate()

    full_transcript = "".join(transcript_parts)
    print(f"\nDecide transcript: {full_transcript}")

    verdict = extract_verdict(full_transcript)
    option_a, option_b = await extract_decide_options(full_transcript)

    print(f"Verdict: {verdict}")
    print(f"Option A: {option_a} | Option B: {option_b}")

    return {"verdict": verdict, "option_a": option_a, "option_b": option_b}


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
                    session_task = asyncio.create_task(run_decide_session())

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

                if mode == "decide":
                    card_a_b64 = card_b_b64 = None
                    try:
                        card_a_b64, card_b_b64 = generate_decide_cards(
                            result.get("option_a", "Option A"),
                            result.get("option_b", "Option B"),
                            api_key
                        )
                        print("Decide cards generated")
                    except Exception as e:
                        print(f"Decide card generation failed: {e}")

                    await websocket.send(json.dumps({
                        "status": "done",
                        "mode": "decide",
                        "verdict": result.get("verdict"),
                        "option_a": result.get("option_a"),
                        "option_b": result.get("option_b"),
                        "card_a": card_a_b64,
                        "card_b": card_b_b64,
                    }))

                else:
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
