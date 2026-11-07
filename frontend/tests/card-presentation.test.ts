import test from 'node:test';
import assert from 'node:assert/strict';
import {pageNumbers} from '../lib/pagination';
import {artworkRecipe,artworkTheme} from '../lib/notice-artwork';

test('Pagination shows all nine pages, with bounded windows for large catalogues',()=>{
  assert.deepEqual(pageNumbers(1,9),[1,2,3,4,5,6,7,8,9]);
  assert.deepEqual(pageNumbers(1,20),[1,2,3,4,5,6,'ellipsis',20]);
  assert.deepEqual(pageNumbers(10,20),[1,'ellipsis',8,9,10,11,12,'ellipsis',20]);
  assert.deepEqual(pageNumbers(20,20),[1,'ellipsis',15,16,17,18,19,20]);
  assert.deepEqual(pageNumbers(1,0),[]);
  assert.deepEqual(pageNumbers(9,1),[1]);
  assert.deepEqual(pageNumbers(NaN,Infinity),[]);
});
test('Every record gets a stable artwork recipe, including same-title records',()=>{
  const paths=[{code:'recommendation_exemption'}];
  assert.deepEqual(artworkRecipe('notice-1','招生公告',paths),artworkRecipe('notice-1','招生公告',paths));
  const recipes=Array.from({length:200},(_,i)=>artworkRecipe('notice-'+i,'招生公告',paths));
  assert.equal(new Set(recipes.map(r=>r.signature)).size,200);
  assert.equal(new Set(recipes.map(r=>JSON.stringify(r))).size,200);
  assert.equal(new Set(recipes.map(r=>r.variant)).size,3);
  assert.equal(new Set(recipes.map(r=>r.composition)).size,4);
  assert.notDeepEqual(recipes[0],recipes[1]);
});
test('Topics select relevant original scenes, not a recycled technical diagram',()=>{
  assert.equal(artworkTheme([],'全国数学建模竞赛'),'competition');
  assert.equal(artworkTheme([],'大学生创业扶持'),'venture');
  assert.equal(artworkTheme([],'推免通知'),'academic');
  assert.equal(artworkTheme([{code:'national_civil_service'}],''),'public');
  assert.equal(artworkTheme([{code:'domestic_postgraduate_exam'}],''),'study');
  assert.equal(artworkTheme([{code:'overseas_study'}],''),'overseas');
  assert.equal(artworkTheme([{code:'employment'}],''),'career');
});
