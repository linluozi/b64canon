"""Tests for b64canon.  Run with: python -m pytest tests -q"""

from __future__ import annotations

import base64
import json
import os
import random
import subprocess
import sys

import pytest

from b64canon import (
    Diagnostic,
    NonCanonicalBase64,
    diagnose,
    is_canonical,
    normalize,
    validate,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

VALID = [
    ("", b""),
    ("MTIz", b"123"),
    ("TWFu", b"Man"),
    ("YQ==", b"a"),
    ("YWI=", b"ab"),
    ("YWJj", b"abc"),
    ("//79", b"\xff\xfe\xfd"),
]

INVALID = [
    # (input, expected reason, expected index or None)
    ("MTIz=", "bad_length", None),          # 5 chars: the icalendar case
    ("A", "bad_length", None),
    ("AAA", "bad_length", None),
    ("AAAAA", "bad_length", None),
    ("AA=A", "padding_in_middle", 2),
    ("=AAA", "padding_in_middle", 0),
    ("YQ=A", "padding_in_middle", 2),
    ("AA===", "too_much_padding", 2),
    ("====", "too_much_padding", 0),
    ("INVALID!", "non_alphabet", 7),
    ("a b", "non_alphabet", 1),
    ("AAAA\n", "non_alphabet", 4),
    ("_-", "non_alphabet", 0),
    (b"\xff", "non_alphabet", 0),
    ("YR==", "non_zero_trailing_bits", None),
    ("YWJ=", "non_zero_trailing_bits", None),
]


@pytest.mark.parametrize(("text", "expected"), VALID)
def test_valid_inputs_validate_and_round_trip(text, expected):
    assert diagnose(text).ok is True
    assert is_canonical(text) is True
    assert validate(text) == expected
    # bytes input behaves the same as str input
    assert validate(text.encode("ascii")) == expected


@pytest.mark.parametrize(("text", "reason", "index"), INVALID)
def test_invalid_inputs_report_the_right_reason(text, reason, index):
    diag = diagnose(text)
    assert diag.ok is False
    assert diag.reason == reason, f"{text!r} -> {diag}"
    assert diag.index == index
    assert is_canonical(text) is False
    with pytest.raises(NonCanonicalBase64) as excinfo:
        validate(text)
    assert excinfo.value.reason == reason
    assert excinfo.value.index == index


def test_padding_character_is_never_reported_as_alphabet_error():
    # '=' must be classified as a padding problem, not as a bad character.
    assert diagnose("YQ==").ok is True


def test_diagnostic_is_str_friendly():
    diag = Diagnostic("bad_length", None, "length 5 is not a multiple of 4")
    assert "bad_length" in str(diag)
    assert "multiple of 4" in str(diag)
    assert str(Diagnostic("ok")) == "ok"


def test_validate_returns_real_bytes():
    assert isinstance(validate("MTIz"), bytes)
    assert validate("MTIz") == b"123"


def test_type_error_for_unsupported_types():
    with pytest.raises(TypeError):
        diagnose(123)  # type: ignore[arg-type]
    assert is_canonical(123) is False  # type: ignore[arg-type]


def test_normalize_repairs_non_canonical_spellings():
    assert normalize("MTIz=") == "MTIz"
    assert normalize("YR==") == "YQ=="
    assert normalize("YWJ=") == "YWI="
    # already canonical input is returned unchanged
    for text, _ in VALID:
        assert normalize(text) == text
    # something that cannot be decoded is a hard error, not a silent repair
    with pytest.raises(NonCanonicalBase64):
        normalize("INVALID!")


def test_normalize_output_is_always_canonical():
    for text, _, _ in INVALID:
        try:
            fixed = normalize(text)
        except NonCanonicalBase64:
            continue
        assert is_canonical(fixed) is True, f"{text!r} -> {fixed!r}"


def test_random_bytes_are_canonical_after_encoding():
    rng = random.Random(20261102)
    seen = set()
    for _ in range(200):
        raw = bytes(rng.randrange(256) for _ in range(rng.randrange(0, 64)))
        encoded = base64.b64encode(raw).decode("ascii")
        assert is_canonical(encoded) is True
        assert validate(encoded) == raw
        seen.add(encoded)
    # the corpus really is varied, not 200 copies of the same string
    assert len(seen) > 180


def test_every_reason_string_is_covered():
    reasons = set()
    for text, _ in VALID:
        reasons.add(diagnose(text).reason)
    for text, _, _ in INVALID:
        reasons.add(diagnose(text).reason)
    assert reasons == {
        "ok",
        "bad_length",
        "padding_in_middle",
        "too_much_padding",
        "non_alphabet",
        "non_zero_trailing_bits",
    }


def _run_cli(args, stdin=None):
    return subprocess.run(
        [sys.executable, "-m", "b64canon", *args],
        input=stdin,
        capture_output=True,
        cwd=ROOT,
    )


def test_cli_exit_codes_and_streams():
    ok = _run_cli([], stdin=b"MTIz")
    assert ok.returncode == 0
    assert b"ok" in ok.stdout

    bad = _run_cli([], stdin=b"MTIz=")
    assert bad.returncode == 1
    assert b"bad_length" in bad.stderr


def test_cli_json_output():
    proc = _run_cli(["--json"], stdin=b"MTIz=")
    assert proc.returncode == 1
    payload = json.loads(proc.stdout.decode())
    assert payload["ok"] is False
    assert payload["reason"] == "bad_length"
    assert payload["index"] is None
    assert payload["detail"] == "length 5 is not a multiple of 4"
    assert "multiple of 4" in payload["message"]


def test_cli_normalize():
    proc = _run_cli(["--normalize"], stdin=b"MTIz=")
    assert proc.returncode == 0
    assert proc.stdout.decode().strip() == "MTIz"


def test_cli_missing_file_is_usage_error():
    proc = _run_cli(["/nonexistent/input.b64"])
    assert proc.returncode == 2
    assert b"b64canon:" in proc.stderr
