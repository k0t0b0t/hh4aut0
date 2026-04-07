from __future__ import annotations

from bot.core.models import Vacancy
from bot.utils.urls import extract_vacancy_id

COLLECT_JS = r"""
() => {
  function text(el) { return (el?.innerText || el?.textContent || '').trim().replace(/\s+/g, ' '); }
  function cleanUrl(href) {
    try {
      const u = new URL(href, location.origin);
      return u.origin + u.pathname + (u.search || '');
    } catch { return href || ''; }
  }
  const anchors = Array.from(document.querySelectorAll('a[href*="/vacancy/"]')).filter(a => /\/vacancy\/\d+/.test(a.href));
  const seen = new Set();
  const items = [];
  for (const a of anchors) {
    const href = cleanUrl(a.href);
    if (!href || seen.has(href)) continue;
    seen.add(href);
    const card = a.closest('[data-qa="serp-item"]') || a.closest('article') || a.closest('section') || a.closest('div');
    const title = text(a);
    if (!title) continue;
    const companyEl = card?.querySelector('[data-qa*="vacancy-serp__vacancy-employer"]') || card?.querySelector('[data-qa*="vacancy-company-name"]');
    const locationEl = card?.querySelector('[data-qa*="vacancy-serp__vacancy-address"]') || card?.querySelector('[data-qa*="vacancy-view-raw-address"]');
    const salaryEl = card?.querySelector('[data-qa*="vacancy-serp__vacancy-compensation"]') || card?.querySelector('[data-qa*="vacancy-salary"]');
    items.push({url: href, title, company: text(companyEl), location: text(locationEl), salary_text: text(salaryEl), snippet: text(card).slice(0,1500)});
  }
  return items;
}
"""


async def extract_vacancies_from_page(page, limit: int) -> list[Vacancy]:
    raw = await page.evaluate(COLLECT_JS)
    out: list[Vacancy] = []
    for item in raw[:limit]:
        url = (item.get("url") or "").strip()
        if not url:
            continue
        out.append(Vacancy(
            vacancy_id=extract_vacancy_id(url),
            url=url,
            title=(item.get("title") or "").strip(),
            company=(item.get("company") or "").strip(),
            location=(item.get("location") or "").strip(),
            salary_text=(item.get("salary_text") or "").strip(),
            snippet=(item.get("snippet") or "").strip(),
        ))
    return out
