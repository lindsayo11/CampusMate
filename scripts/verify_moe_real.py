"""Re-run the decisive adapter verification with the real MOE policy detail page."""
import sys
from pathlib import Path

BACKEND = Path(r"D:\CampusMate\backend")
sys.path.insert(0, str(BACKEND))

import urllib.request  # noqa: E402

from app.adapters import (  # noqa: E402
    MoEPolicyAdapter, YZChsiAdapter, UniversityNoticeAdapter,
    InstitutionRecruitmentAdapter,
)
from app.adapters.entrepreneurship import GovernmentPolicyAdapter  # noqa: E402
from app.adapters.base import RawArtifact  # noqa: E402

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"


def grab(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with OPENER.open(req, timeout=25) as r:
        return r.read(), r.headers.get("content-type", "")


CASES = [
    ("MoEPolicyAdapter", MoEPolicyAdapter, "教育部·2027研考管理规定(真实政策详情)",
     "http://www.moe.gov.cn/srcsite/A15/moe_778/s3261/202609/t20260923_1451734.html"),
    ("MoEPolicyAdapter", MoEPolicyAdapter, "教育部·新闻详情(有 .TRS_Editor)",
     "http://www.moe.gov.cn/jyb_xwfb/moe_176/202609/t20260929_1452614.html"),
]


def main():
    print("=" * 78)
    print("MoEPolicyAdapter 对真实教育部页面（改 selector 前）")
    print("=" * 78)
    for name, cls, label, url in CASES:
        print(f"\n--- {name} | {label}")
        print(f"    {url[:92]}")
        try:
            data, ctype = grab(url)
        except Exception as e:  # noqa: BLE001
            print(f"    抓取失败: {type(e).__name__}: {str(e)[:90]}")
            continue
        try:
            parsed = cls().parse(RawArtifact(content=data, canonical_url=url,
                                             source_item_id="probe", content_type=ctype))
            recs = parsed.records
            print(f"    [OK] 解析: {len(recs)} 条记录, {len(parsed.evidence)} 条证据")
            for r in recs[:1]:
                t = str(r.get("title"))[:80]
                b = str(r.get("body"))[:120]
                print(f"         title={t}")
                print(f"         body[:120]={b}")
        except Exception as e:  # noqa: BLE001
            print(f"    [FAIL] {type(e).__name__}: {str(e)[:140]}")


if __name__ == "__main__":
    main()
