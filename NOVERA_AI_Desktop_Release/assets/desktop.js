'use strict';
const $=id=>document.getElementById(id);let api,history=[],current=[],activeId=null,busy=false,activeAnswer=null,account=null,providers={},authPolling=false;
function notice(text){$('notice').textContent=text;$('notice').hidden=false;setTimeout(()=>$('notice').hidden=true,6500)}
function show(id){if(!account||(['developer','logs'].includes(id)&&account.role!=='developer'))return;for(const el of document.querySelectorAll('.pane'))el.hidden=el.id!==id;if(id==='logs')refreshLogs()}
function message(role,text){const el=document.createElement('article');el.className='message '+role;const name=document.createElement('b');name.textContent=role==='user'?'나':'VIONA';const content=document.createElement('span');content.textContent=text;el.append(name,content);$('messages').append(el);if(role==='assistant')htmlExport(content,text);return content}
function render(){const log=$('messages');log.replaceChildren();for(const m of current)message(m.role,m.content);listHistory()}
function listHistory(){const nav=$('history');nav.replaceChildren();for(const h of history){const b=document.createElement('button');b.textContent=h.title;b.onclick=()=>{if(busy)return;activeId=h.id;current=structuredClone(h.messages);render();show('chat')};nav.append(b)}}
async function persist(){if(!current.length)return;if(!activeId)activeId=crypto.randomUUID();const row={id:activeId,title:current.find(m=>m.role==='user')?.content.slice(0,45)||'대화',messages:current};history=[row,...history.filter(h=>h.id!==activeId)].slice(0,100);await api.save_history(history);listHistory()}
function lock(value){busy=value;$('send').disabled=value;$('generate').disabled=value;$('saveSettings').disabled=value;$('addModel').disabled=value;$('syncWeb').disabled=value;$('logout').disabled=value}
window.addEventListener('novera',e=>{const d=e.detail;if(d.kind==='token'&&activeAnswer){activeAnswer.textContent+=d.text;$('messages').scrollTop=$('messages').scrollHeight}if(d.kind==='replace'&&activeAnswer)activeAnswer.textContent=d.text;if(d.kind==='phase')$('phase').textContent=d.text});
$('chatForm').onsubmit=async e=>{e.preventDefault();if(!api||busy)return;const text=$('prompt').value.trim();if(!text)return;show('chat');if(!current.length)$('messages').replaceChildren();current.push({role:'user',content:text});message('user',text);$('prompt').value='';activeAnswer=message('assistant','');activeAnswer.innerHTML='<span class="working">처리 중 <i></i><i></i><i></i></span>';lock(true);let first=true;const tokenListener=e=>{if(e.detail.kind==='token'&&first){const text=e.detail.text;activeAnswer.textContent=text;first=false}};window.addEventListener('novera',tokenListener);try{const r=await api.chat(current,1024);if(r.error){activeAnswer.textContent=r.error;notice(r.error)}else{activeAnswer.textContent=r.text;htmlExport(activeAnswer,r.text);current.push({role:'assistant',content:r.text});await persist();if(r.code_checks?.issues?.length)notice('정적 검사 주의: '+r.code_checks.issues.join(' / '))}}finally{window.removeEventListener('novera',tokenListener);activeAnswer=null;lock(false)}};
$('prompt').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();$('chatForm').requestSubmit()}};
$('newChat').onclick=()=>{if(busy)return;current=[];activeId=null;render();show('chat');$('prompt').focus()};
document.querySelectorAll('[data-pane]').forEach(b=>b.onclick=()=>show(b.dataset.pane));
document.querySelectorAll('[data-prompt]').forEach(b=>b.onclick=()=>{$('prompt').value=b.dataset.prompt;$('prompt').focus()});
$('cancel').onclick=async()=>{if(api)await api.cancel()};
$('saveSettings').onclick=async()=>{if(!account)return;const v={mode:$('mode').value,threads:Number($('threads').value),context:Number($('context').value)};if(account.role==='developer'){for(const k of ['model','adapter','image_model'])v[k]=$(k).value;v.strength=Number($('strength').value);v.text_lora=$('text_lora').checked;v.follow_web=$('follow_web').checked;}const r=await api.configure(v);notice(r.error||'설정을 저장했습니다. 다음 요청에서 모델을 로드합니다.')};
$('generate').onclick=async()=>{if(busy)return;const p=$('imagePrompt').value.trim();if(!p)return notice('이미지 설명을 입력해 주세요.');lock(true);$('imageResult').textContent='이미지를 생성하고 있습니다…';try{const r=await api.image(p,12,42);if(r.error)$('imageResult').textContent=r.error;else{const im=document.createElement('img');im.src=r.image;im.alt=p;const caption=document.createElement('p');caption.className='muted';caption.textContent=(r.adapter_applied?'LoRA 로딩·적용 로그 확인':'LoRA 적용 확인 없음')+' · '+r.backend+' · '+r.file;$('imageResult').replaceChildren(im,caption)}}finally{lock(false)}};
async function refreshLogs(){if(api)$('logText').textContent=await api.logs()}
$('refreshLogs').onclick=refreshLogs;$('addModel').onclick=async()=>{const r=await api.add_model();if(r.error)notice(r.error);else if(r.ok){const o=document.createElement('option');o.value=r.model.id;o.textContent=r.model.name;$('model').append(o);notice('모델을 추가했습니다. 목록에서 선택하고 저장해 주세요.')}};
$('exportHistory').onclick=()=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(history,null,2)],{type:'application/json'}));a.download='NOVERA-conversations.json';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)};
$('importHistory').onchange=async e=>{try{const rows=JSON.parse(await e.target.files[0].text());if(!Array.isArray(rows)||rows.some(r=>!r.id||!Array.isArray(r.messages)||r.messages.some(m=>!['user','assistant'].includes(m.role)||typeof m.content!=='string')))throw Error('대화 기록 형식이 올바르지 않습니다.');const merged=new Map([...history,...rows].map(h=>[h.id,h]));history=[...merged.values()].slice(0,100);const result=await api.save_history(history);if(result.error)throw Error(result.error);listHistory();notice('대화를 불러왔습니다.')}catch(e){notice(e.message)}};
function populate(d){$('updateStatus').textContent='앱 '+d.app_version+' · 시작 시 자동 업데이트';history=d.history;listHistory();$('model').replaceChildren();$('image_model').replaceChildren();$('adapter').replaceChildren(new Option('사용 안 함',''));$('webRelease').textContent=d.web_release?'연결된 배포: '+d.web_release.name:'웹 배포 미연결 · 로컬 모델 사용';for(const m of d.models.filter(m=>m.kind==='image'))$('image_model').append(new Option(m.name,m.id));for(const m of d.models.filter(m=>m.kind==='text')){const o=document.createElement('option');o.value=m.id;o.textContent=m.name;$('model').append(o)}for(const a of d.adapters){const o=document.createElement('option');o.value=a.id;o.textContent=a.name;$('adapter').append(o)}for(const [k,v] of Object.entries(d.settings)){if($(k)){if(typeof v==='boolean')$(k).checked=v;else $(k).value=v}}}
$('syncWeb').onclick=async()=>{if(!api||busy)return;lock(true);try{const r=await api.sync_web();if(r.error)notice(r.error);else{populate(r.bootstrap);notice('웹 배포 모델을 연결했습니다. 다음 요청에서 로드합니다.')}}finally{lock(false)}};
for(const id of ['model','adapter','image_model','strength','text_lora','follow_web'])$(id)?.closest('label')?.setAttribute('data-developer','');
for(const id of ['addModel','syncWeb'])$(id)?.setAttribute('data-developer','');
function providerState(state){
 providers=state.providers||{};const pending=Boolean(state.pending_provider);
 for(const name of ['google','naver'])$(name+'Login').disabled=pending||!providers[name]?.configured;
 $('cancelLogin').hidden=!pending;
 $('providerSetupNote').textContent=pending?'기본 브라우저에서 인증을 마친 뒤 앱으로 돌아와 주세요.':Object.values(providers).some(p=>!p.configured)?'설정되지 않은 로그인은 개발자 계정에서 서비스 연결이 필요합니다.':'공식 로그인 화면을 기본 브라우저에서 엽니다.';
 if(state.error)$('authMessage').textContent=state.error;
}
async function enterWorkspace(){
 const data=await api.bootstrap();if(!data.authenticated)return;account=data.user;providers=data.providers||{};
 history=[];current=[];activeId=null;render();populate(data);
 document.body.classList.remove('signed-out');$('authScreen').hidden=true;
 $('accountName').textContent=account.login+(account.role==='developer'?' · 개발자':'');
 for(const el of document.querySelectorAll('[data-developer]'))el.hidden=account.role!=='developer';
 $('developerPassword').value='';$('authMessage').textContent='';show('chat');updateOAuthForm();
}
async function checkAuth(){if(!api||authPolling)return;authPolling=true;try{const state=await api.auth_status();providerState(state);if(state.authenticated&&state.user?.id!==account?.id)await enterWorkspace();}catch(e){$('authMessage').textContent='로그인 상태를 확인하지 못했습니다. 앱을 다시 실행해 주세요.';}finally{authPolling=false;}}
for(const name of ['google','naver'])$(name+'Login').onclick=async()=>{const result=await api.begin_social(name);$('authMessage').textContent=result.error||result.notice||'';await checkAuth();};
$('cancelLogin').onclick=async()=>{await api.cancel_login();$('authMessage').textContent='로그인을 취소했습니다.';await checkAuth();};
$('developerLoginForm').onsubmit=async event=>{event.preventDefault();if(!api)return;$('developerSignIn').disabled=true;try{const result=await api.login($('developerUsername').value,$('developerPassword').value);$('developerPassword').value='';if(result.error)$('authMessage').textContent=result.error;else await enterWorkspace();}catch(e){$('authMessage').textContent='로그인을 처리하지 못했습니다. 다시 시도하세요.';}finally{$('developerSignIn').disabled=false;}};
$('logout').onclick=async()=>{await api.logout();account=null;history=[];current=[];activeId=null;activeAnswer=null;render();$('imageResult').replaceChildren();$('logText').textContent='';$('resources').textContent='';$('oauthClientSecret').value='';document.body.classList.add('signed-out');$('authScreen').hidden=false;await checkAuth();};
function updateOAuthForm(){const name=$('oauthProvider').value;$('oauthClientId').value=providers[name]?.client_id||'';$('oauthClientSecret').value='';$('oauthCallback').textContent=name==='google'?'Google OAuth 클라이언트 유형: 데스크톱 앱. 임시 로컬 콜백 포트를 사용합니다.':'네이버 Callback URL: http://127.0.0.1:43871/oauth/callback/naver';}
$('oauthProvider').onchange=updateOAuthForm;
$('oauthSettingsForm').onsubmit=async event=>{event.preventDefault();$('saveOAuthSettings').disabled=true;try{const result=await api.configure_login($('oauthProvider').value,$('oauthClientId').value,$('oauthClientSecret').value);$('oauthClientSecret').value='';$('oauthSettingsMessage').textContent=result.error||'연결 설정을 저장했습니다. 로그아웃 후 실제 계정 로그인을 확인하세요.';if(result.providers)providers=result.providers;}finally{$('saveOAuthSettings').disabled=false;}};
window.addEventListener('pywebviewready',async()=>{api=window.pywebview.api;await checkAuth();setInterval(checkAuth,1500);
async function update(){if(!account)return;try{const s=await api.status();$('phase').textContent=s.phase;$('light').classList.toggle('ready',s.ready);$('resources').textContent=`RAM 여유 ${s.free_gib}GiB / 사용 ${s.used_gib}GiB\n${s.gpu.name} · 여유 VRAM ${s.gpu.free_mib}MiB\n${s.loaded?.text_adapter_loaded?'대화 LoRA 로딩 확인':'대화 모델 대기 / LoRA 적용 미확인'}${s.error?'\n'+s.error:''}`}catch(e){$('phase').textContent='연결 확인 필요'}}await update();setInterval(update,5000)});

