import asyncio
from pathlib import Path
import time
import base64

import streamlit as st
import inngest
from dotenv import load_dotenv
import os
import requests
from voice_input import transcribe_audio, text_to_speech

load_dotenv()

st.set_page_config(page_title="RAG Ingest PDF", page_icon="📄", layout="centered")

# Presence of INNGEST_SIGNING_KEY signals we're pointed at Inngest Cloud
# (production) rather than the local Inngest Dev Server.
INNGEST_SIGNING_KEY = os.getenv("INNGEST_SIGNING_KEY")
INNGEST_EVENT_KEY = os.getenv("INNGEST_EVENT_KEY")
IS_PRODUCTION = bool(INNGEST_SIGNING_KEY)


@st.cache_resource
def get_inngest_client() -> inngest.Inngest:
    return inngest.Inngest(
        app_id="rag_app",
        is_production=IS_PRODUCTION,
        signing_key=INNGEST_SIGNING_KEY,
        event_key=INNGEST_EVENT_KEY,
    )


def save_uploaded_pdf(file) -> Path:
    # Kept for optional local debugging/inspection — not required by the
    # pipeline anymore, since PDF bytes now travel directly in the event.
    uploads_dir = Path("uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)
    file_path = uploads_dir / file.name
    file_bytes = file.getbuffer()
    file_path.write_bytes(file_bytes)
    return file_path


async def send_rag_ingest_event(file_name: str, pdf_bytes: bytes) -> None:
    client = get_inngest_client()
    await client.send(
        inngest.Event(
            name="rag/ingest_pdf",
            data={
                "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
                "source_id": file_name,
            },
        )
    )


st.title("Upload a PDF to Ingest")
uploaded = st.file_uploader("Choose a PDF", type=["pdf"], accept_multiple_files=False)

if uploaded is not None:
    with st.spinner("Uploading and triggering ingestion..."):
        pdf_bytes = uploaded.getvalue()
        # Kick off the event and block until the send completes
        asyncio.run(send_rag_ingest_event(uploaded.name, pdf_bytes))
        # Small pause for user feedback continuity
        time.sleep(0.3)
    st.success(f"Triggered ingestion for: {uploaded.name}")
    st.caption("You can upload another PDF if you like.")

st.divider()
st.title("Ask a question about your PDFs")

st.subheader("🎙️ Or ask by voice")
audio = st.audio_input("Record your question")

if audio is not None:
    if "last_audio_id" not in st.session_state or st.session_state.last_audio_id != audio.file_id:
        with st.spinner("Transcribing..."):
            try:
                text = transcribe_audio(audio.getvalue())
                st.session_state.voice_question = text
                st.session_state.last_audio_id = audio.file_id
                st.session_state.auto_submit = True
            except Exception as e:
                st.error(f"Transcription failed: {e}")


async def send_rag_query_event(question: str, top_k: int) -> None:
    client = get_inngest_client()
    result = await client.send(
        inngest.Event(
            name="rag/query_pdf_ai",
            data={
                "question": question,
                "top_k": top_k,
            },
        )
    )

    return result[0]


def _inngest_api_base() -> str:
    # Local dev server default; Inngest Cloud in production (or override via env).
    default_base = "https://api.inngest.com/v1" if IS_PRODUCTION else "http://127.0.0.1:8288/v1"
    return os.getenv("INNGEST_API_BASE", default_base)


def _inngest_api_headers() -> dict:
    # The local Dev Server needs no auth; Inngest Cloud requires the signing key.
    if IS_PRODUCTION and INNGEST_SIGNING_KEY:
        return {"Authorization": f"Bearer {INNGEST_SIGNING_KEY}"}
    return {}


def fetch_runs(event_id: str) -> list[dict]:
    url = f"{_inngest_api_base()}/events/{event_id}/runs"
    resp = requests.get(url, headers=_inngest_api_headers())
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", [])


def fetch_run_detail(run_id: str) -> dict:
    # The events/{id}/runs list endpoint only returns bare status metadata.
    # The per-run endpoint includes the actual "output" field, which on a
    # failed run holds the exception name/message/stack.
    url = f"{_inngest_api_base()}/runs/{run_id}"
    resp = requests.get(url, headers=_inngest_api_headers())
    resp.raise_for_status()
    data = resp.json()
    return data.get("data", data)


def wait_for_run_output(event_id: str, timeout_s: float = 300.0, poll_interval_s: float = 0.5) -> dict:
    start = time.time()
    last_status = None
    completed_but_empty_since = None
    while True:
        runs = fetch_runs(event_id)
        if runs:
            run = runs[0]
            status = run.get("status")
            last_status = status or last_status
            if status in ("Completed", "Succeeded", "Success", "Finished"):
                output = run.get("output")
                if not output:
                    # The runs-list endpoint often doesn't carry output — fetch the
                    # per-run detail endpoint instead, same as we do for Failed runs.
                    try:
                        detail_run = fetch_run_detail(run["run_id"])
                        output = detail_run.get("output")
                    except Exception:
                        output = None
                if output:
                    return output
                if completed_but_empty_since is None:
                    completed_but_empty_since = time.time()
                elif time.time() - completed_but_empty_since > 5.0:
                    return {}
            if status in ("Failed", "Cancelled"):
                # Pull the detailed run record for the real error; fall back to
                # the bare run dict if that call itself fails for some reason.
                try:
                    detail_run = fetch_run_detail(run["run_id"])
                    detail = detail_run.get("output") or detail_run.get("error") or detail_run
                except Exception:
                    detail = run.get("output") or run.get("error") or run
                raise RuntimeError(f"Function run {status}: {detail}")
        if time.time() - start > timeout_s:
            raise TimeoutError(f"Timed out waiting for run output (last status: {last_status})")
        time.sleep(poll_interval_s)


question = st.text_input("Your question", value=st.session_state.get("voice_question", ""))
top_k = st.number_input("How many chunks to retrieve", min_value=1, max_value=20, value=5, step=1)
manual_ask = st.button("Ask")

should_run = manual_ask or st.session_state.get("auto_submit", False)

if should_run and question.strip():
    st.session_state.auto_submit = False

    with st.spinner("Sending event and generating answer..."):
        event_id = asyncio.run(send_rag_query_event(question.strip(), int(top_k)))
        output = wait_for_run_output(event_id)
        answer = output.get("answer", "")
        sources = output.get("sources", [])
        num_contexts = output.get("num_contexts", 0)

    st.caption(f"Retrieved {num_contexts} chunk(s) from the vector store")
    if not answer:
        st.warning("Got an empty answer. Raw output from the run, for debugging:")
        st.json(output)

    st.subheader("Answer")
    st.write(answer or "(No answer)")
    if sources:
        st.caption("Sources")
        for s in sources:
            st.write(f"- {s}")

    if answer:
        with st.spinner("Generating voice answer..."):
            try:
                audio_answer = text_to_speech(answer)
                st.audio(audio_answer, format="audio/mp3")
            except Exception as e:
                st.warning(f"Voice output failed: {e}")