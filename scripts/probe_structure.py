"""Probe REAL page structures to find the true content container per site.

For each candidate site, dump the top content containers by text volume, so we can
calibrate adapter selectors against evidence instead of guessing.
"""
import json
import sys
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

TARGETS = [
    # ---- 教育部 (MoEPolicyAdapter) ----
    ("MOE 政策详情 srcsite",
     "http://www.moe.gov.cn/srcsite/A15/moe_778/s3261/202609/t20260923_1451734.html"),
    ("MOE 新闻详情 moe_176",
     "http://www.moe.gov.cn/jyb_xwfb/moe_176/202609/t20260929_1452614.html"),
    # ---- 研招网 专业目录 (YZChsiAdapter) ----
    ("研招网 硕士目录 zsml",
     "https://yz.chsi.com.cn/zsml/"),
    ("研招网 专业目录查询页",
     "https://yz.chsi.com.cn/zsml/queryAction.do"),
    # ---- 高校研招通知 (UniversityNoticeAdapter) ----
    ("北大 xxgk 栏目",
     "https://admission.pku.edu.cn/xxgk/index2.htm"),
    ("清华 zxgg 栏目",
     "https://yz.tsinghua.edu.cn/zxgg.htm"),
    ("复旦 gsao 首页",
     "https://gsao.fudan.edu.cn/main.htm"),
    # ---- 政府政策 (GovernmentPolicyAdapter) ----
    ("gov.cn 政策文库",
     "https://www.gov.cn/zhengce/zhengcewenjianku/"),
    ("gov.cn 搜索结果页",
     "https://sousuo.www.gov.cn/zcwjk/policyDocumentLibrary?t=zhengcelibrary"),
    ("税务总局 首页",
     "https://www.chinatax.gov.cn/"),
    # ---- 涉外监管 (OverseasRegistryAdapter) ----
    ("涉外监管网 jsj",
     "https://jsj.moe.gov.cn/"),
    # ---- 留学/开放数据 (OverseasRegistryAdapter) ----
    ("Discover Uni",
     "https://discoveruni.gov.uk/"),
    ("Study in Japan",
     "https://www.studyinjapan.go.jp/en/search-for-schools/school_search.php?lang=en"),
    ("CRICOS",
     "https://cricos.education.gov.au/"),
]


def grab(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    with OPENER.open(req, timeout=25) as r:
        return r.read(), r.status, r.headers.get("content-type", "")


def describe(url):
    out = {"url": url}
    try:
        data, status, ctype = grab(url)
    except Exception as e:  # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {str(e)[:120]}"
        return out
    out.update(status=status, ctype=ctype, bytes=len(data))
    if "text/html" not in ctype.lower():
        out["non_html"] = True
        return out
    soup = BeautifulSoup(data, "html.parser")
    out["title"] = (soup.title.get_text(strip=True) if soup.title else "")[:110]
    out["h1_count"] = len(soup.select("h1"))
    out["h1_text"] = (soup.select_one("h1").get_text(" ", strip=True)[:110]
                      if soup.select("h1") else "")
    # top containers by text volume
    containers = []
    for el in soup.find_all(["div", "article", "main", "section", "td"]):
        text = el.get_text(" ", strip=True)
        if len(text) < 400:
            continue
        p_count = len(el.find_all("p"))
        containers.append({
            "tag": el.name,
            "id": el.get("id"),
            "class": el.get("class"),
            "text_len": len(text),
            "p": p_count,
            "a": len(el.find_all("a")),
        })
    containers.sort(key=lambda x: x["text_len"], reverse=True)
    out["top_containers"] = containers[:6]
    out["trs_editor"] = len(soup.select(".TRS_Editor"))
    out["article"] = len(soup.select("article"))
    out["main"] = len(soup.select("main"))
    out["table"] = len(soup.select("table"))
    out["tables_with_rows"] = [
        {"rows": len(t.select("tr")),
         "header": [c.get_text(" ", strip=True) for c in t.select("tr")[0].select("th, td")][:8]}
        for t in soup.select("table") if t.select("tr")
    ][:5]
    return out


def main():
    results = []
    for label, url in TARGETS:
        print("=" * 78)
        print(label)
        print(url)
        r = describe(url)
        results.append({"label": label, **r})
        if r.get("error"):
            print(f"  [ERR] {r['error']}")
            continue
        print(f"  status={r['status']} bytes={r['bytes']} title={r.get('title','')[:80]}")
        print(f"  h1={r.get('h1_count')} article={r.get('article')} main={r.get('main')} "
              f".TRS_Editor={r.get('trs_editor')} table={r.get('table')}")
        if r.get("h1_text"):
            print(f"  h1_text: {r['h1_text'][:90]}")
        for c in r.get("top_containers", [])[:4]:
            print(f"    <{c['tag']}> id={c['id']} class={c['class']} "
                  f"text={c['text_len']} p={c['p']} a={c['a']}")
        for t in r.get("tables_with_rows", [])[:2]:
            print(f"    table rows={t['rows']} header={t['header']}")
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("structure_probe.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n写入 {out}")


if __name__ == "__main__":
    sys.exit(main())
