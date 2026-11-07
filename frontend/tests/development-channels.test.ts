import test from 'node:test';
import assert from 'node:assert/strict';
import {developmentChannels,getChannel,channelHref,catalogHref,currentChannel,noticeHref} from '../lib/development-channels';

test('Five dedicated channel destinations, with entrepreneurship kept separate',()=>{
  assert.equal(developmentChannels.length,5);
  for(const channel of developmentChannels){
    assert.equal(channelHref(channel.code),'/channels/'+channel.code);
    assert.equal(getChannel(channel.code),channel);
    assert.equal(currentChannel(channelHref(channel.code),new URLSearchParams())?.code,channel.code);
  }
  assert.equal(channelHref('entrepreneurship'),'/entrepreneurship');
  assert.equal(channelHref('unknown'),'/data');
  assert.equal(channelHref('//evil.example'),'/data');
});

test('Preserved filters cannot replace the route-selected channel',()=>{
  const url=new URL(catalogHref('employment',{
    path:'overseas_study',q:'研发 & 实习',offset:'12',status:'active',kind:'reference',
    sort:'deadline',school:'中山大学',year:'2027',region:'CN-GD',
  }),'http://localhost');
  assert.equal(url.pathname,'/channels/employment');
  assert.equal(url.searchParams.has('path'),false);
  assert.equal(url.searchParams.get('q'),'研发 & 实习');
  assert.equal(url.searchParams.get('offset'),'12');
  assert.equal(url.searchParams.get('year'),'2027');
  assert.equal(url.searchParams.get('sort'),'deadline');
  assert.equal(url.searchParams.get('school'),'中山大学');
});

test('Sidebar resolves dedicated routes and legacy/detail context, not unrelated pages',()=>{
  const params=new URLSearchParams({path:'overseas_study',channel:'employment'});
  assert.equal(currentChannel('/channels/recommendation_exemption',params)?.code,'recommendation_exemption');
  assert.equal(currentChannel('/data',params)?.code,'overseas_study');
  assert.equal(currentChannel('/data/publication-1',params)?.code,'employment');
  assert.equal(currentChannel('/data/timeline',params),undefined);
  assert.equal(currentChannel('/agent',params),undefined);
  assert.equal(currentChannel('/channels/unknown',params),undefined);
  assert.equal(currentChannel('/data',new URLSearchParams()),undefined);
});

test('Details carry only validated channel context and encode publication/item IDs',()=>{
  const url=new URL(noticeHref('pub/1','item & 1','employment'),'http://localhost');
  assert.equal(url.pathname,'/data/pub%2F1');
  assert.equal(url.searchParams.get('item'),'item & 1');
  assert.equal(url.searchParams.get('channel'),'employment');
  assert.equal(noticeHref('pub','item','//evil.example'),'/data/pub?item=item');
  assert.equal(noticeHref('pub'),'/data/pub');
});

test('Aggregate and legacy entrepreneurship browsing remain available',()=>{
  assert.equal(catalogHref(undefined,{}),'/data');
  assert.equal(catalogHref(undefined,{path:'entrepreneurship'}),'/data?path=entrepreneurship');
  assert.equal(catalogHref('employment',{q:'',offset:'0'}),'/channels/employment?offset=0');
});
