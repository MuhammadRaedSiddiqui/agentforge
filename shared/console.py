"""
Console output encoding.

Operator-facing output across this codebase uses non-ASCII glyphs — `✓`, `✗`,
`•`, `⚠`, `→` — in roughly 250 places, including the approval gate in
`cli/prompts.py`.

On Windows, Python writes to a real console through WriteConsoleW and those
glyphs render fine, but as soon as stdout is *not* a console — redirected to a
file, piped to `tee`, or captured by CI or any harness — it falls back to the
locale encoding, which is cp1252 here. Encoding `✓` to cp1252 raises
UnicodeEncodeError, so `agent-forge update ... > audit.log` crashes partway
through the approval display: exactly when an operator is keeping a record of
a mutation, and exactly at the step that guards it.

Every entry point calls this before producing output. Rewriting the 250 call
sites to ASCII would work too, but it degrades the interactive display for a
problem that only exists at the stream boundary.
"""

import sys
from typing import IO, Any


def enable_utf8_output() -> None:
    """Force stdout/stderr to UTF-8 so non-ASCII output survives redirection.

    Safe to call more than once, and a no-op on streams that cannot be
    reconfigured (already-wrapped or replaced streams, as under pytest's
    capture). Never raises: a logging concern must not take down a deployment.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (ValueError, OSError):
            # Stream is detached or does not support reconfiguration. Output
            # may still fail to encode, which is no worse than before.
            continue


def write_line(stream: IO[Any], text: str) -> None:
    """Write a line to `stream`, degrading rather than raising on encoding.

    For the rare caller that writes to a stream `enable_utf8_output` could not
    fix. Prefer plain `print` everywhere else.
    """
    try:
        stream.write(text + "\n")
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "ascii"
        stream.write(text.encode(encoding, "backslashreplace").decode(encoding) + "\n")
