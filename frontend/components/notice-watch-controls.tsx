'use client';
import {useState} from 'react';
import {useRouter} from 'next/navigation';

export function NoticeWatchControls({id,enabled}:{id:string;enabled:boolean}){
 const [busy,setBusy]=useState(false),[message,setMessage]=useState('');
 const router=useRouter();
 async function run(rescan:boolean){
  setBusy(true);setMessage('');
  try{
   const r=await fetch('/api/backend/v1/admin/notice-watch/'+id+(rescan?'/rescan':''),{
    method:rescan?'POST':'PATCH',headers:{'Content-Type':'application/json'},
    ...(rescan?{}:{body:JSON.stringify({enabled:!enabled})})});
   const data=await r.json();if(!r.ok)throw Error(data.detail||'操作失败');
   setMessage(rescan?'已加入队列，后台将检查栏目':enabled?'已暂停':'已恢复');router.refresh();
  }catch(e){setMessage((e as Error).message)}finally{setBusy(false)}
 }
 return <div className="actions"><button disabled={busy} onClick={()=>run(false)}>{enabled?'暂停':'恢复'}</button>{enabled&&<button disabled={busy} onClick={()=>run(true)}>检查栏目</button>}<span role="status">{message}</span></div>
}
