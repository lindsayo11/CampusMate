"""Probe robots.txt / terms / licence reachability for the endpoints we want to calibrate.

Gate requirements (intake_governance.PROOF_KEYS) need real quotes from:
  robots_url + robots_quote, terms_url + terms_quote, license_url + license_quote
This script fetches those documents so the quotes we record are genuine, not invented.
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

HOSTS = [
    "www.moe.gov.cn",
    "yz.chsi.com.cn",
    "admission.pku.edu.cn",
    "yz.tsinghua.edu.cn",
    "yzb.sjtu.edu.cn",
    "gsao.fudan.edu.cn",
    "jsj.moe.gov.cn",
    "www.gov.cn",
    "www.chinatax.gov.cn",
    "www.gd.gov.cn",
]


def grab(url, limit=40000):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with OPENER.open(req, timeout=20) as r:
        return r.status, r.headers.get("content-type", ""), r.read(limit)


def main():
    report = {}
    for host in HOSTS:
        print("=" * 74)
        print(host)
        entry = {}
        for label, url in (("robots.txt", f"https://{host}/robots.txt"),):
            try:
                status, ctype, data = grab(url)
                text = data.decode("utf-8", errors="replace")
                entry[label] = {"status": status, "url": url, "bytes": len(data),
                                "head": text[:600]}
                print(f"  {label}: {status} {len(data)}B")
                low = text.lower()
                if "disallow: /" in low.replace(" ", ""):
                    print("    !! 含 Disallow: / 规则，需逐条看 UA")
                for line in text.splitlines()[:25]:
                    print(f"      {line}")
            except Exception as e:  # noqa: BLE001
                entry[label] = {"error": f"{type(e).__name__}: {str(e)[:100]}"}
                print(f"  {label}: ERR {type(e).__name__}: {str(e)[:80]}")
        report[host] = entry

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("robots_probe.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n写入 {out}")


if __name__ == "__main__":
    sys.exit(main())
