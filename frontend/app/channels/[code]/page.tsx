import {notFound} from 'next/navigation';
import {CatalogView} from '@/components/catalog-view';
import {getChannel,type CatalogFilters} from '@/lib/development-channels';

export default async function ChannelPage({params,searchParams}:{params:Promise<{code:string}>;searchParams:Promise<CatalogFilters>}){
  const {code}=await params;
  const channel=getChannel(code);
  if(!channel)notFound();
  return <CatalogView channel={channel} filters={await searchParams}/>;
}
