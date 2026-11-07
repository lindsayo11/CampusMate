import { EligibilityPanel } from "@/components/eligibility-panel";
export const metadata={title:'资格核对 · CampusMate 校伴'};
export default async function EligibilityPage({searchParams}:{searchParams:Promise<{opportunity_id?:string}>}) {
  return <EligibilityPanel initialId={(await searchParams).opportunity_id} />;
}
