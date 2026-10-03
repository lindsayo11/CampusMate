type DiscoveryConfig = {discovery_format?:string;index_formats?:Record<string,string>};

export function discoveryLabel(source:DiscoveryConfig, url:string):string {
  const format=source.index_formats?.[url]||source.discovery_format||'auto';
  return ({rss:'RSS 订阅',atom:'Atom 订阅',json:'公开接口',sitemap:'网站地图'} as Record<string,string>)[format]||'网页栏目';
}
