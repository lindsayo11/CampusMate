import {redirect} from 'next/navigation';
import {CatalogView} from '@/components/catalog-view';
import {catalogHref,getChannel,type CatalogFilters} from '@/lib/development-channels';

export default async function DataPage({searchParams}:{searchParams:Promise<CatalogFilters>}){
  const filters=await searchParams;
  const channel=getChannel(filters.path);
  if(channel)redirect(catalogHref(channel.code,filters));
  return <CatalogView filters={filters}/>;
}
