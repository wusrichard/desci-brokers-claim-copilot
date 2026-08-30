const accounts = [
  {email:'mai@demo.tw', name:'阮氏梅 Nguyen Thi Mai', role:'移工本人', tone:'本人'},
  {email:'meiling@hongtai.tw', name:'陳美玲', role:'仲介承辦人 · ECR 有效', tone:'有效'},
  {email:'zhihao@hongtai.tw', name:'林志豪', role:'前承辦人 · ECR 已撤銷', tone:'撤銷'},
  {email:'taka@jinghong.tw', name:'Taka', role:'雇主 · Migrant Worker Manager', tone:'雇主'},
];
const workflow = [
  ['01','Verify','驗證身份與聘僱關係','verify_employment',{}],
  ['02','Understand','母語事故描述結構化','understand_incident',{lang:'vi'}],
  ['03','Match','理解保障與可申請項目','match_coverage',{}],
  ['04','Claim','列出尚缺文件','list_missing_documents',{}],
  ['05','Track','查看案件進度','track_status',{}],
  ['06','Record','建立保護紀錄','build_protection_record',{}],
];
localStorage.removeItem('claim_token'); // 清除舊版曾使用的 JS 可讀 bearer token
const state={csrf:csrfFromCookie(),user:null,caseId:'',case:null,status:null};
const $=s=>document.querySelector(s); const $$=s=>[...document.querySelectorAll(s)];

