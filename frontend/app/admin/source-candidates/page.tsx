import { privateApi } from "@/lib/session-api";
import { SourceCandidate, SourceCandidateReviewList } from "@/components/source-candidate-review-list";

export default async function SourceCandidatesPage() {
  const candidates = await privateApi("/v1/admin/intake/source-candidates?status=pending&limit=200") as SourceCandidate[];
  return <div className="shell page">
    <p className="eyebrow">SourceRegistry 发现审核</p>
    <h1>地方招聘平台来源候选</h1>
    <p className="lead">候选来自官方目录并保留原文证据。批准只创建未启用来源，不会自动采集；启用前仍须复核精确栏目、robots、条款和访问边界。</p>
    <SourceCandidateReviewList initial={candidates}/>
  </div>;
}
