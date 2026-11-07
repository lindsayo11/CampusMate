// Start the same standalone server layout as the Docker image.
const fs=require('node:fs');
const path=require('node:path');
const frontend=path.resolve(__dirname,'../frontend');
const standalone=path.join(frontend,'.next/standalone');
const nested=path.join(standalone,'frontend');
const output=fs.existsSync(path.join(standalone,'server.js'))?standalone:fs.existsSync(path.join(nested,'server.js'))?nested:null;
if(!output){console.error('Run npm run build in frontend first.');process.exit(1)}
const staticTarget=path.join(output,'.next/static');
fs.cpSync(path.join(frontend,'.next/static'),staticTarget,{recursive:true});
if(fs.existsSync(path.join(frontend,'public'))){const publicTarget=path.join(output,'public');fs.cpSync(path.join(frontend,'public'),publicTarget,{recursive:true});}
process.env.HOSTNAME=process.env.WEB_HOST||'127.0.0.1';
require(path.join(output,'server.js'));