function csrfFromCookie(){const row=document.cookie.split('; ').find(v=>v.startsWith('csrf_token='));return row?decodeURIComponent(row.split('=').slice(1).join('=')):''}
function toast(message){const el=$('#toast');el.textContent=message;el.classList.add('show');setTimeout(()=>el.classList.remove('show'),2600)}
async function api(path,options={}){
  const headers={'content-type':'application/json',...(options.headers||{})};
  const method=(options.method||'GET').toUpperCase();
  if(['POST','PUT','PATCH','DELETE'].includes(method)&&state.csrf)headers['x-csrf-token']=state.csrf;
  const res=await fetch(path,{...options,headers,credentials:'same-origin'});
  let data={};try{data=await res.json()}catch(_){data={detail:`HTTP ${res.status}`}}
  if(!res.ok)throw new Error(data.detail||`HTTP ${res.status}`);return data;
}
function renderAccounts(){
  $('#demo-accounts').innerHTML=accounts.map(a=>`<button class="account-button" data-email="${a.email}"><span><strong>${a.name}</strong><small>${a.role}</small></span><b>${a.tone} →</b></button>`).join('');
  $$('.account-button').forEach(b=>b.onclick=()=>login(b.dataset.email));
}
async function login(email){
  try{const data=await api('/login',{method:'POST',body:JSON.stringify({email,password:'demo1234'})});state.csrf=data.csrf_token||csrfFromCookie();state.user=data.user;await enterApp();}
  catch(err){toast(`登入失敗：${err.message}`)}
}
async function enterApp(){
  try{
    state.user=state.user||await api('/me');state.status=await api('/api/status');
    const cases=await api('/cases');
    $('#login-view').classList.add('hidden');$('#app-view').classList.remove('hidden');
    $('#user-chip').textContent=state.user.display_name;
    $('#verifier-badge').textContent=state.status.verifier==='vlei-sandbox'?'vLEI sandbox ✓':'Mock verifier';
    if(state.status.verifier==='unavailable')$('#verifier-badge').textContent='Verifier unavailable · fail closed';
    $('#tamper-audit').classList.toggle('hidden',!state.status.tamper_demo_enabled);
    const select=$('#case-select');select.innerHTML=cases.length?cases.map(c=>`<option value="${c.case_id}">${c.case_id}</option>`).join(''):'<option>沒有案件</option>';
    configureRoleView();
    if(cases.length){state.caseId=cases[0].case_id;select.value=state.caseId;await loadCase();}
  }catch(err){logout(false);toast(`工作階段失效：${err.message}`)}
}
async function loadCase(){
  try{state.case=await api(`/cases/${state.caseId}`);$('#case-kicker').textContent=`案件 ${state.case.case_id}`;$('#case-title').textContent=state.case.title;renderPrincipal();renderWorkflow();if(state.user.role==='employer_officer')renderEmployerPortal();else await loadAudit();}
  catch(err){$('#case-title').textContent='無法存取案件';toast(err.message)}
}
function renderPrincipal(){
  const a=state.case.acting_as,g=state.case.grant;const who=a.acting_for?`${a.display_name}（代表 ${a.acting_for}）`:a.display_name;
  $('#principal-banner').innerHTML=`<div><span class="step-label">AGENT CURRENTLY REPRESENTS</span><br><strong>${who}</strong></div><div>${g?`目的：${g.purpose}<br><small>Scopes：${g.scopes.join(' · ')}</small>`:'<strong>本案件尚無授權</strong>'}</div>`;
  $('#active-said').textContent=accounts[1].email===state.user.email?(a.role_credential||'—'):'FDqiCq4…RNA6';
  $('#revoked-said').textContent=accounts[2].email===state.user.email?(a.role_credential||'—'):'FKZrCrQ…q1Mk';
}
function configureRoleView(){
  const employer=state.user&&state.user.role==='employer_officer';
  $('#employer-nav').classList.toggle('hidden',!employer);
  $$('.standard-nav').forEach(n=>n.classList.toggle('hidden',employer));
  switchTab(employer?'employer':'workflow');
}
function renderEmployerPortal(){
  $('#employer-lei').textContent=state.user.org_lei||'—';
  $('#employer-said').textContent=state.user.role_credential||'—';
  const caps=new Map((state.case.capabilities||[]).map(c=>[c.name,c]));
  $$('.employer-action').forEach(b=>{const c=caps.get(b.dataset.tool);b.disabled=!state.case.grant||!c||!c.in_scope;});
}
function renderWorkflow(){
  const caps=new Map((state.case.capabilities||[]).map(c=>[c.name,c]));
  $('#workflow-grid').innerHTML=workflow.map(w=>{const c=caps.get(w[3]);const disabled=!state.case.grant;return `<button class="workflow-card" data-tool="${w[3]}" ${disabled?'disabled':''}><span class="number">${w[0]}</span><h4>${w[1]}</h4><p>${w[2]}</p>${c&&!c.in_scope?'<span class="status-pill no">超出 scope</span>':''}</button>`}).join('');
  $$('#workflow-grid .workflow-card').forEach((b,i)=>b.onclick=()=>act(b.dataset.tool,workflow[i][4]));
  $('#submit-claim').disabled=!state.case.grant;
}
async function act(tool,args={},confirmed=false,target='#action-result'){
  try{const r=await api(`/cases/${state.caseId}/act`,{method:'POST',body:JSON.stringify({tool,args,confirmed})});showResult(r,target);if(state.user.role!=='employer_officer')await loadAudit();if(r.code==='NEEDS_HUMAN_CONFIRMATION')$('#confirm-dialog').showModal();return r;}
  catch(err){showResult({allowed:false,code:'REQUEST_FAILED',reason:err.message},target);}
}
function showResult(r,target='#action-result'){
  // 引用出處另外渲染——埋在 JSON 裡沒人會讀，而「有來源」正是要展示的東西
  const cites=(r.value&&r.value.citations)||[];
  const citeHtml=cites.length?`<div class="citations"><h5>引用出處　<em>${escapeHtml((r.value&&r.value.citation_source)||'')}</em></h5>${
    cites.map(c=>`<div class="cite"><strong>${escapeHtml(c.source||'')}</strong><span>${
      c.effective?`施行 ${escapeHtml(c.effective)}　`:''}知識庫 ${escapeHtml(c.kb_version||'')}　sha ${escapeHtml(c.kb_sha256||'')}</span></div>`).join('')
  }<p class="cite-note">本地知識庫，離線可重現；sha256 可重算比對。</p></div>`:'';
  // citations 已單獨呈現，JSON 區塊就不再重複
  const shown=r.value?Object.fromEntries(Object.entries(r.value).filter(([k])=>k!=='citations'&&k!=='citation_source')):null;
  const value=shown&&Object.keys(shown).length?`<pre>${escapeHtml(JSON.stringify(shown,null,2))}</pre>`:'';
  const fixture=r.fixture_note?`<p><small>資料來源：${escapeHtml(r.fixture_note)}</small></p>`:'';
  $(target).innerHTML=`<div class="result-box ${r.allowed?'':'blocked'}"><h4>${r.allowed?'✓ 已允許':'✕ 已阻擋'} · ${escapeHtml(r.code||'')}</h4><p>${escapeHtml(r.reason||'')}</p>${citeHtml}${value}${fixture}</div>`;
  // 結果印在摺線以下，點完看似沒反應——捲過去，錄影時張力才不會斷
  $(target).scrollIntoView({behavior:'smooth',block:'nearest'});
}
async function loadAudit(){
  if(!state.caseId)return;try{const d=await api(`/cases/${state.caseId}/audit`);const v=d.verify;$('#audit-summary').innerHTML=`<div class="${v.ok?'audit-pass':'audit-fail'}">${v.ok?'✓':'✕'} ${escapeHtml(v.message)}</div>`;$('#audit-body').innerHTML=d.entries.map(e=>`<tr><td>${e.seq}</td><td>${e.ts.slice(11,19)}</td><td>${escapeHtml(e.principal)}</td><td>${escapeHtml(e.tool)}</td><td class="${e.allowed?'decision-ok':'decision-no'}">${escapeHtml(e.code)}</td><td><code>${e.hash.slice(0,12)}…</code></td></tr>`).join('')||'<tr><td colspan="6">尚無紀錄</td></tr>';}
  catch(err){$('#audit-summary').innerHTML=`<div class="audit-fail">${escapeHtml(err.message)}</div>`;$('#audit-body').innerHTML='';}
}
function switchTab(name){$$('.nav-item').forEach(n=>n.classList.toggle('active',n.dataset.tab===name));$$('.tab-panel').forEach(p=>p.classList.add('hidden'));$(`#${name}-tab`).classList.remove('hidden');if(name==='audit')loadAudit();}
async function logout(notifyServer=true){
  if(notifyServer){try{await api('/logout',{method:'POST',body:'{}'})}catch(_){}}
  state.csrf='';state.user=null;state.case=null;$('#app-view').classList.add('hidden');$('#login-view').classList.remove('hidden');
}
function escapeHtml(v){return String(v).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}

