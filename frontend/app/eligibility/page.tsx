import { EligibilityPanel } from "@/components/eligibility-panel";
import { getOpportunities } from "@/lib/api";
import {PageHeading} from "@/components/ui";
export default async function EligibilityPage({searchParams}:{searchParams:Promise<{opportunity_id?:string}>}) {
  const data = await getOpportunities(undefined,undefined,'all');
  return <div className="shell page narrow"><PageHeading eyebrow="ELIGIBILITY CHECK" title="我能报吗" description="逐条比对个人资料和已核验的限制条件。资料不足时会明确提示，最终以官方原文为准。"/><EligibilityPanel opportunities={data.items} initialId={(await searchParams).opportunity_id} /></div>;
}
