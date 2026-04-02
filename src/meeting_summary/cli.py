from __future__ import annotations

import argparse
import os
import sys

from .config import load_config
from .drive_client import DriveClient
from .manifest import Manifest
from .ollama_client import OllamaSummarizer
from .openai_client import OpenAISummarizer
from .service import SummaryService


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Summarize meeting transcripts from Google Drive")
    parser.add_argument("--source-folder", dest="source_folder_id", help="Drive folder ID for transcripts")
    parser.add_argument("--dest-folder", dest="dest_folder_id", help="Drive folder ID for summaries")
    parser.add_argument("--manifest", dest="manifest_path", help="Path to manifest JSON")
    parser.add_argument("--format", dest="summary_format", choices=["markdown", "gdoc"], help="Summary output format")
    parser.add_argument("--model", dest="openai_model", help="OpenAI model name")
    parser.add_argument("--provider", dest="llm_provider", choices=["openai", "ollama"], help="LLM provider")
    parser.add_argument("--ollama-base-url", dest="ollama_base_url", help="Ollama base URL")
    parser.add_argument("--ollama-model", dest="ollama_model", help="Ollama model name")
    parser.add_argument("--transcript-mime-types", dest="transcript_mime_types", help="CSV of allowed transcript MIME types")
    parser.add_argument("--dry-run", action="store_true", help="Do not call LLM or write to Drive")
    parser.add_argument("--force", action="store_true", help="Reprocess even if manifest has entry")
    parser.add_argument("--max-files", type=int, help="Limit number of transcripts processed")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    config = load_config(
        source_folder_id=args.source_folder_id,
        dest_folder_id=args.dest_folder_id,
        manifest_path=args.manifest_path,
        summary_format=args.summary_format,
        openai_model=args.openai_model,
        transcript_mime_types=args.transcript_mime_types,
        llm_provider=args.llm_provider,
        ollama_base_url=args.ollama_base_url,
        ollama_model=args.ollama_model,
    )

    token_path = os.getenv("GOOGLE_OAUTH_TOKEN_PATH", "token.json")
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds_path and not os.path.exists(token_path):
        raise SystemExit("Set GOOGLE_APPLICATION_CREDENTIALS or provide token.json (or GOOGLE_OAUTH_TOKEN_PATH)")

    drive = DriveClient(credentials_path=creds_path, token_path=token_path)
    if config.llm_provider == "ollama":
        summarizer = OllamaSummarizer(model=config.ollama_model, base_url=config.ollama_base_url)
    else:
        summarizer = OpenAISummarizer(config.openai_model)
    manifest = Manifest(config.manifest_path)

    service = SummaryService(config, drive, summarizer, manifest)
    report = service.run(dry_run=args.dry_run, force=args.force, max_files=args.max_files)

    print(f"Processed: {len(report.processed)}")
    if report.processed:
        print("  " + "\n  ".join(report.processed))
    print(f"Skipped: {len(report.skipped)}")
    if report.skipped:
        print("  " + "\n  ".join(report.skipped))
    if report.errors:
        print(f"Errors: {len(report.errors)}")
        print("  " + "\n  ".join(report.errors))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
