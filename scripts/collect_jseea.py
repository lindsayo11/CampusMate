"""Collect 江苏省教育考试院 notices through the project's own governed import API.

Why this shape
--------------
The manual import endpoint (`/v1/admin/intake/education-html`) is the project's
sanctioned way to bring one already-fetched official page into the governed
pipeline: it creates the DocumentVersion, the DOM-level Evidence rows and the
DevelopmentItem, and it rejects anything that is not an official, credential-free
URL. Fetching the list page and submitting each notice through it therefore keeps
every downstream guarantee intact - no direct database writes.

Usage
-----
    # API must already be running
    python scripts/collect_jseea.py
    python scripts/collect_jseea.py --api http://127.0.0.1:8000 --limit 15
"""
import argparse
import base64
import re
import sys
import time
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

LIST_URL = "https://www.jseea.cn/webfile/index/index_zkxx/"
DETAIL = re.compile(r"/webfile/index/index_zkxx/\d{4}-\d{2}-\d{2}/\d+\.html")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CampusMate/1.0"}


def discover(limit):
    """Return [(absolute_url, title)] from the 招考信息 list page."""
    with httpx.Client(timeout=30, follow_redirects=True, verify=False,
                      trust_env=False, headers=UA) as client:
        page = BeautifulSoup(client.get(LIST_URL).text, "html.parser")
    found, seen = [], set()
    for anchor in page.select("a[href]"):
        href = anchor.get("href", "")
        if not DETAIL.search(href):
            continue
        url = str(httpx.URL(LIST_URL).join(href))
        if url in seen:
            continue
        seen.add(url)
        found.append((url, anchor.get_text(" ", strip=True)))
    return found[:limit]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--user", default="demo-user")
    parser.add_argument("--limit", type=int, default=15)
    args = parser.parse_args()

    headers = {"X-User-Id": args.user}
    with httpx.Client(timeout=60, headers=headers, trust_env=False) as api:
        seed = api.post(f"{args.api}/v1/admin/sources/seed")
        print(f"seed: {seed.status_code} {seed.text[:120]}")

        notices = discover(args.limit)
        print(f"列表页发现 {len(notices)} 条通知\n")
        imported = skipped = failed = 0
        for url, title in notices:
            with httpx.Client(timeout=30, follow_redirects=True, verify=False,
                              trust_env=False, headers=UA) as client:
                detail = client.get(url)
            body = {
                "source_code": "CM-GR-003-JS",
                "endpoint_name": "notice_list",
                "source_url": url,
                "source_item_id": url.rsplit("/", 1)[-1].replace(".html", ""),
                "adapter_config": {},
                "content_base64": base64.b64encode(detail.content).decode(),
            }
            r = api.post(f"{args.api}/v1/admin/intake/education-html", json=body)
            if r.status_code == 201:
                data = r.json()
                changed = data.get("changed", True)
                imported += bool(changed)
                skipped += not changed
                print(f"  {'新增' if changed else '未变'}  {title[:52]}")
                print(f"        证据={data.get('evidence')}  文档={str(data.get('document_version_id'))[:8]}")
            else:
                failed += 1
                print(f"  失败 {r.status_code}  {title[:44]}  {r.text[:110]}")
            time.sleep(0.4)
        print(f"\n新增 {imported} / 未变 {skipped} / 失败 {failed}")


if __name__ == "__main__":
    sys.exit(main())
