from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path

from bot.dialogs.chat_parser import (
    collect_messages_and_debug,
    detect_reply_available,
    dump_debug_messages,
    open_chat,
)
from bot.dialogs.list_parser import collect_dialogs
from bot.dialogs.llm_decider import DialogLLMDecider
from bot.dialogs.reply_sender import ask_send_decision, click_send, fill_reply_text
from bot.dialogs.store_writer import ask_store_decision, write_case_file


@dataclass
class RunDialogsConfig:
    mode: str = "all"
    limit: int = 20
    dry_run: bool = False
    debug_submit: bool = False
    auto: bool = False
    chat_id: str = ""
    chat_url: str = ""
    loops: int = 1
    interval: float = 0.0
    refresh: bool = False
    date_from: str = ""
    date_to: str = ""
    order: str = "newest"


def shorten(text: str, limit: int = 220) -> str:
    text = (text or "").replace("\n", " ").strip()
    if len(text) > limit:
        return text[:limit] + "..."
    return text


def _dialogs_log_dir(app_cfg: dict) -> Path:
    base = Path(app_cfg["storage"]["logs_dir"])
    path = base / "dialogs_llm"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _save_llm_debug(app_cfg: dict, chat_id: str, payload: dict) -> str:
    path = _dialogs_log_dir(app_cfg) / f"{chat_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _normalize_message_key(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"\b\d{1,2}:\d{2}\b$", "", text).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _last_me_index(messages) -> int:
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("author") == "me":
            return i
    return -1


def _collect_pending_employer_indexes(messages) -> list[int]:
    last_me_idx = _last_me_index(messages)

    if last_me_idx >= 0:
        candidates = [
            (i, m) for i, m in enumerate(messages)
            if i > last_me_idx and m.get("author") == "employer"
        ]
    else:
        candidates = [
            (i, m) for i, m in enumerate(messages)
            if m.get("author") == "employer"
        ]

    seen = set()
    out = []

    for i, m in candidates:
        key = _normalize_message_key(m.get("text") or "")
        if not key:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(i)

    return out


def _post_normalize_decision(decision, llm_context: dict):
    text = "\n".join((m.get("text") or "") for m in llm_context.get("messages", [])).lower()

    robot_signals = [
        "робот-рекрутер",
        "ответьте на несколько вопросов",
        "это займет всего пару минут",
        "начнем?",
        "начнём?",
        "do you have at least",
        "question",
        "опрос",
        "анкета",
    ]

    if any(s in text for s in robot_signals):
        if decision.status == "interview_invite_llm":
            decision.status = "test_or_survey_llm"
        if decision.store_bucket == "interview":
            decision.store_bucket = "survey"

    return decision


def _build_direct_dialogs(cfg: RunDialogsConfig) -> list[dict]:
    if cfg.chat_url:
        chat_url = cfg.chat_url
        chat_id = cfg.chat_id.strip()
        if not chat_id:
            m = re.search(r"/chat/(\d+)", chat_url)
            if m:
                chat_id = m.group(1)
        return [{
            "chat_id": chat_id or "direct",
            "chat_url": chat_url,
        }]

    if cfg.chat_id:
        return [{
            "chat_id": cfg.chat_id,
            "chat_url": f"/chat/{cfg.chat_id}?hhtmFrom=app",
        }]

    return []


def _empty_report() -> dict:
    return {
        "loops_completed": 0,
        "dialogs_seen": 0,
        "dialogs_processed": 0,
        "sent": 0,
        "stored": 0,
        "interview_cases": 0,
        "test_or_survey_cases": 0,
        "skip_no_reply_ui": 0,
        "skip_last_message_is_mine": 0,
        "skip_no_pending": 0,
        "skip_empty_messages": 0,
        "skip_llm_disabled": 0,
        "skip_llm_failed": 0,
    }


def _print_report(report: dict) -> None:
    print("=" * 60)
    print("[dialogs] summary")
    print(f"loops_completed:            {report['loops_completed']}")
    print(f"dialogs_seen:               {report['dialogs_seen']}")
    print(f"dialogs_processed:          {report['dialogs_processed']}")
    print(f"sent:                       {report['sent']}")
    print(f"stored:                     {report['stored']}")
    print(f"interview_cases:            {report['interview_cases']}")
    print(f"test_or_survey_cases:       {report['test_or_survey_cases']}")
    print(f"skip_no_reply_ui:           {report['skip_no_reply_ui']}")
    print(f"skip_last_message_is_mine:  {report['skip_last_message_is_mine']}")
    print(f"skip_no_pending:            {report['skip_no_pending']}")
    print(f"skip_empty_messages:        {report['skip_empty_messages']}")
    print(f"skip_llm_disabled:          {report['skip_llm_disabled']}")
    print(f"skip_llm_failed:            {report['skip_llm_failed']}")
    print("=" * 60)


