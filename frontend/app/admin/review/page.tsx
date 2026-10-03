import { privateApi } from "@/lib/session-api";
const getReviews=()=>privateApi("/v1/admin/reviews");
import { ReviewQueue } from "@/components/review-queue";
export default async function Review(){return <div className="shell page"><p className="eyebrow">内容治理</p><h1>待审核队列</h1><p className="lead">低置信度或高风险内容必须人工确认后才能上线。</p><ReviewQueue initial={await getReviews()}/></div>}
