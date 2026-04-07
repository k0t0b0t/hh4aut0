from __future__ import annotations

import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse


def extract_vacancy_id(url: str) -> str:
    match = re.search(r"/vacancy/(\d+)", url)
    return match.group(1) if match else url


def set_page_param(url: str, page_num: int, param_name: str = "page") -> str:
    parts = urlparse(url)
    query = parse_qs(parts.query, keep_blank_values=True)
    query[param_name] = [str(page_num)]
    new_query = urlencode(query, doseq=True)
    return urlunparse((parts.scheme, parts.netloc, parts.path, parts.params, new_query, parts.fragment))
