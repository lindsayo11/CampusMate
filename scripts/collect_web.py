"""Collect notices from static official sources through the project's governed import API.

Each source is described by: a list page, a regex that recognises its detail links,
the registered source_code / endpoint_name, and (optionally) a fixed development-channel
path code when the whole source belongs to one channel.

Everything is submitted to `/v1/admin/intake/education-html`, so DocumentVersion,
DOM-level Evidence and DevelopmentItem are all produced by the project's own ingest
logic - this script never writes to the database directly.

Usage
-----
    python scripts/collect_web.py --source jseea
    python scripts/collect_web.py --source jsj --source tzb
    python scripts/collect_web.py --source all --limit 20
"""
import argparse
import base64
import re
import sys
import time
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

SOURCES = {
    # 江苏省教育考试院：招考信息列表，详情 /webfile/index/index_zkxx/YYYY-MM-DD/<id>.html
    # 内容横跨考研/证书考试，交给 classify_path 按正文分类。
    "jseea": {
        "name": "江苏省教育考试院",
        "source_code": "CM-GR-003-JS",
        "endpoint_name": "notice_list",
        "list_url": "https://www.jseea.cn/webfile/index/index_zkxx/",
        "detail": re.compile(r"/webfile/index/index_zkxx/\d{4}-\d{2}-\d{2}/\d+\.html"),
        "path_code": None,
    },
    # 教育涉外监管信息网：整体属涉外教育监管，固定挂「境外留学」。
    "jsj": {
        "name": "教育涉外监管信息网",
        "source_code": "CM-OS-002",
        "endpoint_name": "policy_documents",
        "list_url": "https://jsj.moe.gov.cn/api/index/sortlist/1",
        "detail": re.compile(r"/n2/\d+/\d+/\d+\.shtml"),
        "path_code": "overseas_study",
    },
    # 挑战杯：创新创业赛事，固定挂「创新创业」。
    "tzb": {
        "name": "挑战杯",
        "source_code": "CM-ENT-008",
        "endpoint_name": "news_list",
        "list_url": "https://www.tiaozhanbei.net/tzb",
        "detail": re.compile(r"/article/\d+/?$"),
        "path_code": "entrepreneurship",
    },
}

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) CampusMate/1.0"}


def discover(config, limit):
    with httpx.Client(timeout=30, follow_redirects=True, verify=False,
                      trust_env=False, headers=UA) as client:
        page = BeautifulSoup(client.get(config["list_url"]).text, "html.parser")
    found, seen = [], set()
    for anchor in page.select("a[href]"):
        href = anchor.get("href", "")
        if not config["detail"].search(href):
            continue
        url = str(httpx.URL(config["list_url"]).join(href))
        if url in seen:
            continue
        seen.add(url)
        found.append((url, anchor.get_text(" ", strip=True)))
    return found[:limit]


def collect(api_url, user, key, config, limit):
    headers = {"X-User-Id": user}
    notices = discover(config, limit)
    print("=" * 78)
    print(f"{config['name']}  ({key})  — 列表发现 {len(notices)} 条")
    print("=" * 78)
    added = unchanged = failed = 0
    with httpx.Client(timeout=60, headers=headers, trust_env=False) as api:
        for url, title in notices:
            with httpx.Client(timeout=30, follow_redirects=True, verify=False,
                              trust_env=False, headers=UA) as client:
                detail = client.get(url)
            payload = {
                "source_code": config["source_code"],
                "endpoint_name": config["endpoint_name"],
                "source_url": url,
                "source_item_id": re.sub(r"\W+", "-", url.rsplit("/", 2)[-2:][0] + "-" +
                                         url.rsplit("/", 1)[-1].replace(".shtml", "")
                                         .replace(".html", ""))[:120],
                "adapter_config": ({"path_code": config["path_code"]}
                                   if config["path_code"] else {}),
                "content_base64": base64.b64encode(detail.content).decode(),
            }
            r = api.post(f"{api_url}/v1/admin/intake/education-html", json=payload)
            if r.status_code == 201:
                data = r.json()
                changed = data.get("changed", True)
                added += bool(changed)
                unchanged += not changed
                flag = "新增" if changed else "未变"
                print(f"  {flag}  {title[:50]}")
                print(f"        正文={len(data.get('body', '') or '')}  证据={data.get('evidence')}")
            else:
                failed += 1
                print(f"  失败 {r.status_code}  {title[:40]}  {r.text[:100]}")
            time.sleep(0.4)
    print(f"\n  新增 {added} / 未变 {unchanged} / 失败 {failed}\n")
    return added


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", default=[],
                        help="jseea / jsj / tzb，可重复；all 表示全部")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--user", default="demo-user")
    parser.add_argument("--limit", type=int, default=15)
    args = parser.parse_args()

    keys = list(SOURCES) if (not args.source or "all" in args.source) else args.source
    unknown = [k for k in keys if k not in SOURCES]
    if unknown:
        print(f"未知源: {unknown}；可选 {list(SOURCES)}")
        return 1

    with httpx.Client(timeout=60, headers={"X-User-Id": args.user},
                      trust_env=False) as api:
        seed = api.post(f"{args.api}/v1/admin/sources/seed")
        print(f"seed: {seed.status_code} {seed.text[:110]}\n")

    total = 0
    for key in keys:
        total += collect(args.api, args.user, key, SOURCES[key], args.limit)
    print(f"合计新增 {total} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
