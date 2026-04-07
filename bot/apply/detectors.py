from __future__ import annotations

import re
from typing import Any

from bot.apply.click_logic import find_active_form_root, find_apply_locator, find_next_locator, find_submit_locator
from bot.browser.navigation import safe_click

FORM_FIELD_SELECTOR = "textarea, input, select, [contenteditable='true']"

RELEVANT_BUTTON_RE = re.compile(
    r"(отклик|отправ|ответить|продолж|далее|submit|apply|continue|next|send)",
    re.I,
)

NOISE_TEXT_RE = re.compile(
    r"(мы используем файлы cookie|правила использования файлов cookie|понятно|headhunter|"
    r"о компании|помощь|наши вакансии|реклама на сайте|требования к по|"
    r"безопасный headhunter|headhunter api|партнерам|инвесторам|каталог компаний|"
    r"создать резюме|поиск по вакансиям|работа рядом с метро|hh pro|готовое резюме|"
    r"пользовательское соглашение|защита персональных данных|"
    r"применяются рекомендательные технологии)",
    re.I,
)

QUESTION_NOISE_RE = re.compile(
    r"(мы используем файлы cookie|правила использования файлов cookie|понятно|"
    r"писать тут\b|ответьте на вопросы\b)",
    re.I,
)


def normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def strip_question_noise(text: str) -> str:
    value = normalize_ws(text)
    if not value:
        return ""
    value = QUESTION_NOISE_RE.sub(" ", value)
    value = normalize_ws(value)
    return value


def is_noise_text(text: str) -> bool:
    value = normalize_ws(text).lower()
    if not value:
        return True
    return bool(NOISE_TEXT_RE.search(value))


async def detect_already_applied_on_page(page) -> dict[str, Any]:
    checks = [
        ("already_applied_text", page.locator("text=Вы откликнулись")),
        ("already_applied_text_2", page.locator("text=Вы уже откликались")),
        ("already_applied_text_3", page.locator("text=Отклик отправлен")),
        ("repeat_apply_text", page.locator("text=Откликнуться повторно")),
    ]

    found = []
    for name, locator in checks:
        try:
            if await locator.count() > 0:
                found.append(name)
        except Exception:
            pass

    return {
        "already_applied": len(found) > 0,
        "signals": found,
    }


async def click_apply_button(page) -> bool:
    locator = await find_apply_locator(page)
    if locator is None:
        return False
    return await safe_click(locator, timeout=5000)


async def wait_for_form(page, timeout_loops: int = 12) -> bool:
    for _ in range(timeout_loops):
        root, _ = await find_active_form_root(page)
        if root is not None:
            try:
                field_count = await root.locator(FORM_FIELD_SELECTOR).count()
                if field_count > 0:
                    return True
            except Exception:
                pass

        try:
            if await page.locator(FORM_FIELD_SELECTOR).count() > 0:
                return True
        except Exception:
            pass

        for frame in page.frames:
            try:
                if await frame.locator(FORM_FIELD_SELECTOR).count() > 0:
                    return True
            except Exception:
                pass

        await page.wait_for_timeout(1000)

    return False


async def _find_best_root(page):
    root, root_selector = await find_active_form_root(page)
    if root is not None:
        return root, root_selector

    fallback_selectors = [
        "form[id^='cover-letter-']",
        "form[action*='/applicant/vacancy_response/']",
        "form:has(textarea)",
        "form:has(input)",
        "form:has(select)",
        "body",
    ]

    best = None
    best_selector = None
    best_score = -1

    for sel in fallback_selectors:
        loc = page.locator(sel)
        try:
            count = await loc.count()
        except Exception:
            continue

        for i in range(min(count, 10)):
            el = loc.nth(i)
            try:
                if not await el.is_visible():
                    continue
                fields = el.locator(FORM_FIELD_SELECTOR)
                field_count = await fields.count()
                score = field_count
                if sel.startswith("form[id^='cover-letter-'"):
                    score += 100
                elif "applicant/vacancy_response" in sel:
                    score += 90
                elif sel == "body":
                    score -= 1000
            except Exception:
                continue

            if score > best_score:
                best = el
                best_selector = sel
                best_score = score

    return best, best_selector


