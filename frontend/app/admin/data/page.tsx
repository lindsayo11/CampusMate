import Link from "next/link";
import {privateApi} from "@/lib/session-api";
import {CorrectionQueue} from '@/components/data-correction';
import {DataConsole,DataImport} from "@/components/data-console";

export default async function DataAdmin({searchParams}:{searchParams:Promise<{offset?:string}>}) {
  const params=await searchParams;
  const offset=Math.max(0,Number(params.offset)||0);
  const [overview,documents,corrections]=await Promise.all([privateApi("/v1/admin/data/overview"),
    privateApi(`/v1/admin/data/documents?offset=${offset}&limit=30`),privateApi("/v1/admin/data/corrections")]);
  return <div className="shell page"><p className="eyebrow">数据工作台</p><h1>接入、证据与发布</h1>
    <p>系统导入通过完整性校验后直接发布；手动导入经审核后发布。来源停用、内容变更或撤回后，旧版本不再作为当前事实展示。</p>
    <div className="actions"><Link href="/admin/notice-watch">官方栏目持续采集</Link><Link href="/admin/registry">来源校准</Link><Link href="/data">公开信息中心</Link><Link href="/admin/entrepreneurship">政策关系</Link></div>
    <section className="card"><p>文档 {overview.documents} 份；已发布 {overview.publications.published||0} 份；开放阻塞 {overview.blockers.open||0} 项</p>
      <details><summary>各端点实际可用状态</summary><ul>{overview.endpoints.map((e:{id:string;name:string;parser_type:string;gate_reason:string|null})=><li key={e.id}>{e.name} / {e.parser_type}：{e.gate_reason||"校准门禁通过"}</li>)}</ul></details></section>
    <CorrectionQueue initial={corrections}/><DataImport/><DataConsole documents={documents.items}/>
    <nav>{offset>0&&<Link href={`/admin/data?offset=${Math.max(0,offset-30)}`}>上一页</Link>} {offset+30<documents.total&&<Link href={`/admin/data?offset=${offset+30}`}>下一页</Link>}</nav>
  </div>;
}
