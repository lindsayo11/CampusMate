"""Probe every SourceEndpoint in the registry for reachability and page structure.

Read-only reconnaissance: no writes to the project, no persistence. The goal is a
factual map of which endpoints can realistically be collected and how.
"""
import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

REGISTRY = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("backend/app/source_registry.yaml")
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("endpoint_probe.json")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def fetch(url, timeout=15):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as r:
            raw = r.read(600_000)
            return {"ok": True, "status": r.status, "final_url": r.url,
                    "ctype": r.headers.get("content-type", ""), "body": raw}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "error": f"HTTP {e.code}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "status": None, "error": type(e).__name__ + ": " + str(e)[:120]}


def analyze(res, fmt):
    """Classify the fetched page so we know which collection strategy applies."""
    if not res.get("ok"):
        return {"reachable": False, "why": res.get("error", "unknown")}
    body = res["body"]
    ctype = res["ctype"].lower()
    out = {"reachable": True, "status": res["status"], "bytes": len(body), "ctype": ctype}

    # Binary/document payloads: real file download, which is the best case.
    if any(k in ctype for k in ("officedocument", "msword", "excel", "pdf", "octet-stream", "zip")):
        out.update({"kind": "FILE", "parser_ok": True,
                    "note": "直接文件下载，CivilServiceWorkbookAdapter 这类可处理"})
        return out

    text = body.decode("utf-8", errors="replace")
    if text.count("<") < 5:
        out.update({"kind": "NON_HTML", "parser_ok": False,
                    "note": "非 HTML 响应"})
        return out

    # JS redirect stub (e.g. gov.cn policy library) -> we must find the real target.
    stubs = re.findall(r"window\.location\.href\s*=\s*['\"]([^'\"]+)['\"]", text)
    if len(text) < 1500 and stubs:
        out.update({"kind": "JS_REDIRECT", "parser_ok": False,
                    "redirect_to": stubs[0][:200],
                    "note": "首页是 JS 跳转壳，真实地址在 redirect_to"})
        return out

    counts = {
        "h1": len(re.findall(r"<h1[\s>]", text, re.I)),
        "article": len(re.findall(r"<article[\s>]", text, re.I)),
        "main": len(re.findall(r"<main[\s>]", text, re.I)),
        "table": len(re.findall(r"<table[\s>]", text, re.I)),
        "trs": text.count("TRS_Editor"),
        "li": len(re.findall(r"<li[\s>]", text, re.I)),
        "a_href": len(re.findall(r"<a\s[^>]*href=", text, re.I)),
        "script_src": len(re.findall(r"<script[^>]+src=", text, re.I)),
        "iframe": len(re.findall(r"<iframe[\s>]", text, re.I)),
        "password": len(re.findall(r"type=[\"']password[\"']", text, re.I)),
    }
    out["counts"] = counts
    out["has_captcha"] = ("验证码" in text) or ("captcha" in text.lower())

    # Heuristic: heavy JS + almost no server-rendered content = needs a browser.
    content_markers = counts["trs"] + counts["article"] + counts["table"] + counts["li"]
    if counts["script_src"] >= 6 and content_markers <= 2:
        out.update({"kind": "JS_RENDERED", "parser_ok": False,
                    "note": "内容由 JS 渲染，静态抓取拿不到，需要 Playwright"})
    elif counts["trs"] or counts["article"] or counts["main"] or counts["table"]:
        adapters = []
        if counts["trs"] or counts["article"] or counts["main"]:
            adapters.append("MoEPolicyAdapter(h1+article/.TRS_Editor/main)")
        if counts["table"]:
            adapters.append("YZChsiAdapter(需表头匹配)")
        out.update({"kind": "STATIC_HTML", "parser_ok": True,
                    "possible_adapters": adapters,
                    "note": "服务端渲染静态页，改 selector 后有望直接采集"})
    else:
        out.update({"kind": "LIST_PAGE", "parser_ok": True,
                    "note": "列表/栏目页，含 " + str(counts["a_href"]) + " 个链接，可做 discover"})
    return out


def probe_source(item):
    name, code = item["name"], item["code"]
    rows = []
    for ep in item.get("endpoints", []):
        url, fmt = ep["url"], ep.get("format", "html")
        res = fetch(url)
        info = analyze(res, fmt)
        rows.append({
            "source": code, "source_name": name, "endpoint": ep["name"],
            "url": url, "declared_format": fmt, "declared_auth": ep.get("auth_type", "none"),
            "access_tags": ep.get("access_tags", []), "automation": ep.get("automation_level"),
            "parser_type": ep.get("parser_type", ""), **info,
        })
    return rows


def main():
    body = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    sources = body["sources"]
    print(f"探测 {len(sources)} 个来源...\n", flush=True)
    all_rows = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for rows in pool.map(probe_source, sources):
            all_rows.extend(rows)
            for r in rows:
                flag = "OK " if r.get("reachable") else "XX "
                kind = r.get("kind", "-")
                print(f"{flag}{r['source']:<24} {r['endpoint']:<34} {kind}", flush=True)

    out = OUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(all_rows, ensure_ascii=False, indent=2), encoding="utf-8")

    # Summary
    from collections import Counter
    reach = Counter(r.get("reachable") for r in all_rows)
    kinds = Counter(r.get("kind", "UNREACHABLE") for r in all_rows)
    print("\n" + "=" * 60)
    print("可达性:", dict(reach))
    print("类型分布:", dict(kinds))
    print("结果已写入:", out)


if __name__ == "__main__":
    main()
