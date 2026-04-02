from meeting_summary.drive_client import _decode_transcript_bytes


def test_decode_transcript_bytes_utf8() -> None:
    text = "Hello world"
    assert _decode_transcript_bytes(text.encode("utf-8")) == text


def test_decode_transcript_bytes_utf16_with_bom() -> None:
    text = "Seqinfomics transcript"
    assert _decode_transcript_bytes(text.encode("utf-16")) == text


def test_decode_transcript_bytes_invalid_utf8_fallback() -> None:
    raw = b"\xff\xfeH\x00i\x00"
    assert _decode_transcript_bytes(raw) == "Hi"
