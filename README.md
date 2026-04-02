# Meeting Summary Service

Scans a Google Drive folder for meeting transcripts, exports transcript text, sends it to OpenAI for a structured summary, and writes a companion summary file to another Drive folder. A manifest prevents duplicate processing.

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
- `SUMMARY_FORMAT`: `markdown` or `gdoc` (default `markdown`).
- `MANIFEST_PATH`: Optional, defaults to `manifest.json`.
- `TRANSCRIPT_MIME_TYPES`: Optional CSV list of allowed MIME types.

## Run

```bash
python -m meeting_summary.cli --dry-run
python -m meeting_summary.cli
```

## Tests

```bash
pytest
```
