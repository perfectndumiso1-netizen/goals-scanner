"""Telegram delivery for the tennis scanner (own copy of the two generic helpers so that the tennis job
never imports the football scanner). Every message starts with the 🎾 TENNIS SCANNER tag."""
from __future__ import annotations

import logging
import os
from pathlib import Path

import requests

log = logging.getLogger("tennis.notify")
TAG = "🎾 TENNIS SCANNER"


def _creds() -> tuple[str | None, str | None]:
    return os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")


def send_text(text: str) -> bool:
    token, chat = _creds()
    if not token or not chat:
        log.info("Telegram not configured – tennis message not sent")
        return False
    if not text.startswith(TAG):
        text = f"{TAG}\n{text}"
    ok = True
    chunk, chunks = "", []
    for line in text.split("\n"):
        if len(chunk) + len(line) + 1 > 3800:
            chunks.append(chunk)
            chunk = ""
        chunk += line + "\n"
    chunks.append(chunk)
    for c in chunks:
        try:
            r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id": chat, "text": c, "disable_web_page_preview": True}, timeout=30)
            ok = ok and r.ok
        except Exception as exc:                       # noqa: BLE001
            log.warning("Telegram send failed: %s", exc)
            ok = False
    return ok


def send_document(path: Path, caption: str) -> bool:
    token, chat = _creds()
    if not token or not chat or not path.exists():
        return False
    if not caption.startswith(TAG):
        caption = f"{TAG} · {caption}"
    try:
        with path.open("rb") as fh:
            r = requests.post(f"https://api.telegram.org/bot{token}/sendDocument", data={"chat_id": chat, "caption": caption[:1000]},
                              files={"document": (path.name, fh)}, timeout=120)
        return r.ok
    except Exception as exc:                           # noqa: BLE001
        log.warning("Telegram document failed: %s", exc)
        return False
