from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Tuple
import re


MSG_SELECTOR = "[data-qa^='chatik-chat-message-'][data-qa$='-text']"
DEBUG_DIR = Path("data/logs/dialogs_debug")
SHORT_ME_REPLIES = {"да", "нет", "+", "-", "ок", "ага", "неа"}


async def open_chat(page, url: str):
    if url.startswith("/"):
        url = "https://hh.ru" + url

    await page.goto(url, wait_until="domcontentloaded")
    try:
        await page.locator("#chatik_messages_scroller").first.wait_for(state="visible", timeout=2500)
    except Exception:
        pass
    await page.wait_for_timeout(350)


def normalize_text(text: str) -> str:
    text = " ".join((text or "").split()).strip()
    text = re.sub(r"\b\d{1,2}:\d{2}\b$", "", text).strip()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_garbage(text: str, author: str = "") -> bool:
    t = normalize_text(text).lower()
    if not t:
        return True

    # короткие ответы кандидата нельзя выкидывать,
    # иначе ломается last_message_is_mine_auto
    if author == "me" and t in SHORT_ME_REPLIES:
        return False

    if t in {"вчера", "сегодня", "...", "yes", "no"}:
        return True
    if "присоединился к чату" in t:
        return True
    if "добавить сопроводительное" in t:
        return True
    if "отклик на вакансию" in t:
        return True
    if "без сопроводительного письма" in t:
        return True

    if len(t) < 3 and author != "me":
        return True

    return False


async def extract_node_info(el) -> dict:
    try:
        data = await el.evaluate(
            """(node) => {
                function norm(s) {
                    return (s || "").replace(/\\s+/g, " ").trim();
                }

                const rect = node.getBoundingClientRect();
                const cls = node.getAttribute("class") || "";
                const qa = node.getAttribute("data-qa") || "";

                const bubble = node.closest("[data-qa='chat-bubble-wrapper']") || node.closest(".message--ObAiH0ml6LsDWxjP");
                const bubbleHtml = bubble ? (bubble.innerHTML || "") : "";

                return {
                    class: cls,
                    data_qa: qa,
                    raw_text: norm(node.innerText || node.textContent || ""),
                    clean_text: norm(node.innerText || node.textContent || ""),
                    html_preview: (node.innerHTML || "").slice(0, 1200),
                    bubble_html_preview: (bubbleHtml || "").slice(0, 2500),
                    x: rect.x,
                    y: rect.y,
                    width: rect.width,
                    height: rect.height,
                };
            }"""
        )
        return data or {}
    except Exception:
        return {}


def guess_author(info: dict) -> str:
    cls = (info.get("class") or "").lower()
    html = (info.get("bubble_html_preview") or "").lower()
    text = (info.get("clean_text") or "").lower()

    if "participant-action" in cls or "присоединился к чату" in text:
        return "system"

    if "chat-bubble_bot" in html:
        return "employer"

    if "chat-bubble_outgoing" in html or "message_my" in html or "with-right-tail" in html:
        return "me"

    return "employer"


async def collect_messages_and_debug(page, chat_id: str = "", limit: int = 20, save_debug: bool = False) -> Tuple[List[Dict], str]:
    items = page.locator(MSG_SELECTOR)
    count = await items.count()

    raw = []
    debug_dump = []
    start = max(0, count - limit)

    for i in range(start, count):
        el = items.nth(i)
        info = await extract_node_info(el)
        if not info:
            continue

        text = normalize_text(info.get("clean_text") or "")
        author = guess_author(info)

        info["author_guess"] = author
        info["is_garbage"] = is_garbage(text, author=author)
        info["dom_index"] = i

        debug_dump.append(info)

        if info["is_garbage"]:
            continue

        raw.append({
            "text": text,
            "author": author,
            "_debug": info,
        })

    seen = set()
    cleaned = []

    for m in raw:
        key = (m["author"], m["text"])
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(m)

    debug_path = ""
    if save_debug and chat_id:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        path = DEBUG_DIR / f"{chat_id}.json"
        path.write_text(json.dumps(debug_dump, ensure_ascii=False, indent=2), encoding="utf-8")
        debug_path = str(path)

    return cleaned, debug_path


async def collect_messages(page, limit: int = 20) -> List[Dict]:
    messages, _ = await collect_messages_and_debug(page, limit=limit, save_debug=False)
    return messages


async def dump_debug_messages(page, chat_id: str, limit: int = 30) -> str:
    _, debug_path = await collect_messages_and_debug(page, chat_id=chat_id, limit=limit, save_debug=True)
    return debug_path


async def detect_reply_available(page) -> bool:
    try:
        textarea = page.locator("[data-qa='chatik-new-message-text']")
        button = page.locator("[data-qa='chatik-do-send-message']")
        return (await textarea.count() > 0) and (await button.count() > 0)
    except Exception:
        return False
