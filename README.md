# Say It Better

A voice-first AI communication coach that helps you find the right words in the moment — powered by Gemini Live API.

## What it does

**Say It Better** has three modes:

- **Voice mode** — Ramble out loud about something you need to say. The AI listens, then gives you: a one-sentence summary of what's really going on, the exact words to say, and one delivery tip based on your tone.
- **Text mode** — Type a messy description of what you need to communicate. The AI speaks a polished version out loud — directly to the person sitting with you.
- **Decide mode** — Have a back-and-forth voice conversation with an AI acting as a trusted friend to help you think through a decision.

## Demo

This app runs locally and requires microphone access. There is no hosted demo.

**GitHub:** https://github.com/Rachana078/say-it-better

## Tech Stack

- **AI:** Gemini Live API (`gemini-2.5-flash-native-audio-latest`) — real-time audio streaming
- **Backend:** Python, WebSockets (`websockets`), PyAudio
- **Frontend:** Vanilla JS, HTML/CSS (no framework)

## Setup

### Prerequisites

- Python 3.10+
- A Gemini API key — get one at [Google AI Studio](https://aistudio.google.com/apikey)
- A browser (Chrome recommended for microphone access)
- PortAudio installed (required by PyAudio):
  - macOS: `brew install portaudio`
  - Ubuntu/Debian: `sudo apt-get install portaudio19-dev`

### 1. Clone the repo

```bash
git clone https://github.com/Rachana078/say-it-better.git
cd say-it-better
```

### 2. Create a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install google-genai websockets pyaudio python-dotenv
```

### 4. Add your API key

Create a `.env` file in the project root:

```
GEMINI_API_KEY=your_api_key_here
```

### 5. Run the backend

```bash
python backend/main.py
```

You should see `API key loaded` and the WebSocket server starts on `ws://localhost:8765`.

### 6. Open the frontend

Open `frontend/index.html` directly in your browser (no server needed):

```bash
open frontend/index.html   # macOS
# or just double-click the file
```

## Usage

### Voice mode
1. Click **Voice** to select the mode
2. Click **Start** and speak — ramble freely about what you need to say to someone
3. Click **Stop** when done
4. The AI responds with a summary, exact words to use, and a delivery tip

### Text mode
1. Click **Text** to select the mode
2. Type a description of what you need to communicate and who to
3. Click **Send**
4. The AI speaks a polished version out loud — for the person in the room with you

### Decide mode
1. Click **Decide** to select the mode
2. Click **Start** and describe your decision out loud
3. Have a natural back-and-forth conversation — the AI acts as a trusted friend, not a life coach
4. Click **Stop** to end the session
