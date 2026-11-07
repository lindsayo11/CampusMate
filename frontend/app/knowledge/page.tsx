import {KnowledgeLibrary} from '@/components/knowledge-library';

export const metadata={title:'原文依据 · CampusMate 校伴'};
export default async function Knowledge({searchParams}:{searchParams:Promise<{document_id?:string}>}){
  return <KnowledgeLibrary initialDocument={(await searchParams).document_id}/>;
}