async def collect_form_screen_dump(page, screen_index: int = 1) -> dict[str, Any]:
    root, root_selector = await _find_best_root(page)

    if root is None:
        try:
            page_title = await _safe_title(page)
        except Exception:
            page_title = ""
        return {
            "page_url": page.url,
            "page_title": page_title,
            "screen_index": screen_index,
            "root_selector": None,
            "elements": [],
            "visible_text": "",
        }

    js = r"""
(root, fieldSelector) => {
  function norm(s) {
    return (s || '').replace(/\s+/g, ' ').trim();
  }

  function isVisible(el) {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    const type = (el.getAttribute('type') || '').toLowerCase();

    return (
      style.display !== 'none' &&
      style.visibility !== 'hidden' &&
      rect.width > 6 &&
      rect.height > 6 &&
      type !== 'hidden'
    );
  }

  function cssPath(el) {
    if (!(el instanceof Element)) return '';
    const path = [];
    while (el && el.nodeType === Node.ELEMENT_NODE) {
      let selector = el.nodeName.toLowerCase();
      if (el.id) {
        selector += '#' + CSS.escape(el.id);
        path.unshift(selector);
        break;
      } else {
        let sib = el;
        let nth = 1;
        while ((sib = sib.previousElementSibling) != null) {
          if (sib.nodeName.toLowerCase() === selector) nth++;
        }
        selector += `:nth-of-type(${nth})`;
      }
      path.unshift(selector);
      el = el.parentElement;
    }
    return path.join(' > ');
  }

  function textOf(el) {
    return norm(el?.innerText || el?.textContent || '');
  }

  function visibleFieldCount(scope) {
    try {
      return Array.from(scope.querySelectorAll(fieldSelector)).filter(isVisible).length;
    } catch {
      return 0;
    }
  }

  function textWithoutControls(container) {
    if (!container) return '';
    const clone = container.cloneNode(true);
    for (const node of clone.querySelectorAll('textarea, input, select, option, button, a, [role="button"], script, style')) {
      node.remove();
    }
    return norm(clone.innerText || clone.textContent || '');
  }

  function questionBlockText(fieldEl) {
    let node = fieldEl.parentElement;
    let best = '';

    while (node && node !== root && node !== document.body) {
      const fieldCount = visibleFieldCount(node);
      const txt = textWithoutControls(node);

      if (fieldCount === 1 && txt && txt.length >= 8 && txt.length <= 900) {
        best = txt;
      }

      node = node.parentElement;
    }

    return best;
  }

  function textNearField(fieldEl) {
    const box = fieldEl.getBoundingClientRect();
    const nodes = Array.from(root.querySelectorAll('label, div, span, p, strong, b, legend, h1, h2, h3'))
      .filter(isVisible)
      .map(el => {
        const rect = el.getBoundingClientRect();
        return {
          el,
          text: textOf(el),
          top: rect.top,
          left: rect.left,
          width: rect.width,
          height: rect.height
        };
      })
      .filter(x => x.text && x.text.length >= 2 && x.text.length <= 800);

    const candidates = nodes
      .filter(x => {
        const dy = Math.abs(box.top - x.top);
        const dx = Math.abs(box.left - x.left);
        return dy <= 220 && dx <= 360;
      })
      .sort((a, b) => {
        const da = Math.abs(box.top - a.top) + Math.abs(box.left - a.left);
        const db = Math.abs(box.top - b.top) + Math.abs(box.left - b.left);
        return da - db;
      })
      .slice(0, 8)
      .map(x => x.text);

    const uniq = [];
    const seen = new Set();
    for (const item of candidates) {
      const t = norm(item);
      if (!t || seen.has(t)) continue;
      seen.add(t);
      uniq.push(t);
    }
    return uniq;
  }

  function findLabel(fieldEl) {
    const aria = norm(fieldEl.getAttribute('aria-label') || '');
    if (aria) return aria;

    const placeholder = norm(fieldEl.getAttribute('placeholder') || '');

    const id = fieldEl.getAttribute('id') || '';
    if (id) {
      const label = root.querySelector(`label[for="${id}"]`) || document.querySelector(`label[for="${id}"]`);
      const txt = textOf(label);
      if (txt) return txt;
    }

    const parentLabel = fieldEl.closest('label');
    const parentLabelText = textOf(parentLabel);
    if (parentLabelText) return parentLabelText;

    const blockText = questionBlockText(fieldEl);
    if (blockText) return blockText;

    const nearby = textNearField(fieldEl);
    if (nearby.length) return nearby.join(' | ');

    return placeholder;
  }

  function extractOptions(el) {
    const tag = (el.tagName || '').toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();

    if (tag === 'select') {
      return Array.from(el.options || [])
        .map(opt => norm(opt.textContent || opt.label || opt.value || ''))
        .filter(Boolean);
    }

    if (tag === 'input' && (type === 'radio' || type === 'checkbox')) {
      const name = el.getAttribute('name') || '';
      let group = [];
      if (name) {
        group = Array.from(root.querySelectorAll(`input[type="${type}"][name="${CSS.escape(name)}"]`)).filter(isVisible);
      }
      if (!group.length) group = [el];

      return group.map(node => {
        const id = node.getAttribute('id') || '';
        let labelText = '';
        if (id) {
          const label = root.querySelector(`label[for="${id}"]`) || document.querySelector(`label[for="${id}"]`);
          labelText = textOf(label);
        }
        if (!labelText) labelText = textOf(node.closest('label'));
        if (!labelText) labelText = norm(node.getAttribute('value') || '');
        return labelText;
      }).filter(Boolean);
    }

    return [];
  }

  const fieldNodes = Array.from(root.querySelectorAll(fieldSelector)).filter(isVisible);
  const fields = fieldNodes.map((el, idx) => {
    const tag = (el.tagName || '').toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    const rect = el.getBoundingClientRect();

    return {
      kind: tag === 'textarea' ? 'textarea' : 'field',
      field_id: idx,
      visible_index: idx,
      field_ref: `F${idx + 1}`,
      tag,
      type: tag === 'textarea' && !type ? 'textarea' : type,
      selector_hint: cssPath(el),
      name: norm(el.getAttribute('name') || ''),
      label: findLabel(el),
      placeholder: norm(el.getAttribute('placeholder') || ''),
      visible: true,
      textual:
        tag === 'textarea' ||
        (tag === 'input' && !['checkbox', 'radio', 'hidden', 'file'].includes(type)) ||
        tag === 'select' ||
        (tag !== 'input' && tag !== 'select'),
      is_select: tag === 'select',
      is_radio: tag === 'input' && type === 'radio',
      is_checkbox: tag === 'input' && type === 'checkbox',
      required: !!el.required || el.getAttribute('aria-required') === 'true',
      options: extractOptions(el),
      top: rect.top,
      left: rect.left
    };
  });

  const buttonNodes = Array.from(root.querySelectorAll('button, a, [role="button"]'))
    .filter(isVisible)
    .map(el => ({
      kind: 'button',
      text: textOf(el),
      selector_hint: cssPath(el),
      visible: true
    }));

  const visibleText = norm(root.innerText || root.textContent || '');

  return {
    fields,
    buttons: buttonNodes,
    visible_text: visibleText
  };
}
"""
    raw = await root.evaluate(js, FORM_FIELD_SELECTOR)

    fields = [_cleanup_field(x) for x in raw.get("fields", [])]
    fields = [x for x in fields if not _drop_field(x)]

    buttons = [_cleanup_button(x) for x in raw.get("buttons", [])]
    buttons = [x for x in buttons if _keep_button(x)]

    visible_text = _cleanup_visible_text(raw.get("visible_text", ""))

    elements = []
    elements.extend(fields)
    elements.extend(buttons[:8])

    return {
        "page_url": page.url,
        "page_title": await _safe_title(page),
        "screen_index": screen_index,
        "root_selector": root_selector,
        "elements": elements,
        "visible_text": visible_text[:8000],
    }


