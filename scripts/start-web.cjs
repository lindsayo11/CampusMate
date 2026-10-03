// Start the same standalone server layout as the Docker image.
const fs=require('node:fs');
const path=require('node:path');
const frontend=path.resolve(__dirname,'../frontend');
const output=path.join(frontend,'.next/standalone');
if(!fs.existsSync(path.join(output,'server.js'))){console.error('Run npm run build in frontend first.');process.exit(1)}
fs.cpSync(path.join(frontend,'.next/static'),path.join(output,'.next/static'),{recursive:true});
if(fs.existsSync(path.join(frontend,'public')))fs.cpSync(path.join(frontend,'public'),path.join(output,'public'),{recursive:true});
process.env.HOSTNAME=process.env.WEB_HOST||'127.0.0.1';
require(path.join(output,'server.js'));