function htmlExport(content,text){
 if(!/```html\s|<!doctype html|<html\b/i.test(text)||content.parentElement.querySelector('.html-export'))return;
 const button=document.createElement('button');button.className='html-export';button.textContent='HTML 파일 저장';button.style.marginTop='12px';button.style.display='block';
 button.onclick=async()=>{button.disabled=true;try{const r=await api.export_html(text);if(r.error)return notice(r.error);const url=URL.createObjectURL(new Blob([r.html],{type:'text/html;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=r.filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),3000);notice('HTML 저장 완료: '+r.file);}finally{button.disabled=false}};
 content.parentElement.append(button);
}

$('checkUpdates').onclick=async()=>{const button=$('checkUpdates');button.disabled=true;try{const r=await api.check_updates();$('updateStatus').textContent=(r.current_version?'앱 '+r.current_version+' · ':'')+(r.available?'새 버전 '+r.version+' · 앱을 다시 시작하면 자동 적용합니다.':r.status||r.error||'확인 완료');}finally{button.disabled=false}};

function authMode(register){
 $('registerForm').hidden=!register;$('developerLoginForm').hidden=register;
 $('showRegister').setAttribute('aria-pressed',String(register));$('showLogin').setAttribute('aria-pressed',String(!register));
 $('developerPassword').value='';$('registerPassword').value='';$('registerConfirm').value='';$('authMessage').textContent='';
}
$('showLogin').onclick=()=>authMode(false);
$('showRegister').onclick=()=>authMode(true);
$('registerForm').onsubmit=async event=>{
 event.preventDefault();if(!api)return;
 if($('registerPassword').value!==$('registerConfirm').value){$('authMessage').textContent='비밀번호 확인이 일치하지 않습니다.';return;}
 $('registerSubmit').disabled=true;
 try{
  const username=$('registerUsername').value;
  const result=await api.register(username,$('registerPassword').value,$('registerConfirm').value);
  $('registerPassword').value='';$('registerConfirm').value='';
  if(result.error)$('authMessage').textContent=result.error;
  else{authMode(false);$('developerUsername').value=username.trim().toLowerCase();$('authMessage').textContent='회원가입이 완료됐습니다. 로그인해 주세요.';}
 }catch(e){$('authMessage').textContent='회원가입을 처리하지 못했습니다. 다시 시도하세요.';}
 finally{$('registerSubmit').disabled=false;}
};
