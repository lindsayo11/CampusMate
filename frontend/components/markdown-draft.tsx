/** Safe, small Markdown reader: all content stays React text, never raw HTML. */
export function MarkdownDraft({text}:{text:string}){
 const blocks=text.split(/\n\s*\n/);
 return <article className="startup-draft" aria-label="创业文稿预览">{blocks.map((block,index)=>{
  if(block.startsWith('# '))return <h3 key={index}>{block.slice(2)}</h3>;
  if(block.startsWith('## '))return <h4 key={index}>{block.slice(3)}</h4>;
  if(block.split('\n').every(line=>line.startsWith('- ')))return <ul key={index}>{block.split('\n').map((line,i)=><li key={i}>{line.slice(2)}</li>)}</ul>;
  return <p key={index} style={{whiteSpace:'pre-wrap'}}>{block.replace(/\*\*/g,'')}</p>
 })}</article>
}
