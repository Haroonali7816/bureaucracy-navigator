"""
Hand-written, minimal RFC 5545 (iCalendar) generation.

We dropped the `ics` library here on purpose: it pulls in `tatsu` for a full
grammar parser, and `ics==0.7.2`'s pinned grammar API is incompatible with
any `tatsu` release that still runs on Python 3.10+ (tatsu 5.x rewrote
ParserConfig; tatsu 4.x still imports the collections.Mapping alias Python
removed in 3.10). Rather than fight that dependency chain, we only ever
need a handful of RFC 5545 fields for this project -- one VEVENT per
deadline, all-day, no recurrence, no attendees -- so we write that subset
directly instead of carrying a broken/fragile dependency for it.
"""

from datetime import datetime, timezone


def _escape_ics_text(text: str) -> str:
    """RFC 5545 TEXT value escaping: backslash, semicolon, comma, and
    newline are the only characters that need escaping for our fields."""
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _fold_ics_line(line: str) -> str:
    """RFC 5545 line folding: a content line longer than 75 octets must be
    split across multiple physical lines, each continuation line starting
    with a single leading space. We fold on UTF-8 byte boundaries without
    splitting a multi-byte character in half."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line

    chunks = []
    start = 0
    limit = 75
    while start < len(encoded):
        end = min(start + limit, len(encoded))
        # never split a multi-byte utf-8 sequence in half -- continuation
        # bytes have the high bits `10`, so back off until we're not
        # pointing into the middle of one
        while end < len(encoded) and (encoded[end] & 0xC0) == 0x80:
            end -= 1
        chunks.append(encoded[start:end].decode("utf-8"))
        start = end
        limit = 74  # continuation lines lose one column to the leading space

    return "\r\n ".join(chunks)


def build_ics(
    letter_id: int,
    authority: str,
    consequences: str | None,
    deadlines: list[dict],
) -> str:
    """Build a single .ics document containing one all-day VEVENT per
    entry in `deadlines` (each `{"date": "YYYY-MM-DD", "description": str}`).

    Per RFC 5545 3.6.1, a VEVENT with a DATE-valued DTSTART and no DTEND or
    DURATION is defined to span exactly one day -- so no DTEND is needed
    for our all-day deadlines.
    """
    now_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//bureaucracy-navigator//EN"]

    for i, entry in enumerate(deadlines):
        summary = _escape_ics_text(f"{authority}: {entry['description']}")
        date_value = entry["date"].replace("-", "")  # "2026-09-15" -> "20260915"

        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:letter-{letter_id}-deadline-{i}@bureaucracy-navigator")
        lines.append(f"DTSTAMP:{now_stamp}")
        lines.append(f"DTSTART;VALUE=DATE:{date_value}")
        lines.append(f"SUMMARY:{summary}")
        if consequences:
            lines.append(f"DESCRIPTION:{_escape_ics_text(consequences)}")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")

    return "\r\n".join(_fold_ics_line(line) for line in lines) + "\r\n"