async def _execute_dialog_decision(page, cfg: RunDialogsConfig, chat_meta: dict, llm_context: dict, decision):
    decision_dict = decision.as_dict()

    print("[decision]")
    print(json.dumps(decision_dict, ensure_ascii=False, indent=2))

    should_send = False
    should_store = False
    reply_prefilled = False
    prefill_reason = ""

    store_allowed_statuses = {"interview_invite_llm", "test_or_survey_llm"}
    store_requested_by_decision = decision.decision in {"store_only", "reply_and_store"}
    store_allowed = (
        store_requested_by_decision
        and decision.store_bucket != "none"
        and decision.status in store_allowed_statuses
    )

    if cfg.dry_run:
        print("dry-run: no send, no store")
        return {
            "send": False,
            "store": False,
            "send_result": None,
            "store_path": "",
        }

    if cfg.debug_submit:
        if decision.decision in {"reply", "reply_and_store"}:
            reply_prefilled = await fill_reply_text(page, decision.reply_text)
            prefill_reason = "ok" if reply_prefilled else "fill_reply_failed_debug_prefill"
            print(f"[prefill] ok={reply_prefilled} reason={prefill_reason}")

            if reply_prefilled:
                send_choice = ask_send_decision()
                should_send = send_choice in {"yes", "y"}
            else:
                should_send = False

        if store_allowed:
            store_choice = ask_store_decision(decision.store_bucket)
            should_store = store_choice in {"yes", "y"}

    elif cfg.auto:
        should_send = decision.decision in {"reply", "reply_and_store"}
        should_store = store_allowed

    send_result = None
    if should_send:
        if reply_prefilled:
            ok_send, reason = await click_send(page)
            send_result = {"ok": ok_send, "reason": reason}
            print(f"[send] ok={ok_send} reason={reason}")
        else:
            ok_fill = await fill_reply_text(page, decision.reply_text)
            if not ok_fill:
                send_result = {"ok": False, "reason": "fill_reply_failed"}
            else:
                ok_send, reason = await click_send(page)
                send_result = {"ok": ok_send, "reason": reason}
                print(f"[send] ok={ok_send} reason={reason}")
    elif cfg.debug_submit and decision.decision in {"reply", "reply_and_store"} and not reply_prefilled:
        send_result = {"ok": False, "reason": prefill_reason or "fill_reply_failed_debug_prefill"}

    store_path = ""
    if should_store:
        store_path = write_case_file(chat_meta, llm_context, decision_dict)
        print(f"[store] path={store_path}")

    return {
        "send": should_send,
        "store": should_store,
        "send_result": send_result,
        "store_path": store_path,
    }


async def _collect_target_dialogs(page, cfg: RunDialogsConfig) -> tuple[list[dict], bool]:
    direct_dialogs = _build_direct_dialogs(cfg)
    if direct_dialogs:
        return direct_dialogs, True

    dialogs = await collect_dialogs(page, cfg.limit)
    if cfg.chat_id:
        dialogs = [d for d in dialogs if str(d.get("chat_id", "")).strip() == cfg.chat_id]
        print(f"[dialogs] filter chat_id={cfg.chat_id}")
    return dialogs, False


