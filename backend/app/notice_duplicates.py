"""Group byte-identical notices; titles alone never establish identity."""
import hashlib


def group_identical(items):
    groups={};result=[]
    for item in items:
        # Different item rows in a multi-item document are not duplicates.
        identity=(item['document'].get('content_hash'),item['title'],item.get('start_time'),
            item.get('deadline'),item.get('description'),tuple(p['code'] for p in item.get('paths',[])))
        if not identity[0]:
            result.append({**item,'duplicate_count':1,'alternate_sources':[]});continue
        if identity in groups:
            first=groups[identity]
            first['duplicate_count']+=1
            first['alternate_sources'].append({'publication_id':item['publication_id'],
                'source':item['source'],'url':item['document']['canonical_url']})
        else:
            first={**item,'duplicate_count':1,'alternate_sources':[]}
            groups[identity]=first;result.append(first)
    return result