renderAccounts();$$('.nav-item').forEach(n=>n.onclick=()=>switchTab(n.dataset.tab));
$('#logout').onclick=()=>logout(true);$('#case-select').onchange=async e=>{state.caseId=e.target.value;await loadCase()};
$('#clear-result').onclick=()=>$('#action-result').innerHTML='<div class="empty-state">選擇上方任一步驟開始。</div>';
$('#clear-employer-result').onclick=()=>$('#employer-action-result').innerHTML='<div class="empty-state">選擇上方一項公司任務開始。</div>';
$$('.employer-action').forEach(b=>b.onclick=()=>act(b.dataset.tool,{case_id:state.caseId},false,'#employer-action-result'));
$('#submit-claim').onclick=()=>act('submit_claim');$('#confirm-submit').onclick=()=>setTimeout(()=>act('submit_claim',{},true),0);
$('#verify-audit').onclick=async()=>{try{const r=await api(`/cases/${state.caseId}/audit/verify`,{method:'POST'});toast(r.message);await loadAudit()}catch(e){toast(e.message)}};
$('#tamper-audit').onclick=async()=>{try{const a=await api(`/cases/${state.caseId}/audit`);const target=a.entries.find(e=>!e.allowed)||a.entries[0];if(!target)throw new Error('請先執行至少一個動作');await api(`/cases/${state.caseId}/audit/tamper`,{method:'POST',body:JSON.stringify({seq:target.seq,field:'code',value:'TAMPERED'})});toast(`已竄改第 ${target.seq} 筆`);await loadAudit()}catch(e){toast(e.message)}};
$$('.officer-test').forEach(b=>b.onclick=()=>login(b.dataset.email));
if(document.cookie.includes('csrf_token='))enterApp();
