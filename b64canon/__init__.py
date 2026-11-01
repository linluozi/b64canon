"""Strict RFC 4648 canonical base64 validation and repair.

``base64.b64decode(..., validate=True)`` only rejects characters outside the
base64 alphabet.  It happily accepts misplaced or oversized ``=`` padding and
encodings with non-zero trailing bits.  Those spellings decode to the same
bytes as their canonical form, which is exactly what makes them dangerous:
two different inputs can pass a naive "is this base64?" check while a strict
parser, a signature check or a filter disagrees about the decoded value.

This module answers three questions precisely:

* :func:`diagnose` -- why is this input not canonical?  (a reason code)
* :func:`validate` -- decode it, or raise :class:`NonCanonicalBase64`
* :func:`normalize` -- decode leniently and re-emit the canonical spelling
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass

__all__ = [
    "Diagnostic",
    "NonCanonicalBase64",
    "diagnose",
    "is_canonical",
    "normalize",
    "validate",
]
__version__ = "0.1.0"

_ALPHABET = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
)

REASONS = {
    "ok": "input is canonical RFC 4648 base64",
    "non_alphabet": "character outside the standard base64 alphabet",
    "padding_in_middle": "'=' padding appears before the end of the input",
    "too_much_padding": "more than two '=' padding characters",
    "bad_length": "length is not a multiple of 4",
    "non_zero_trailing_bits": "unused trailing bits are not zero (non-canonical encoding)",
}


@dataclass(frozen=True)
class Diagnostic:
    """The outcome of checking one input.

    ``reason`` is ``"ok"`` for canonical input, otherwise one of the keys of
    :data:`REASONS`.  ``index`` points at the first offending character when a
    single character is to blame.
    """

    reason: str
    index: int | None = None
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.reason == "ok"

    def __str__(self) -> str:
        if self.ok:
            return "ok"
        where = f" at index {self.index}" if self.index is not None else ""
        detail = f": {self.detail}" if self.detail else ""
        return f"{self.reason}{where}{detail}"


class NonCanonicalBase64(ValueError):
    """Raised by :func:`validate` when the input is not canonical base64."""

    def __init__(self, diagnostic: Diagnostic) -> None:
        self.diagnostic = diagnostic
        super().__init__(str(diagnostic))

    @property
    def reason(self) -> str:
        return self.diagnostic.reason

    @property
    def index(self) -> int | None:
        return self.diagnostic.index


def _as_text(data) -> tuple[str | None, int | None]:
    """Return ``(text, None)`` or ``(None, bad_index)`` for non-ASCII bytes."""
    if isinstance(data, str):
        return data, None
    if isinstance(data, (bytes, bytearray, memoryview)):
        raw = bytes(data)
        try:
            return raw.decode("ascii"), None
        except UnicodeDecodeError as exc:  # non-ASCII byte
            return None, exc.start
    raise TypeError(
        f"expected str or bytes, got {type(data).__name__}"
    )  # pragma: no cover - defensive


def diagnose(data) -> Diagnostic:
    """Explain whether ``data`` is canonical base64 and why not."""
    text, bad = _as_text(data)
    if text is None:
        return Diagnostic("non_alphabet", bad, "byte is not ASCII")
    if text == "":
        return Diagnostic("ok")

    for i, ch in enumerate(text):
        if ch != "=" and ch not in _ALPHABET:
            return Diagnostic(
                "non_alphabet", i, f"{ch!r} is not in the standard base64 alphabet"
            )

    first_pad = text.find("=")
    if first_pad != -1:
        padding = len(text) - first_pad
        if any(ch != "=" for ch in text[first_pad:]):
            return Diagnostic(
                "padding_in_middle", first_pad, "'=' padding must be a suffix"
            )
        if padding > 2:
            return Diagnostic(
                "too_much_padding", first_pad, f"{padding} '=' characters"
            )

    if len(text) % 4 != 0:
        return Diagnostic(
            "bad_length", None, f"length {len(text)} is not a multiple of 4"
        )

    try:
        decoded = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as exc:
        return Diagnostic("non_zero_trailing_bits", None, f"decode failed: {exc}")

    if base64.b64encode(decoded).decode("ascii") != text:
        return Diagnostic(
            "non_zero_trailing_bits",
            None,
            "re-encoding the decoded bytes gives a different spelling",
        )
    return Diagnostic("ok")


def is_canonical(data) -> bool:
    """``True`` when ``data`` is canonical base64 (no exception on bad types)."""
    try:
        return diagnose(data).ok
    except TypeError:
        return False


def validate(data) -> bytes:
    """Decode canonical base64 or raise :class:`NonCanonicalBase64`."""
    diag = diagnose(data)
    if not diag.ok:
        raise NonCanonicalBase64(diag)
    text, _ = _as_text(data)
    return base64.b64decode(text, validate=True)


def normalize(data) -> str:
    """Re-emit ``data`` in canonical form, repairing padding/trailing bits.

    Raises :class:`NonCanonicalBase64` when the input cannot be decoded at all
    (for example when it contains a character outside the alphabet).
    """
    text, bad = _as_text(data)
    if text is None:
        raise NonCanonicalBase64(
            Diagnostic("non_alphabet", bad, "byte is not ASCII")
        )
    try:
        raw = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise NonCanonicalBase64(
            Diagnostic("non_alphabet", None, f"cannot decode: {exc}")
        ) from exc
    return base64.b64encode(raw).decode("ascii")