def _cleanup_field(field: dict[str, Any]) -> dict[str, Any]:
    field = dict(field)
    field["label"] = strip_question_noise(field.get("label", ""))
    field["placeholder"] = strip_question_noise(field.get("placeholder", ""))
    return field


def _drop_field(field: dict[str, Any]) -> bool:
    joined = normalize_ws(
        " ".join(
            [
                field.get("label", ""),
                field.get("placeholder", ""),
                field.get("name", ""),
            ]
        )
    )
    if not joined:
        return False
    if is_noise_text(joined):
        return True
    return False


def _cleanup_button(button: dict[str, Any]) -> dict[str, Any]:
    button = dict(button)
    button["text"] = normalize_ws(button.get("text", ""))
    return button


def _keep_button(button: dict[str, Any]) -> bool:
    text = normalize_ws(button.get("text", ""))
    if not text:
        return False
    if is_noise_text(text):
        return False
    return bool(RELEVANT_BUTTON_RE.search(text))


def _cleanup_visible_text(text: str) -> str:
    parts = []
    seen = set()

    for raw_part in re.split(r"(?<=[\?\!\.])\s+|\s{2,}", normalize_ws(text)):
        part = strip_question_noise(raw_part)
        if not part:
            continue
        if is_noise_text(part):
            continue
        key = part.lower()
        if key in seen:
            continue
        seen.add(key)
        parts.append(part)

    return " | ".join(parts)


async def _safe_title(page) -> str:
    try:
        return await page.title()
    except Exception:
        return ""


__all__ = [
    "FORM_FIELD_SELECTOR",
    "find_active_form_root",
    "wait_for_form",
    "collect_form_screen_dump",
    "detect_already_applied_on_page",
    "click_apply_button",
    "find_apply_locator",
    "find_next_locator",
    "find_submit_locator",
]
