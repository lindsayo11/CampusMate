import { privateApi } from "@/lib/session-api";
import { SourceChange, SourceChangeReviewList } from "@/components/source-change-review-list";

export default async function SourceChangesPage() {
  const items = await privateApi("/v1/admin/intake/change-reviews?status=pending") as SourceChange[];
  return <div className="shell page"><p className="eyebrow">来源变化</p><h1>DocumentVersion 变化审核</h1>
    <p className="lead">内容变化不会直接覆盖已确认事实。先核对版本差异和原文，再确认或拒绝。</p>
    <SourceChangeReviewList initial={items}/></div>;
}
