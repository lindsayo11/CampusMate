import Link from "next/link";
export type Citation={chunk_id:string;document_id:string;text:string;source_url:string;content_hash:string;fetched_at:string;opportunity_id:string;title:string;start_offset:number;end_offset:number};
export function SourceCitations({items}:{items:Citation[]}){
 return <div>{items.map(item=><article className="card" key={item.chunk_id}><h3>{item.title}</h3><blockquote style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{item.text}</blockquote><p><a href={item.source_url} target="_blank" rel="noreferrer">核对官方原文</a> · <Link href={`/opportunity/${item.opportunity_id}`}>查看机会并行动</Link></p><p>采集时间：{new Date(item.fetched_at).toLocaleString('zh-CN')}</p><details><summary>引用定位</summary><p>原文字符位置 {item.start_offset}–{item.end_offset}</p><code style={{overflowWrap:'anywhere'}}>{item.content_hash}</code></details></article>)}</div>;
}
