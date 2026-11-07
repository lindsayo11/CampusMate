'use client';
import {useEffect,useMemo,useState} from 'react';
import Link from 'next/link';

type Result={key:string;name:string;note:string;score:number};
const labels=[['A','考公考编','重视稳定、规则与可预期的生活节奏。'],['B','保研','偏好校园、科研与持续的专业深耕。'],['C','考研','目标感强，愿意用备考换取学历与平台。'],['D','留学','看重国际经历、独立性与多元环境。'],['E','就业','希望尽快行动，在真实项目中获得回报。'],['F','创业','愿意承担不确定性，创造自己的事业路径。']];
const questions=[
 ['你更喜欢的日常节奏是：','规律稳定，职责清晰，少变动','校园科研节奏，读书、实验、写论文','有明确目标，集中备考','多元变化，跨文化环境','项目快节奏，做出成果拿回报','自己定方向，随时应对不确定性'],
 ['面对风险，你更偏向：','尽量规避，稳定第一','在学术路径内承担可控风险','愿为更好学历承担备考风险','愿承担海外适应和经济压力','接受职场竞争，但不赌全部','高风险高回报，愿意试错'],
 ['你更享受哪种成就感：','被组织认可，服务公众','成绩优异，获导师和学校认可','考上目标院校或专业','独立完成海外学习生活','拿offer、升职加薪、经济独立','从0到1做成一个项目或公司'],
 ['对规则和流程：','喜欢明确规则，按流程做事','适应学术规范，按培养方案走','能接受应试规则，为目标准备','能适应不同制度，灵活遵守','在规则内高效完成KPI','不喜欢被束缚，想自己定规则'],
 ['理想的工作生活状态：','朝九晚五，双休稳定','校园环境，自由但科研压力大','备考期辛苦，上岸后改善','海外生活，文化体验优先','忙但回报可见，接受加班','工作即生活，全力投入'],
 ['你更喜欢的社交圈：','体制内同事、长辈认可的朋友','导师、同门、学术圈','研友、目标院校同学','国际朋友、多元文化','职场人脉、行业伙伴','创业者、投资人、合伙人'],
 ['平时最愿意花时间在：','看时政、政策、公共事务','读文献、做实验、写论文','刷题、总结考点、研究院校','学外语、看海外内容','学实用技能、实习、搞副业','研究商业模式、找机会、组队做事'],
 ['如果免费学一门课，你会选：','公共管理、法律、行政能力','本专业前沿、研究方法','考研英语/数学/专业课','雅思托福、跨文化交流','编程、数据分析、营销、证书','创业管理、融资、产品'],
 ['你对“研究”的态度：','不太想长期做，够用就行','很喜欢，愿意读研读博','可以接受，作为提升手段','愿意在海外做研究','更想解决实际问题','研究市场比研究文献更有趣'],
 ['你更喜欢哪种评价方式：','稳定考核、资历积累','绩点、论文、导师评价','考试分数、录取结果','申请材料、语言成绩、面试','绩效、KPI、薪资涨幅','用户、市场、收入验证'],
 ['对继续读书：','除非必要，不想再读','希望保研，顺其自然深造','想考研，换学校/专业/城市','想留学，获得国际经历','先工作，需要再读在职','读书不如直接干，边干边学'],
 ['你更看重的薪资形态：','不高但稳定，福利好，退休有保障','补贴+奖学金，够用，未来走学术','读研期间投入，期待毕业后涨薪','前期投入大，换长期回报或海外薪资','起薪中等，涨薪快，看能力','波动大，但上限高，可能财富自由'],
 ['你能接受前期低收入或高投入吗：','不太能，希望尽快稳定收入','能，保研成本相对较低','能，接受1—3年备考和读研','能，接受较高留学费用','希望尽快工作赚钱','能，接受创业前期无收入'],
 ['你对“成功”的定义：','稳定、体面、家庭安心','学术成就、专业深耕','学历跃迁、进入更好平台','国际视野、人生体验丰富','高薪、职位、经济独立','自己掌控事业、创造价值'],
 ['家庭对你出路的期待：','考公考编，稳定最好','保研/读博，学历越高越好','考研提升学历','留学开阔眼界或移民','找份好工作，先赚钱','支持你闯，但风险自担'],
 ['你对城市和地域的偏好：','家乡或附近体制内城市','本科城市，学术资源好','目标院校城市，愿意考过去','海外或国际化大都市','机会多的城市，跟着工作走','哪里有机会就去哪'],
 ['你的本科成绩/排名：','中等，考公更看考试','前列，有保研希望','中上，考研可冲','中上，有语言和经济条件','一般，但实习/项目多','一般，但点子多、行动力强'],
 ['你的英语/跨文化适应：','一般，国内环境更舒服','能读文献，学术英语够用','应试英语还行，考研够用','较好，愿意考雅思托福','能工作沟通即可','能谈合作，不怕和陌生人打交道'],
 ['你的经济条件：','需要尽快稳定收入','保研成本低，适合','考研成本可承受','留学费用压力不大','希望工作后经济独立','有一定启动资金或能承受失败'],
 ['如果明天必须做决定，你会：','报名考公考编','准备保研材料','买考研资料','查留学项目','改简历投递','写商业计划、找合伙人'],
];