async def _run_one_loop(page, cfg: RunDialogsConfig, app_cfg: dict, report: dict, loop_idx: int):
    dialogs, direct_open = await _collect_target_dialogs(page, cfg)

    if direct_open:
        print("[dialogs] direct_open=yes")

    decider = DialogLLMDecider(
        app_cfg.get("llm", {}),
        app_cfg.get("prompts", {}),
        app_cfg,
    )

    print(f"[dialogs] loop={loop_idx + 1}/{cfg.loops}")
    print(f"[dialogs] found: {len(dialogs)}")
    print(f"[dialogs] llm_enabled={decider.enabled()}")

    report["dialogs_seen"] += len(dialogs)

    for d in dialogs:
        print("-" * 60)
        print(f"chat_id={d['chat_id']}")

        await open_chat(page, d["chat_url"])

        reply_available = await detect_reply_available(page)
        save_debug = bool(cfg.debug_submit or cfg.chat_id or cfg.chat_url)

        if not reply_available:
            debug_path = ""
            if save_debug:
                debug_path = await dump_debug_messages(page, d["chat_id"])
            report["skip_no_reply_ui"] += 1
            print("skip: no_reply_ui_auto")
            if debug_path:
                print(f"debug_json={debug_path}")
            continue

        messages, debug_path = await collect_messages_and_debug(
            page,
            chat_id=d["chat_id"],
            limit=20,
            save_debug=save_debug,
        )

        print(f"messages={len(messages)} reply_available={reply_available}")
        if debug_path:
            print(f"debug_json={debug_path}")

        if not messages:
            report["skip_empty_messages"] += 1
            print("skip: empty_messages")
            continue

        print("[debug] normalized messages:")
        for idx, m in enumerate(messages, 1):
            print(f"  {idx:02d}. author={m.get('author')} text={shorten(m.get('text') or '')}")

        last = messages[-1]
        dbg = last.get("_debug") or {}
        print(f"[debug] last_message_author={last.get('author')}")
        print(f"[debug] last_message_x={dbg.get('x')} width={dbg.get('width')}")

        if last.get("author") == "me":
            report["skip_last_message_is_mine"] += 1
            print("skip: last_message_is_mine")
            continue

        last_me_idx = _last_me_index(messages)
        print(f"[debug] last_me_index={last_me_idx}")

        pending_indexes = _collect_pending_employer_indexes(messages)
        if not pending_indexes:
            report["skip_no_pending"] += 1
            print("skip: no_pending_employer_messages")
            continue

        last_employer_message_index = pending_indexes[-1]

        print(f"[debug] pending_employer_indexes={pending_indexes}")
        print(f"[debug] last_employer_message_index={last_employer_message_index}")
        print("[debug] pending_employer_messages:")
        for i in pending_indexes:
            print(f"  idx={i} text={shorten(messages[i].get('text') or '', 500)}")

        llm_context = {
            "chat_id": d["chat_id"],
            "chat_url": d["chat_url"],
            "vacancy_title": d.get("vacancy_title", ""),
            "company": d.get("company", ""),
            "list_status_raw": d.get("list_status_raw", ""),
            "messages": [
                {
                    "author": m.get("author"),
                    "text": m.get("text"),
                }
                for m in messages
            ],
            "last_employer_message_index": last_employer_message_index,
            "pending_employer_indexes": pending_indexes,
        }

        print("[debug] llm_context_ready=yes")
        print(f"[debug] llm_messages_count={len(llm_context['messages'])}")
        print(f"[debug] llm_last_employer_preview={shorten(messages[last_employer_message_index].get('text') or '', 300)}")

        if not decider.enabled():
            report["skip_llm_disabled"] += 1
            print("skip: llm_disabled")
            continue

        try:
            decision, llm_debug = await decider.decide(llm_context)
            decision = _post_normalize_decision(decision, llm_context)

            llm_debug_path = _save_llm_debug(app_cfg, d["chat_id"], {
                "chat_meta": d,
                "llm_context": llm_context,
                "llm_debug": llm_debug,
                "decision": decision.as_dict(),
            })

            print("[llm] decision:")
            print(json.dumps(decision.as_dict(), ensure_ascii=False, indent=2))
            print(f"[llm] debug_json={llm_debug_path}")

            exec_result = await _execute_dialog_decision(
                page=page,
                cfg=cfg,
                chat_meta=d,
                llm_context=llm_context,
                decision=decision,
            )

            print("[execution]")
            print(json.dumps(exec_result, ensure_ascii=False, indent=2))

            report["dialogs_processed"] += 1

            send_result = exec_result.get("send_result") or {}
            if send_result.get("ok"):
                report["sent"] += 1

            if exec_result.get("store"):
                report["stored"] += 1
                if decision.store_bucket == "interview":
                    report["interview_cases"] += 1
                elif decision.store_bucket in {"survey", "test_task"}:
                    report["test_or_survey_cases"] += 1

        except Exception as exc:
            report["skip_llm_failed"] += 1
            print(f"skip: llm_failed error={exc}")


async def run_dialogs(page, cfg: RunDialogsConfig, app_cfg: dict):
    print("[dialogs] collecting list...")

    report = _empty_report()

    for loop_idx in range(max(1, cfg.loops)):
        await _run_one_loop(page, cfg, app_cfg, report, loop_idx)
        report["loops_completed"] += 1

        if loop_idx < max(1, cfg.loops) - 1 and cfg.interval > 0:
            print(f"[dialogs] sleep_between_loops_sec={cfg.interval}")
            await asyncio.sleep(cfg.interval)

    _print_report(report)
    return {"ok": True, "report": report}
