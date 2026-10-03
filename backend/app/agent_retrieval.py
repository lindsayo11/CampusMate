"""Sparse text vectors: no semantic-embedding claim, public evidence only."""
import math
import re
from collections import Counter
from .data_catalog import visible


def vector(text):
    words=re.findall(r'[a-z0-9]+',text.lower())
    for part in re.findall(r'[\u4e00-\u9fff]+',text):
        words.extend(part[i:i+2] for i in range(len(part)-1))
    return {word:1+math.log(count) for word,count in Counter(words).items()}


def retrieve(db,query):
    q=vector(query);qn=math.sqrt(sum(v*v for v in q.values()));matches=[]
    if not qn:return []
    for pub,data in visible(db):
        for e in data['evidence']:
            quote=e['quote_or_normalized_fact']
            for offset in range(0,len(quote),700):
                chunk=quote[offset:offset+900];v=vector(chunk);norm=math.sqrt(sum(x*x for x in v.values()))
                score=sum(weight*v.get(word,0) for word,weight in q.items())/(qn*norm) if norm else 0
                if score>0:matches.append({'publication_id':pub.id,'evidence_id':e['id'],
                    'url':data['document']['canonical_url'],'quote':chunk,'location':e['evidence_location'],
                    'score':round(score,5),'content_hash':data['document']['content_hash']})
    return sorted(matches,key=lambda x:-x['score'])[:8]
