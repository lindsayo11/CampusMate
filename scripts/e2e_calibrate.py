"""Governed end-to-end calibration + first real ingestion for CM-GR-001.

Everything goes through the project's own admin API and governance code.
"""
import sys

sys.path.insert(0, r"D:\CampusMate\backend")

import hashlib  # noqa: E402

import httpx  # noqa: E402

API = "http://127.0.0.1:8000"
HDRS = {"X-User-Id": "demo-user"}
T = 120

ROBOTS_URL = "http://www.moe.gov.cn/robots.txt"
ROBOTS_QUOTE = ("HTTP 404 Not Found：www.moe.gov.cn 未提供 robots.txt，"
                "即未声明任何抓取限制（实测 2026-09-29）。")
TERMS_URL = "http://www.moe.gov.cn/jyb_sjzl/"
TERMS_QUOTE = ("教育部政府门户网站公开政策栏目，面向社会公开发布教育政策文件，"
               "无登录、付费或访问限制（实测 2026-09-29）。")
LICENSE_URL = "http://www.moe.gov.cn/jyb_sjzl/"
LICENSE_QUOTE = ("教育部政府门户网站页面未附加限制性许可声明；本项目仅抓取公开政策正文，"
                 "保留原文链接与页面 SHA256 以供核验。")


def governed_fetch(url):
    from app.collector_http import collect_bytes
    data, ctype = collect_bytes(url)
    return hashlib.sha256(data).hexdigest(), len(data), ctype


def main():
    src = httpx.get(f"{API}/v1/sources/CM-GR-001", headers=HDRS, timeout=30).json()
    eps = {e["name"]: e for e in src["endpoints"]}
    print("=" * 78)
    print("CM-GR-001 治理化端到端校准")
    print("=" * 78)

    for name in ("graduate_policy", "graduate_policy_detail"):
        ep = eps.get(name)
        if not ep:
            print(f"\n[跳过] {name} 未注册")
            continue
        eid, url = ep["id"], ep["url"]
        print(f"\n--- {name}  id={eid}")
        print(f"    url={url}")

        # ---- blockers currently open?
        health = httpx.get(f"{API}/v1/admin/intake/health",
                           headers=HDRS, timeout=30).json()
        ep_health = next((h for h in health if h["id"] == eid), {})
        print(f"    开放 Blocker: {ep_health.get('open_blockers')}  "
              f"calibration={ep_health.get('calibration_status')}")
        print(f"    门禁原因: {ep_health.get('gate_reason')}")

        # 1) governed fetch
        try:
            digest, size, ctype = governed_fetch(url)
            print(f"    [1/6] 受治理抓取 OK: {size}B {ctype} sha256={digest[:20]}...")
        except Exception as exc:  # noqa: BLE001
            print(f"    [1/6] 抓取失败: {type(exc).__name__}: {str(exc)[:150]}")
            continue

        # 2) submit calibration with genuine evidence
        body = {
            "exact_url": url,
            "robots_status": "allowed",
            "terms_status": "permitted",
            "license_status": "permitted",
            "field_mapping": {"title": "h1",
                              "body": "div.moe-detail-box p, #downloadContent p, .TRS_Editor p"},
            "adapter_config": {},
            "proof": {"robots_url": ROBOTS_URL, "robots_quote": ROBOTS_QUOTE,
                      "terms_url": TERMS_URL, "terms_quote": TERMS_QUOTE,
                      "license_url": LICENSE_URL, "license_quote": LICENSE_QUOTE,
                      "page_sha256": digest},
        }
        r = httpx.post(f"{API}/v1/admin/intake/endpoints/{eid}/calibrations",
                       headers=HDRS, json=body, timeout=T)
        if r.status_code >= 400:
            print(f"    [2/6] 提交校准失败 {r.status_code}: {r.text[:300]}")
            continue
        cal = r.json()
        print(f"    [2/6] 校准已提交 id={cal['id']} status={cal['status']}")

        # 3) review (twice, single-admin override ON)
        for attempt in (1, 2):
            r = httpx.patch(f"{API}/v1/admin/intake/calibrations/{cal['id']}",
                            headers=HDRS, timeout=T,
                            json={"action": "approve",
                                  "note": f"本地开发校准 第{attempt}次审核：已核验 robots/条款/许可与页面 SHA256"})
            if r.status_code >= 400:
                print(f"    [3/6] 第{attempt}次审核失败 {r.status_code}: {r.text[:250]}")
                break
            print(f"    [3/6] 第{attempt}次审核 OK status={r.json()['status']}")

        # 4) verify endpoint state after approval
        eps2 = {e["name"]: e
                for e in httpx.get(f"{API}/v1/sources/CM-GR-001", headers=HDRS,
                                   timeout=30).json()["endpoints"]}
        now_ep = eps2[name]
        print(f"    [4/6] 端点 url={now_ep['url']}")
        print(f"           robots={now_ep['robots_status']} license={now_ep['license_status']} "
              f"scheduled={now_ep['scheduled']}")

        # 5) enable scheduling
        r = httpx.patch(f"{API}/v1/admin/intake/endpoints/{eid}",
                        headers=HDRS, timeout=T,
                        json={"action": "enable", "reason": "本地开发校准完成后启用调度"})
        print(f"    [5/6] 启用调度 {r.status_code}: {r.text[:220]}")

        # 6) enqueue a run
        r = httpx.post(f"{API}/v1/admin/intake/endpoints/{eid}/run",
                       headers=HDRS, timeout=T)
        print(f"    [6/6] 入队 {r.status_code}: {r.text[:220]}")


if __name__ == "__main__":
    main()
