from __future__ import annotations

import re
from pathlib import Path

from bot.apply.action_executor import execute_action, find_target, fill_locator
from bot.apply.cover_prefill import build_cover_text, find_cover_fields, try_expand_cover_section
from bot.apply.cover_safe import is_safe_single_cover_screen
from bot.apply.detectors import (
    click_apply_button,
    collect_form_screen_dump,
    detect_already_applied_on_page,
    wait_for_form,
)
from bot.apply.salary_prefill import build_salary_text, find_salary_fields
from bot.apply.submit import finalize_submit
from bot.apply.preapply_warning import handle_pre_apply_warning
from bot.apply.flow_guard import is_in_apply_flow
from bot.browser.elements import build_screen_dump
from bot.browser.screenshots import capture_html, capture_screenshot
from bot.core.models import ApplyAttemptContext, ApplyResult, Vacancy
from bot.loggingx.run_logger import save_json
from bot.utils.serialize import to_dict_safe
from bot.utils.template_render import render_text_template


TG_FIELD_RE = re.compile(r"(telegram|телеграм|телеграмм|tg\b|t\.me)", re.I)

SUBMIT_LIKE_ACTION_RE = re.compile(r"(отправить|submit|send|откликнуться|apply)", re.I)


def _pick_llm_modes(ctx: ApplyAttemptContext, clicked: bool, stage_index: int) -> list[str]:
    if not clicked and stage_index == 1:
        return ["button_recovery"]

    if ctx.debug_submit:
        return ["form_analyze", "form_auto"]

    return ["form_auto"]


def _field_joined(item: dict) -> str:
    return " ".join(
        [
            item.get("label", "") or "",
            item.get("placeholder", "") or "",
            item.get("name", "") or "",
        ]
    ).strip()


def _get_telegram_value(cfg: dict) -> str:
    candidates = [
        cfg.get("candidate", {}).get("telegram"),
        cfg.get("telegram"),
        cfg.get("contacts", {}).get("telegram"),
        cfg.get("candidate", {}).get("contacts", {}).get("telegram"),
        cfg.get("dialog_profile", {}).get("telegram"),
        cfg.get("dialog_profile", {}).get("telegram_handle"),
    ]
    for value in candidates:
        if value not in (None, ""):
            return str(value)
    return ""


def _remap_check_action(screen: dict, action):
    if action.action != "check" or not action.value:
        return action

    elements = screen.get("elements", []) or []
    target_el = next((x for x in elements if x.get("field_ref") == action.target), None)
    if not target_el:
        return action

    name = (target_el.get("name") or "").strip()
    if not name:
        return action

    wanted = str(action.value).strip().lower()
    for el in elements:
        if (el.get("name") or "").strip() != name:
            continue
        if (el.get("label") or "").strip().lower() == wanted:
            action.target = el.get("field_ref", action.target)
            return action

    return action


def _is_submit_like_action(action) -> bool:
    if action.action == "submit":
        return True

    if action.action != "click":
        return False

    target = (action.target or "").strip()
    if not target:
        return False

    return bool(SUBMIT_LIKE_ACTION_RE.search(target))


async def _apply_known_prefills(page, screen: dict, cfg: dict, vacancy: Vacancy, report: dict, stage_index: int, flush_report):
    filled = []

    salary_value = build_salary_text(cfg)
    if salary_value:
        for field in find_salary_fields(screen):
            target = await find_target(page, field.get("field_ref", ""))
            if target is None:
                continue
            try:
                await fill_locator(target, salary_value)
                filled.append(
                    {
                        "kind": "salary",
                        "target": field.get("field_ref"),
                        "value": salary_value,
                    }
                )
            except Exception:
                continue

    tg_value = _get_telegram_value(cfg)
    if tg_value:
        for item in screen.get("elements", []) or []:
            if not item.get("textual"):
                continue
            if item.get("is_select") or item.get("is_radio") or item.get("is_checkbox"):
                continue

            joined = _field_joined(item)
            if not joined or not TG_FIELD_RE.search(joined):
                continue

            target = await find_target(page, item.get("field_ref", ""))
            if target is None:
                continue
            try:
                await fill_locator(target, tg_value)
                filled.append(
                    {
                        "kind": "telegram",
                        "target": item.get("field_ref"),
                        "value": tg_value,
                    }
                )
            except Exception:
                continue

    cover_value = build_cover_text(cfg, vacancy)
    if cover_value:
        for field in find_cover_fields(screen):
            target = await find_target(page, field.get("field_ref", ""))
            if target is None:
                continue
            try:
                await fill_locator(target, cover_value)
                filled.append(
                    {
                        "kind": "cover",
                        "target": field.get("field_ref"),
                        "value_preview": cover_value[:300],
                    }
                )
            except Exception:
                continue

    if filled:
        report["steps"].append(
            {
                "stage": stage_index,
                "deterministic_prefills": filled,
            }
        )
        flush_report()

    return filled


