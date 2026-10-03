"""Verify MoEPolicyAdapter / YZChsiAdapter against REAL live pages.

This is the decisive test: run the project's own adapters, unmodified, against
pages actually fetched from the internet, and see which ones genuinely work.
"""
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
    with OPENER.open(req, timeout=20) as r:
        return r.read(), r.headers.get("content-type", "")


CASES = [
    ("MoEPolicyAdapter", MoEPolicyAdapter, "教育部·回信详情页",
     "http://www.moe.gov.cn/jyb_xwfb/moe_176/202609/t20260929_1452614.html"),
    ("MoEPolicyAdapter", MoEPolicyAdapter, "教育部·首页(现配置URL)",
     "https://www.moe.gov.cn/"),
    ("UniversityNoticeAdapter", UniversityNoticeAdapter, "北大研究生招生通知",
     "https://admission.pku.edu.cn/xxgk/index2.htm"),
    ("UniversityNoticeAdapter", UniversityNoticeAdapter, "清华研究生招生",
     "https://yz.tsinghua.edu.cn/zxgg.htm"),
    ("YZChsiAdapter", YZChsiAdapter, "研招网·硕士目录",
     "https://yz.chsi.com.cn/zsml/"),
    ("YZChsiAdapter", YZChsiAdapter, "研招网·首页",
     "https://yz.chsi.com.cn/"),
    ("InstitutionRecruitmentAdapter", InstitutionRecruitmentAdapter, "人社部事业单位平台",
     "https://www.mohrss.gov.cn/SYrlzyhshbzb/fwyd/SYkaoshizhaopin/zyhgjjgsydwgkzp/"),
    ("GovernmentPolicyAdapter", GovernmentPolicyAdapter, "gov.cn政策库(现配置URL)",
     "https://www.gov.cn/zhengce/zhengcewenjianku/"),
]


def main():
    print("=" * 78)
    print("用项目自带适配器，直接跑真实线上页面")
    print("=" * 78)
    for name, cls, label, url in CASES:
        print(f"\n--- {name} | {label}")
        print(f"    {url[:88]}")
        try:
            data, ctype = grab(url)
        except Exception as e:  # noqa: BLE001
            print(f"    抓取失败: {type(e).__name__}: {str(e)[:90]}")
            continue
        try:
            parsed = cls().parse(RawArtifact(content=data, canonical_url=url,
                                             source_item_id="probe", content_type=ctype))
            recs = parsed.records
            print(f"    [OK] 解析成功: {len(recs)} 条记录, {len(parsed.evidence)} 条证据")
            for r in recs[:2]:
                keys = list(r.items())[:4]
                print(f"         {str(keys)[:150]}")
            if parsed.evidence:
                ev = parsed.evidence[0]
                print(f"         首条证据位置: {str(ev.get('evidence_location'))[:80]}")
        except Exception as e:  # noqa: BLE001
            print(f"    [FAIL] {type(e).__name__}: {str(e)[:140]}")


if __name__ == "__main__":
    main()
