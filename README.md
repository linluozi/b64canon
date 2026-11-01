# b64canon

Strict [RFC 4648](https://www.rfc-editor.org/rfc/rfc4648#section-3.5) **canonical** base64 validation and repair for Python.

`base64.b64decode(..., validate=True)` is weaker than it looks: it only rejects characters outside the base64 alphabet. It still accepts misplaced or oversized `=` padding, and it accepts encodings whose unused trailing bits are non-zero. Both spellings decode to the same bytes as their canonical form, which is what makes them dangerous — two different inputs pass a naive "is this base64?" check while a strict parser, a signature check or a filter disagrees about the decoded value.

`b64canon` answers three questions precisely: **is this canonical**, **why not**, and **what is the canonical spelling**.

## Why this exists (a real bug, measured)

While auditing `collective/icalendar` on CPython 3.12.3, `vBinary.from_xcal()` was found to accept an invalid xCal `<binary>` value:

```pycon
>>> import base64
>>> base64.b64decode("MTIz=", validate=True)
b'123'          # accepted: no exception
```

`"MTIz="` is five characters — four data characters plus a `=` that cannot belong to a quantum — so it is not valid `xsd:base64Binary` (RFC 6321 §3.6.1 → RFC 4648). The project's own test already classifies it as invalid and asserts `XCalParsingError`, yet the parser silently returned `b'123'`. A 11-line fix (re-encode after decoding and compare) made the suite green: **15639 passed, 766 skipped, 591 xfailed, 0 failed**.

`b64canon` packages that check so the same gap can be found before it ships.

## Install

```bash
python -m pip install .
# development
python -m pip install -e ".[test]"
```

## Use as a library

```python
from b64canon import diagnose, is_canonical, validate, normalize, NonCanonicalBase64

is_canonical("MTIz")       # True
is_canonical("MTIz=")      # False
diagnose("MTIz=")          # Diagnostic(reason='bad_length', index=None, detail='length 5 is not a multiple of 4')
str(diagnose("MTIz="))     # 'bad_length: length 5 is not a multiple of 4'

validate("MTIz")           # b'123'
validate("MTIz=")          # raises NonCanonicalBase64(reason='bad_length')

normalize("MTIz=")         # 'MTIz'   (repairs the padding)
normalize("YR==")          # 'YQ=='   (repairs non-zero trailing bits)
```

`NonCanonicalBase64` subclasses `ValueError` and exposes `.reason` and `.index`.

## Reason codes

| `reason` | meaning |
| --- | --- |
| `ok` | canonical RFC 4648 base64 |
| `non_alphabet` | a character outside `A-Za-z0-9+/` and `=` |
| `padding_in_middle` | `=` appears before the end of the input |
| `too_much_padding` | more than two `=` characters |
| `bad_length` | length is not a multiple of 4 (e.g. `"MTIz="` is 5 characters) |
| `non_zero_trailing_bits` | unused trailing bits are not zero, so the spelling is not unique |

Reasons are checked in that order, so each input gets the most specific explanation.

## Command line

```bash
$ printf 'MTIz' | python -m b64canon
ok: canonical base64

$ printf 'MTIz=' | python -m b64canon; echo "exit=$?"
bad_length at index None: length 5 is not a multiple of 4
exit=1

$ printf 'MTIz=' | python -m b64canon --json
{"ok": false, "reason": "bad_length", "index": null, "detail": "length 5 is not a multiple of 4", "message": "length is not a multiple of 4"}

$ printf 'MTIz=' | python -m b64canon --normalize
MTIz

$ python -m b64canon file.b64
```

Exit codes: **0** canonical, **1** not canonical, **2** usage or I/O error. With no file argument (`-` or omitted) the input is read from standard input.

## Tests

```bash
python -m pytest tests -q
```

**35 passed** on CPython 3.12.3. The suite covers 22 hand-written valid/invalid cases across every reason code, a 200-sample random round-trip property test (with a uniqueness assertion so it is not 200 copies of one input), the repair path, and the CLI exit codes / JSON / normalize output as real subprocesses.

## Design choices

- **Standard alphabet only.** URL-safe base64 (`-` and `_`) is reported as `non_alphabet`; callers who want it should translate first. This is deliberate: a validator that silently accepts two alphabets cannot tell you which one a document used.
- **Whitespace is not ignored.** RFC 4648 allows implementations to ignore it, but then the canonical form is ambiguous. `b64canon` reports it as `non_alphabet`. Strip explicitly at your own boundary.
- **`normalize()` repairs, `validate()` never does.** Validation stays a pure predicate; repair is a separate, explicit call.
- **No dependencies**, standard library only.

## License

MIT — see `LICENSE`.
