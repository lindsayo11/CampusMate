import Link from "next/link";
import { privateApi } from "@/lib/session-api";

type DocumentDetail = { id: string; canonical_url: string; version_no: number; fetched_at: string; content_hash: string; raw_text: string; diff: string };

export default async function IntakeDocumentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const document = await privateApi(`/v1/admin/intake/documents/${id}`) as DocumentDetail;
  return <div className="shell page"><Link href="/admin/source-changes">返回变化审核</Link><h1>来源文档版本 {document.version_no}</h1>
    <p>抓取：{new Date(document.fetched_at).toLocaleString("zh-CN")}</p><a href={document.canonical_url} target="_blank" rel="noreferrer">打开官方原文</a>
    <p><code>{document.content_hash}</code></p><h2>与上一版本差异</h2><pre style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>{document.diff || "首个版本"}</pre>
    <h2>当前解析正文</h2><pre style={{whiteSpace:"pre-wrap",overflowWrap:"anywhere"}}>{document.raw_text}</pre></div>;
}
