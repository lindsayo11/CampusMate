const {chromium}=require('../frontend/node_modules/playwright');
const fs=require('fs');
const path=require('path');
(async()=>{
 const out=path.join(__dirname,'../artifacts/ui');fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH,args:['--no-sandbox','--disable-dev-shm-usage','--disable-gpu']});
 const page=await browser.newPage({viewport:{width:1440,height:1000},deviceScaleFactor:1});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 for(const [route,name] of [['/','workspace-desktop'],['/data?status=all','information-desktop'],['/tracker','plans-desktop'],['/agent','agent-desktop'],['/teams','conversations-desktop'],['/admin','admin-desktop']]){
  await page.goto('http://127.0.0.1:3033'+route);await page.waitForLoadState('networkidle');
  await page.screenshot({path:path.join(out,name+'.png'),fullPage:true});
 }
 await page.goto('http://127.0.0.1:3034/');await page.waitForLoadState('networkidle');await page.screenshot({path:path.join(out,'student-desktop.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});await page.goto('http://127.0.0.1:3034/');await page.waitForLoadState('networkidle');await page.screenshot({path:path.join(out,'workspace-mobile.png'),fullPage:true});
 await page.getByRole('button',{name:'展开导航'}).click();await page.screenshot({path:path.join(out,'navigation-mobile.png')});
 console.log(JSON.stringify({screenshots:9,browserErrors:errors}));
 await browser.close();if(errors.length)process.exitCode=1;
})().catch(e=>{console.error(e);process.exit(1)});
