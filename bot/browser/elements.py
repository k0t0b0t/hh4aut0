from __future__ import annotations

JS_SCREEN = r"""
() => {
  function norm(s) { return (s || '').replace(/\s+/g, ' ').trim(); }
  function visible(el) {
    const style = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    const type = (el.getAttribute('type') || '').toLowerCase();
    return style.display !== 'none' && style.visibility !== 'hidden' && r.width > 6 && r.height > 6 && type !== 'hidden';
  }
  function cssPath(el) {
    if (!(el instanceof Element)) return '';
    const path = [];
    while (el && el.nodeType === Node.ELEMENT_NODE) {
      let sel = el.nodeName.toLowerCase();
      if (el.id) { sel += '#' + CSS.escape(el.id); path.unshift(sel); break; }
      let sib = el, nth = 1;
      while ((sib = sib.previousElementSibling) != null) if (sib.nodeName.toLowerCase() === sel) nth++;
      sel += `:nth-of-type(${nth})`;
      path.unshift(sel);
      el = el.parentElement;
    }
    return path.join(' > ');
  }
  function textOf(el) { return norm(el?.innerText || el?.textContent || ''); }
  const texts = Array.from(document.querySelectorAll('label, div, span, p, strong, b, legend, h1, h2, h3')).filter(visible).map(el => {
    const r = el.getBoundingClientRect();
    return {text: textOf(el), top: r.top, left: r.left};
  }).filter(x => x.text && x.text.length < 300);
  function nearby(field) {
    const fr = field.getBoundingClientRect();
    return texts.filter(t => Math.abs(fr.top - t.top) <= 120 && Math.abs(fr.left - t.left) <= 240).slice(0,6).map(x => x.text).join(' | ');
  }
  function question(field) {
    const aria = norm(field.getAttribute('aria-label') || '');
    if (aria) return aria;
    const ph = norm(field.getAttribute('placeholder') || '');
    const id = field.getAttribute('id') || '';
    if (id) {
      const l = document.querySelector(`label[for="${id}"]`); if (l) { const t = textOf(l); if (t) return t; }
    }
    const p = field.closest('label'); if (p) { const t = textOf(p); if (t) return t; }
    return ph || nearby(field);
  }
  const elements = [];
  const fields = Array.from(document.querySelectorAll('textarea, input, select, [contenteditable="true"]')).filter(visible);
  for (let i=0; i<fields.length; i++) {
    const el = fields[i];
    const tag = (el.tagName || '').toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    elements.push({
      kind: tag,
      tag,
      type,
      selector_hint: cssPath(el),
      label: question(el),
      placeholder: norm(el.getAttribute('placeholder') || ''),
      visible: true,
      textual: tag === 'textarea' || (tag === 'input' && !['checkbox','radio','hidden','file'].includes(type)),
      is_select: tag === 'select',
      is_radio: tag === 'input' && type === 'radio',
      is_checkbox: tag === 'input' && type === 'checkbox',
      nearby_text: nearby(el),
    });
  }
  const buttons = Array.from(document.querySelectorAll('button, a, [role="button"]')).filter(visible).slice(0, 80);
  for (const el of buttons) {
    elements.push({kind: 'button', text: textOf(el), selector_hint: cssPath(el), visible: true});
  }
  return {elements, visible_text: norm(document.body.innerText).slice(0, 7000)};
}
"""


async def build_screen_dump(page, screen_index: int) -> dict:
    payload = await page.evaluate(JS_SCREEN)
    return {
        "page_url": page.url,
        "page_title": await page.title(),
        "screen_index": screen_index,
        **payload,
    }
