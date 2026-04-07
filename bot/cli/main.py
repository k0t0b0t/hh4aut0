from __future__ import annotations

import argparse
import asyncio
import json

from bot.browser.session import BrowserSession
from bot.config.loader import load_all_configs
from bot.config.schema import ensure_dirs
from bot.db.migrations import init_db
from bot.db.repo_vacancies import VacancyRepo
from bot.llm.client import LLMClient
from bot.scenarios.dump_form import dump_form
from bot.scenarios.run_db import run_db
from bot.scenarios.run_one import run_one
from bot.scenarios.run_search import run_search
from bot.utils.time import run_id


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bot")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("init-db")

    ps = sub.add_parser("status")
    ps.add_argument("--limit", type=int, default=20)

    pl = sub.add_parser("list")
    pl.add_argument("--limit", type=int, default=20)

    prs = sub.add_parser("run-search")
    prs.add_argument("--limit", type=int, default=20)
    prs.add_argument("--urls", nargs="+", required=True)
    prs.add_argument("--dry-run", action="store_true")
    prs.add_argument("--debug-submit", action="store_true")
    prs.add_argument("--llm-only", action="store_true")
    prs.add_argument("--force-debug", action="store_true")
    prs.add_argument("--max-pages", type=int, default=None)

    prd = sub.add_parser("run-db")
    prd.add_argument("--mode", choices=["new", "retry-errors", "not-applied", "statuses"], required=True)
    prd.add_argument("--statuses", default="")
    prd.add_argument("--limit", type=int, default=20)
    prd.add_argument("--dry-run", action="store_true")
    prd.add_argument("--debug-submit", action="store_true")
    prd.add_argument("--llm-only", action="store_true")
    prd.add_argument("--force-debug", action="store_true")

    pro = sub.add_parser("run-one")
    pro.add_argument("--url", required=True)
    pro.add_argument("--dry-run", action="store_true")
    pro.add_argument("--debug-submit", action="store_true")
    pro.add_argument("--llm-only", action="store_true")
    pro.add_argument("--force-debug", action="store_true")

    pdf = sub.add_parser("dump-form")
    pdf.add_argument("--url", required=True)

    prd2 = sub.add_parser("run-dialogs")
    prd2.add_argument("chat_id", nargs="?", default="")
    prd2.add_argument("--chat-id", dest="chat_id_flag", default="")
    prd2.add_argument("--chat-url", dest="chat_url", default="")
    prd2.add_argument("--mode", default="all")
    prd2.add_argument("--limit", type=int, default=20)
    prd2.add_argument("--dry-run", action="store_true")
    prd2.add_argument("--debug-submit", action="store_true")
    prd2.add_argument("--auto", action="store_true")
    prd2.add_argument("--loops", type=int, default=1)
    prd2.add_argument("--interval", type=float, default=0.0)
    prd2.add_argument("--refresh", action="store_true")
    prd2.add_argument("--date-from", dest="date_from", default="")
    prd2.add_argument("--date-to", dest="date_to", default="")
    prd2.add_argument("--order", choices=["newest", "oldest"], default="newest")

    return p


async def _run_async(args, cfg, repo, llm_client):
    rid = run_id()
    async with BrowserSession(cfg["browser"]["cdp_url"], cfg["browser"]["goto_timeout_ms"]) as session:
        page = session.page
        assert page is not None

        if args.cmd == "run-search":
            return await run_search(
                page,
                repo,
                cfg,
                cfg.get("prompts", {}),
                llm_client,
                run_id=rid,
                urls=args.urls,
                limit=args.limit,
                dry_run=args.dry_run,
                debug_submit=args.debug_submit,
                llm_only=args.llm_only,
                force_debug=args.force_debug,
                max_pages=args.max_pages or cfg["search"]["max_pages_per_url"],
            )

        if args.cmd == "run-db":
            statuses = [x.strip() for x in args.statuses.split(",") if x.strip()]
            return await run_db(
                page,
                repo,
                cfg,
                cfg.get("prompts", {}),
                llm_client,
                run_id=rid,
                mode=args.mode,
                statuses=statuses,
                limit=args.limit,
                dry_run=args.dry_run,
                debug_submit=args.debug_submit,
                llm_only=args.llm_only,
                force_debug=args.force_debug,
            )

        if args.cmd == "run-one":
            return await run_one(
                page,
                repo,
                cfg,
                cfg.get("prompts", {}),
                llm_client,
                run_id=rid,
                url=args.url,
                dry_run=args.dry_run,
                debug_submit=args.debug_submit,
                llm_only=args.llm_only,
                force_debug=args.force_debug,
            )

        if args.cmd == "dump-form":
            return await dump_form(page, cfg, url=args.url, run_id=rid)

        if args.cmd == "run-dialogs":
            from bot.dialogs.scenario_run_dialogs import RunDialogsConfig, run_dialogs

            cfg_dialogs = RunDialogsConfig(
                mode=args.mode,
                limit=args.limit,
                dry_run=args.dry_run,
                debug_submit=args.debug_submit,
                auto=args.auto,
                chat_id=(args.chat_id_flag or args.chat_id or "").strip(),
                chat_url=(args.chat_url or "").strip(),
                loops=max(1, int(args.loops)),
                interval=max(0.0, float(args.interval)),
                refresh=bool(getattr(args, "refresh", False)),
                date_from=(getattr(args, "date_from", "") or "").strip(),
                date_to=(getattr(args, "date_to", "") or "").strip(),
                order=(getattr(args, "order", "newest") or "newest").strip(),
            )

            return await run_dialogs(page, cfg_dialogs, cfg)

        raise ValueError(args.cmd)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    cfg = load_all_configs()
    ensure_dirs(cfg)
    repo = VacancyRepo(cfg["storage"]["db_path"])
    llm_client = LLMClient(cfg["llm"])

    if args.cmd == "init-db":
        init_db(cfg["storage"]["db_path"])
        print("DB initialized")
        return

    if args.cmd == "status":
        print(f"Vacancies: {repo.count_all()}")
        for status, cnt in repo.count_by_status():
            print(f"  {status}: {cnt}")
        return

    if args.cmd == "list":
        for row in repo.list_recent(args.limit):
            print(json.dumps(row, ensure_ascii=False))
        return

    if not args.cmd:
        parser.print_help()
        return

    init_db(cfg["storage"]["db_path"])
    result = asyncio.run(_run_async(args, cfg, repo, llm_client))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
