# DocuVoice RAG 🎙️📄

Upload a PDF, ask it questions out loud, and get answers back — in text and in voice. DocuVoice RAG is a voice-powered document assistant built on top of a Retrieval-Augmented Generation (RAG) pipeline, using AssemblyAI for speech-to-text so you don't have to type a single question.

**🔗 Live demo:** [docuvoice-rag-gj8vc5os5hp8cngmylbdtu.streamlit.app](https://docuvoice-rag-gj8vc5os5hp8cngmylbdtu.streamlit.app/)

Built for the [AssemblyAI Voice Agent Hackathon](https://lablab.ai/ai-hackathons/assemblyai-voice-agent-hackathon) on lablab.ai.

---

## What it does

Most PDF chatbots make you type. DocuVoice RAG lets you just talk to your documents.

1. **Upload** a PDF through the web app.
2. **Ask** your question by voice — hit record, ask your question, stop. No typing needed.
3. **AssemblyAI** transcribes your voice into text in real time.
4. That text is automatically sent into a **RAG pipeline**: it gets embedded, matched against the most relevant chunks of your PDF in a vector database, and passed to an LLM as context.
5. You get an answer back — as text, and also read aloud through **text-to-speech**, so the whole interaction can happen without touching the keyboard.

It's meant to feel less like "chatting with a bot" and more like asking a question out loud and getting a spoken answer back.

---

## How it works

```
   Your voice
       │
       ▼
AssemblyAI (speech-to-text)
       │
       ▼
   Question (text)
       │
       ▼
  Embed question ──► Qdrant vector search ──► top-k relevant chunks
       │
       ▼
   LLM (Groq) generates answer using those chunks
       │
       ▼
   Answer shown as text + converted to speech (played back to you)
```

PDF ingestion runs the same way: the file is chunked, each chunk is embedded, and the vectors are stored in Qdrant so they can be searched later. Both ingestion and querying run as background jobs through Inngest, so a slow embedding call or a flaky API call doesn't take down the app.

---

## Try it yourself

1. Open the [live app](https://docuvoice-rag-gj8vc5os5hp8cngmylbdtu.streamlit.app/).
2. Upload a PDF (a guide, an article, a report — anything text-based works).
3. Wait for the "ingestion triggered" confirmation.
4. Scroll down to the voice section, hit record, and ask a question about the PDF.
5. Stop the recording — the question gets transcribed automatically and the answer comes back in text and audio.

You can also just type your question if you'd rather not use the mic — both work side by side.

---

## Running it locally

### Prerequisites

- Python 3.12+
- Docker (for a local Qdrant instance)
- Node.js (for the Inngest Dev Server)
- A free [Groq API key](https://console.groq.com/keys)
- A free [AssemblyAI API key](https://www.assemblyai.com/dashboard)

### Setup

```bash
git clone https://github.com/<your-username>/DocuVoice-RAG.git
cd DocuVoice-RAG

python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # macOS/Linux

pip install -r requirements.txt

docker run -d --name qdrantRagDb -p 6333:6333 -v "$(pwd)/qdrant_storage:/qdrant/storage" qdrant/qdrant
```

Create a `.env` file:

```
GROQ_API_KEY=your_groq_key_here
ASSEMBLYAI_API_KEY=your_assemblyai_key_here
```

### Run it

You'll need three things running at once, each in its own terminal:

```bash
# Terminal 1 — Inngest Dev Server
npx inngest-cli@latest dev

# Terminal 2 — Backend (FastAPI + Inngest functions)
python -m uvicorn main:app --reload

# Terminal 3 — Frontend
streamlit run streamlit_app.py
```

Locally, the app auto-detects dev mode (no `INNGEST_SIGNING_KEY` set) and talks to the Inngest Dev Server on `localhost:8288`, and to Qdrant on `localhost:6333` — no cloud accounts needed to develop and test.

---

## Deploying it

The same codebase runs locally or in production, switching behavior based on which environment variables are present.

1. Create a free cluster on [Qdrant Cloud](https://cloud.qdrant.io) → get a URL and API key.
2. Create a free account on [Inngest Cloud](https://app.inngest.com) → get a Signing Key and Event Key.
3. Deploy `main.py` to [Render](https://render.com) (or any host) as a web service.
   - Build command: `pip install -r requirements.txt`
   - Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - Set all five keys above (plus `GROQ_API_KEY` and `ASSEMBLYAI_API_KEY`) as environment variables.
4. In the Inngest Cloud dashboard, sync your backend using `https://<your-backend>/api/inngest`.
5. Deploy `streamlit_app.py` to [Streamlit Community Cloud](https://share.streamlit.io), with the matching keys set in **Secrets**.

---

## Known limitations

- Render's free tier spins down after inactivity, so the first request after idling can take 30–60+ seconds.
- Voice output depends on an external TTS service; on rare occasions a network hiccup can cause it to briefly fail (retrying usually fixes it).
- This is a demo/portfolio-scale deployment — no authentication, single free-tier instances. A production version would need rate limiting, auth, and paid infrastructure to avoid cold starts.
- Retrieval quality depends on how the PDF is structured; very technical or image-heavy documents may retrieve less precisely.


