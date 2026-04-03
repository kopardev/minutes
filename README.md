# Meeting Summary Service

Scans a Google Drive folder for meeting transcripts, exports transcript text, sends it to the configured LLM provider (OpenAI, Ollama, or Gemini) for structured extraction, and writes a companion summary file to another Drive folder. A manifest prevents duplicate processing.

## Setup

1. Create a Google Cloud service account with Drive access and share both Drive folders with the service account email.
2. Download the service account JSON key.
3. Install dependencies.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

## Configuration

Set environment variables:

- `GOOGLE_APPLICATION_CREDENTIALS`: Path to service account JSON.
- `TRANSCRIPTS_FOLDER_ID`: Source Drive folder ID.
- `SUMMARIES_FOLDER_ID`: Destination Drive folder ID.
- `OPENAI_API_KEY`: OpenAI API key.
- `OPENAI_MODEL`: Optional, defaults to `gpt-5`.
- `GEMINI_API_KEY`: Gemini API key.
- `GEMINI_MODEL`: Optional, defaults to `gemini-2.5-pro`.
- `LLM_PROVIDER`: `openai`, `ollama`, or `gemini` (default `openai`).
- `OLLAMA_BASE_URL`: Optional, defaults to `http://localhost:11434`.
- `OLLAMA_MODEL`: Optional, defaults to `qwen3:14b`.
- `SUMMARY_FORMAT`: `markdown`, `gdoc`, `html`, or `pdf` (default `gdoc`).
- `MANIFEST_PATH`: Optional, defaults to `manifest.json`.
- `TRANSCRIPT_MIME_TYPES`: Optional CSV list of allowed MIME types.

## Run

```bash
python -m meeting_summary.cli --dry-run
python -m meeting_summary.cli

# Fast cloud path (OpenAI)
python -m meeting_summary.cli --use-openai --model gpt-5

# Local path (Ollama)
python -m meeting_summary.cli --provider ollama --ollama-model qwen3:14b

# Gemini path
python -m meeting_summary.cli --provider gemini --gemini-model gemini-2.5-pro

# Show live progress logs
python -m meeting_summary.cli --provider ollama --max-files 3 --verbose

# Optional: enable chunking (default is single-pass full transcript)
python -m meeting_summary.cli --provider ollama --use-chunks --max-files 3 --verbose

# Upload styled HTML summary file
python -m meeting_summary.cli --provider ollama --format html --max-files 1

# Upload PDF summary file
python -m meeting_summary.cli --provider ollama --format pdf --max-files 1
```

## Tests

```bash
pytest
```