export default function TestClient({authenticated}:{authenticated:boolean}){
 const [answers,setAnswers]=useState<string[]>([]);
 const [submitted,setSubmitted]=useState(false);
 useEffect(()=>{try{const saved=sessionStorage.getItem('campusmate-test-answers');if(saved){const value=JSON.parse(saved);if(Array.isArray(value))setAnswers(value)}}catch{}if(new URLSearchParams(window.location.search).get('result')==='1')setSubmitted(true)},[]);
 useEffect(()=>{try{sessionStorage.setItem('campusmate-test-answers',JSON.stringify(answers))}catch{}},[answers]);
 const complete=answers.length===20;
 const scores=useMemo<Result[]>(()=>labels.map(([key,name,note])=>({key,name,note,score:answers.filter(a=>a===key).length})),[answers]);
 const ranked=[...scores].sort((a,b)=>b.score-a.score);
 function choose(i:number,key:string){setAnswers(current=>{const next=[...current];next[i]=key;return next})}
 function gate(){if(!authenticated){window.location.assign('/#login');return}setSubmitted(true)}
 if(submitted)return <main className="test-page"><div className="test-frame test-results"><span className="test-kicker">YOUR RESULT</span><h1>{ranked[0].name}</h1><p className="result-score">{ranked[0].score} / 20 · 主倾向</p><p>{ranked[0].note}</p><div className="result-secondary"><h2>辅助倾向 · {ranked[1].name}</h2><p>{ranked[1].score} / 20 · {ranked[1].note}</p></div><div className="score-list">{ranked.map(item=><div key={item.key}><span>{item.name}</span><span>{item.score}</span></div>)}</div><a className="test-button test-button-primary" href="/console">开始探索</a></div></main>;
 return <main className="test-page"><div className="test-frame"><div className="test-top"><Link href="/" className="test-brand">CampusMate</Link><span>{answers.length} / 20</span></div><div className="test-intro"><span className="test-kicker">SELF EXPLORATION</span><h1>六条出路倾向测试</h1><p>每题选择一个最符合你的选项。</p></div><div className="test-progress"><span style={{width:`${answers.length/20*100}%`}}/></div><div className="test-questions">{questions.map((question,i)=><fieldset key={question[0]} className="test-question"><legend><span>{String(i+1).padStart(2,'0')}</span>{question[0]}</legend><div className="test-options">{question.slice(1).map((text,j)=>{const key='ABCDEF'[j];return <label key={key} className={answers[i]===key?'selected':''}><input type="radio" name={`q-${i}`} checked={answers[i]===key} onChange={()=>choose(i,key)}/><b>{key}</b><span>{text}</span></label>})}</div></fieldset>)}</div><button className="test-button test-submit" disabled={!complete} onClick={gate}>查看结果</button></div></main>;
}