async def apply_vacancy(vacancy: Vacancy, page, ctx: ApplyAttemptContext, cfg: dict, prompts: dict, llm_client, repo) -> ApplyResult:
    storage = cfg["storage"]
    logs_dir = Path(storage["logs_dir"]) / "vacancies" / vacancy.vacancy_id
    report = {
        "vacancy_id": vacancy.vacancy_id,
        "url": vacancy.url,
        "title": vacancy.title,
        "steps": [],
        "screens": [],
        "ctx": {
            "run_id": ctx.run_id,
            "mode": ctx.mode,
            "dry_run": ctx.dry_run,
            "debug_submit": ctx.debug_submit,
            "llm_only": ctx.llm_only,
            "force_debug": ctx.force_debug,
        },
    }
    log_path = logs_dir / f"{ctx.run_id}.json"

    def flush_report() -> str:
        return save_json(log_path, report)

    repo.mark_start_attempt(vacancy.vacancy_id, ctx.run_id, status="queued")
    try:
        await page.goto(vacancy.url, wait_until="domcontentloaded", timeout=cfg["browser"]["goto_timeout_ms"])
        await page.wait_for_timeout(1800)
        report["steps"].append({"goto": "ok", "final_url": page.url})
        flush_report()
    except Exception as exc:
        report["steps"].append({"goto": "error", "error": str(exc)})
        result = ApplyResult(status="open_error", message=str(exc), log_path=flush_report())
        repo.update_status(vacancy.vacancy_id, result.status, last_error=result.message, log_path=result.log_path)
        return result

    if cfg["debug"]["save_html_snapshot"]:
        html_path = await capture_html(page, Path(storage["html_dir"]) / f"{vacancy.vacancy_id}_{ctx.run_id}.html")
        report["html_snapshot"] = html_path
    if cfg["debug"]["save_screenshot"]:
        png_path = await capture_screenshot(page, Path(storage["screenshots_dir"]) / f"{vacancy.vacancy_id}_{ctx.run_id}.png")
        report["screenshot"] = png_path
    flush_report()

    pre = await detect_already_applied_on_page(page)
    report["already_applied_precheck"] = pre
    flush_report()

    if pre.get("already_applied") and not ctx.force_debug:
        result = ApplyResult(
            status="already_applied_on_hh",
            message="already applied on page",
            submit_result_json=pre,
            log_path=flush_report(),
        )
        repo.update_status(
            vacancy.vacancy_id,
            result.status,
            submit_result_json=result.submit_result_json,
            log_path=result.log_path,
        )
        return result

    clicked = await click_apply_button(page)
    report["steps"].append({"apply_clicked": clicked, "url_after_click": page.url})
    flush_report()

    if not clicked and not llm_client.enabled():
        result = ApplyResult(status="no_apply_button", message="apply button not found", log_path=flush_report())
        repo.update_status(vacancy.vacancy_id, result.status, last_error=result.message, log_path=result.log_path)
        return result

    repo.update_status(vacancy.vacancy_id, "apply_opened")
    if clicked:
        await page.wait_for_timeout(cfg["browser"]["wait_after_click_ms"])
        try:
            warning_result = await handle_pre_apply_warning(page)
            report["steps"].append(
                {
                    "pre_apply_warning": warning_result,
                    "page_url_after_warning": page.url,
                }
            )
            flush_report()
            if warning_result.get("handled"):
                await page.wait_for_timeout(cfg["browser"]["wait_after_click_ms"])
        except Exception as exc:
            report["steps"].append(
                {
                    "pre_apply_warning": {
                        "handled": False,
                        "reason": f"warning_handler_error:{exc}",
                    }
                }
            )
            flush_report()

        try:
            flow_check = await is_in_apply_flow(page)
        except Exception as exc:
            flow_check = {"ok": False, "reason": f"flow_guard_error:{exc}", "url": page.url}

        report["steps"].append(
            {
                "post_apply_flow_check": flow_check,
            }
        )
        flush_report()

        if not flow_check.get("ok"):
            if llm_client.enabled():
                try:
                    recovery_screen = await build_screen_dump(page, 0)
                    report.setdefault("post_apply_recovery_screens", []).append(recovery_screen)
                    flush_report()

                    recovery_modes = _pick_llm_modes(ctx, clicked, 1)
                    recovery_plan = None
                    recovery_mode = None
                    recovery_exc = None

                    for mode in recovery_modes:
                        try:
                            candidate_plan, _candidate_debug = await llm_client.plan(prompts, cfg, recovery_screen, mode)
                            recovery_plan = candidate_plan
                            recovery_mode = mode
                            report.setdefault("llm_post_apply_recovery", []).append(
                                {
                                    "mode": mode,
                                    "ok": True,
                                    "actions": [to_dict_safe(a) for a in recovery_plan.actions],
                                    "submit_candidate": to_dict_safe(recovery_plan.submit_candidate),
                                    "stop_reason": recovery_plan.stop_reason,
                                }
                            )
                            flush_report()
                            break
                        except Exception as exc:
                            recovery_exc = exc
                            report.setdefault("llm_post_apply_recovery", []).append(
                                {
                                    "mode": mode,
                                    "ok": False,
                                    "error": str(exc),
                                }
                            )
                            flush_report()

                    if recovery_plan is not None:
                        recovery_results = []
                        for action in recovery_plan.actions[:3]:
                            if _is_submit_like_action(action):
                                report["steps"].append(
                                    {
                                        "post_apply_recovery_submit_like_blocked": True,
                                        "action": to_dict_safe(action),
                                    }
                                )
                                flush_report()
                                break

                            if action.action in {"fill", "select"} and action.value is not None:
                                action.value = render_text_template(action.value, cfg, vacancy)

                            step = await execute_action(page, action)
                            recovery_results.append(step)
                            report["steps"].append(
                                {
                                    "post_apply_recovery_action": to_dict_safe(action),
                                    "result": step,
                                }
                            )
                            flush_report()

                            if not step.get("ok"):
                                break

                            await page.wait_for_timeout(cfg["browser"]["wait_after_fill_ms"])

                    try:
                        second_flow_check = await is_in_apply_flow(page)
                    except Exception as exc:
                        second_flow_check = {"ok": False, "reason": f"second_flow_guard_error:{exc}", "url": page.url}

                    report["steps"].append(
                        {
                            "post_apply_second_flow_check": second_flow_check,
                        }
                    )
                    flush_report()

                    if not second_flow_check.get("ok"):
                        result = ApplyResult(
                            status="lost_after_apply",
                            message=second_flow_check.get("reason", "lost after apply"),
                            log_path=flush_report(),
                        )
                        repo.update_status(
                            vacancy.vacancy_id,
                            result.status,
                            last_error=result.message,
                            log_path=result.log_path,
                        )
                        return result

                except Exception as exc:
                    result = ApplyResult(
                        status="lost_after_apply",
                        message=f"recovery_failed:{exc}",
                        log_path=flush_report(),
                    )
                    repo.update_status(
                        vacancy.vacancy_id,
                        result.status,
                        last_error=result.message,
                        log_path=result.log_path,
                    )
                    return result
            else:
                result = ApplyResult(
                    status="lost_after_apply",
                    message=flow_check.get("reason", "lost after apply"),
                    log_path=flush_report(),
                )
                repo.update_status(
                    vacancy.vacancy_id,
                    result.status,
                    last_error=result.message,
                    log_path=result.log_path,
                )
                return result

    stage_index = 0
    try:
        while True:
            stage_index += 1
            ctx.current_screen_index = stage_index

            form_found = await wait_for_form(page, timeout_loops=4)
            report["steps"].append(
                {
                    "stage": stage_index,
                    "form_found": form_found,
                    "page_url": page.url,
                }
            )

            if form_found:
                screen = await collect_form_screen_dump(page, stage_index)
            else:
                screen = await build_screen_dump(page, stage_index)

            report["screens"].append(screen)
            flush_report()

            if form_found and not ctx.llm_only:
                try:
                    expanded = await try_expand_cover_section(page)
                except Exception:
                    expanded = False

                if expanded:
                    report["steps"].append(
                        {
                            "stage": stage_index,
                            "cover_expanded": True,
                        }
                    )
                    await page.wait_for_timeout(700)
                    screen = await collect_form_screen_dump(page, stage_index)
                    report["screens"].append(screen)
                    flush_report()

                await _apply_known_prefills(page, screen, cfg, vacancy, report, stage_index, flush_report)

            if (
                form_found
                and not ctx.llm_only
                and cfg["apply"]["allow_safe_cover_autofill"]
                and is_safe_single_cover_screen(screen)
            ):
                field = next(e for e in screen["elements"] if e.get("textual"))
                target = await find_target(page, field.get("selector_hint", ""))
                if target is not None:
                    cover = render_text_template(
                        cfg.get("cover_letters", {}).get("default", ""),
                        cfg,
                        vacancy,
                    )
                    await fill_locator(target, cover)

                    report["steps"].append(
                        {
                            "stage": stage_index,
                            "safe_cover": True,
                            "target": field.get("selector_hint", ""),
                            "cover_preview": cover[:300],
                        }
                    )
                    flush_report()

                    ok, reason = await finalize_submit(page, dry_run=ctx.dry_run, debug_submit=ctx.debug_submit)
                    report["steps"].append(
                        {
                            "stage": stage_index,
                            "safe_cover_submit": {"ok": ok, "reason": reason},
                        }
                    )
                    result = ApplyResult(
                        status="applied" if ok else "submit_failed",
                        message=reason,
                        form_json=screen,
                        fill_json={"mode": "safe_cover", "cover": cover},
                        submit_result_json={"submitted": ok, "reason": reason},
                        log_path=flush_report(),
                    )
                    repo.update_status(
                        vacancy.vacancy_id,
                        result.status,
                        form_json=result.form_json,
                        fill_json=result.fill_json,
                        submit_result_json=result.submit_result_json,
                        last_error="" if ok else reason,
                        log_path=result.log_path,
                    )
                    return result

            if not llm_client.enabled():
                result = ApplyResult(
                    status="form_detected" if form_found else "no_apply_button",
                    message="LLM disabled and safe flow unavailable",
                    form_json=screen,
                    log_path=flush_report(),
                )
                repo.update_status(
                    vacancy.vacancy_id,
                    result.status,
                    form_json=result.form_json,
                    last_error=result.message,
                    log_path=result.log_path,
                )
                return result

            repo.update_status(vacancy.vacancy_id, "llm_in_progress")

            llm_modes = _pick_llm_modes(ctx, clicked, stage_index)
            report.setdefault("llm_attempts", []).append(
                {
                    "stage": stage_index,
                    "candidate_modes": llm_modes,
                }
            )
            flush_report()

            plan = None
            last_exc = None
            used_mode = None

            for mode in llm_modes:
                try:
                    candidate_plan, _candidate_debug = await llm_client.plan(prompts, cfg, screen, mode)
                    plan = candidate_plan
                    used_mode = mode
                    report.setdefault("llm", []).append(
                        {
                            "stage": stage_index,
                            "mode": mode,
                            "ok": True,
                            "actions": [to_dict_safe(a) for a in plan.actions],
                            "submit_candidate": to_dict_safe(plan.submit_candidate),
                            "stop_reason": plan.stop_reason,
                        }
                    )
                    flush_report()
                    break
                except Exception as exc:
                    last_exc = exc
                    report.setdefault("llm", []).append(
                        {
                            "stage": stage_index,
                            "mode": mode,
                            "ok": False,
                            "error": str(exc),
                        }
                    )
                    flush_report()

            if plan is None:
                result = ApplyResult(
                    status="llm_failed",
                    message=str(last_exc) if last_exc else "llm returned no usable plan",
                    form_json=screen,
                    log_path=flush_report(),
                )
                repo.update_status(
                    vacancy.vacancy_id,
                    result.status,
                    form_json=result.form_json,
                    last_error=result.message,
                    log_path=result.log_path,
                )
                return result

            action_results = []
            submit_action_seen = False
            progressed = False

            report["steps"].append(
                {
                    "stage": stage_index,
                    "llm_mode_used": used_mode,
                    "actions_count": len(plan.actions),
                }
            )
            flush_report()

            for action in plan.actions:
                if _is_submit_like_action(action):
                    submit_action_seen = True
                    report["steps"].append(
                        {
                            "stage": stage_index,
                            "submit_action_seen": True,
                            "target": action.target,
                            "original_action": to_dict_safe(action),
                            "submit_like_action_blocked": action.action == "click",
                        }
                    )
                    flush_report()
                    break

                action = _remap_check_action(screen, action)

                if action.action in {"fill", "select"} and action.value is not None:
                    action.value = render_text_template(action.value, cfg, vacancy)

                step = await execute_action(page, action)
                action_results.append(step)

                report["steps"].append(
                    {
                        "stage": stage_index,
                        "action": to_dict_safe(action),
                        "result": step,
                    }
                )
                flush_report()

                if not step.get("ok"):
                    result = ApplyResult(
                        status="llm_failed",
                        message=step.get("error") or step.get("reason", "llm action failed"),
                        form_json=screen,
                        fill_json={"actions": action_results, "llm_mode": used_mode},
                        log_path=flush_report(),
                    )
                    repo.update_status(
                        vacancy.vacancy_id,
                        result.status,
                        form_json=result.form_json,
                        fill_json=result.fill_json,
                        last_error=result.message,
                        log_path=result.log_path,
                    )
                    return result

                if action.action in {"click", "next"} and (step.get("screen_changed") or step.get("form_opened") or step.get("submitted")):
                    progressed = True

                await page.wait_for_timeout(cfg["browser"]["wait_after_fill_ms"])

            has_submit = plan.submit_candidate is not None or submit_action_seen
            report["steps"].append(
                {
                    "stage": stage_index,
                    "has_submit": has_submit,
                    "submit_candidate": to_dict_safe(plan.submit_candidate),
                    "progressed": progressed,
                    "stop_reason": plan.stop_reason,
                }
            )
            flush_report()

            if has_submit:
                ok, reason = await finalize_submit(page, dry_run=ctx.dry_run, debug_submit=ctx.debug_submit)
                report["steps"].append(
                    {
                        "stage": stage_index,
                        "finalize_submit": {"ok": ok, "reason": reason},
                    }
                )
                flush_report()

                if not ok and reason.startswith("operator_"):
                    result = ApplyResult(
                        status="bad_response",
                        message=reason,
                        form_json=screen,
                        fill_json={"actions": action_results, "llm_mode": used_mode},
                        submit_result_json={"submitted": False, "reason": reason},
                        log_path=flush_report(),
                    )
                    repo.update_status(
                        vacancy.vacancy_id,
                        result.status,
                        form_json=result.form_json,
                        fill_json=result.fill_json,
                        submit_result_json=result.submit_result_json,
                        last_error=reason,
                        log_path=result.log_path,
                    )
                    return result

                if ok:
                    next_screen = await build_screen_dump(page, stage_index + 100)
                    report.setdefault("post_submit_screens", []).append(next_screen)
                    flush_report()

                    visible_text = next_screen.get("visible_text", "").lower()
                    if any(x in visible_text for x in ["отклик отправлен", "вы откликнулись", "спасибо"]):
                        result = ApplyResult(
                            status="applied",
                            message=reason,
                            form_json=screen,
                            fill_json={"actions": action_results, "llm_mode": used_mode},
                            submit_result_json={"submitted": True, "reason": reason},
                            log_path=flush_report(),
                        )
                        repo.update_status(
                            vacancy.vacancy_id,
                            result.status,
                            form_json=result.form_json,
                            fill_json=result.fill_json,
                            submit_result_json=result.submit_result_json,
                            log_path=result.log_path,
                        )
                        return result

                    clicked = True
                    continue

                result = ApplyResult(
                    status="submit_failed",
                    message=reason,
                    form_json=screen,
                    fill_json={"actions": action_results, "llm_mode": used_mode},
                    submit_result_json={"submitted": False, "reason": reason},
                    log_path=flush_report(),
                )
                repo.update_status(
                    vacancy.vacancy_id,
                    result.status,
                    form_json=result.form_json,
                    fill_json=result.fill_json,
                    submit_result_json=result.submit_result_json,
                    last_error=reason,
                    log_path=result.log_path,
                )
                return result

            if progressed:
                clicked = True
                continue

            result = ApplyResult(
                status="manual_skipped",
                message=plan.stop_reason or "stage complete without submit",
                form_json=screen,
                fill_json={"actions": action_results, "llm_mode": used_mode},
                log_path=flush_report(),
            )
            repo.update_status(
                vacancy.vacancy_id,
                result.status,
                form_json=result.form_json,
                fill_json=result.fill_json,
                last_error=result.message,
                log_path=result.log_path,
            )
            return result

    except KeyboardInterrupt:
        report["interrupted"] = {
            "stage_index": stage_index,
            "page_url": page.url,
        }
        flush_report()
        raise
    except Exception as exc:
        report["fatal_error"] = {
            "stage_index": stage_index,
            "page_url": page.url,
            "error": str(exc),
        }
        result = ApplyResult(
            status="apply_error",
            message=str(exc),
            log_path=flush_report(),
        )
        repo.update_status(
            vacancy.vacancy_id,
            result.status,
            last_error=result.message,
            log_path=result.log_path,
        )
        return result
