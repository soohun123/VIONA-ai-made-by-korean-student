/* Existing local developer surface: practice, feedback and actual weights are separate. */
(async()=>{'use strict';
 const $=id=>document.getElementById(id);let token='',active=null,timer=null,viewId=null;
 const capability=await(await fetch('/api/capabilities')).json();
 if(capability.mode!=='developer')return;token=capability.tool_token;
 async function api(path,method='GET',body){const response=await fetch(path,{method,headers:{'Content-Type':'application/json','X-NovaBrain-Token':token},body:body?JSON.stringify(body):undefined});const data=await response.json();if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'요청 내용을 확인하세요.');return data;}
 const button=document.createElement('button');button.id='openCodingLearning';button.textContent='코딩 학습';$('openSettings').before(button);
 const dialog=document.createElement('dialog');dialog.id='codingLearningDialog';dialog.className='desktop-dialog';
 dialog.innerHTML=`<div class="dialog-heading"><h2>코딩 학습</h2><button id="closeCodingLearning" class="icon-button" aria-label="코딩 학습 닫기">×</button></div>
 <p class="help">내 PC에서 문제 풀이 → 격리 검사 → 피드백 → 실제 추가 학습을 순서대로 진행합니다. 이미지 학습 중에는 기다립니다.</p>
 <fieldset><legend>학습 파트 · 각 50문제</legend><label><input type="checkbox" name="codingPart" value="basics" checked> 기초·경계값</label><br><label><input type="checkbox" name="codingPart" value="collections" checked> 문자열·자료구조</label><br><label><input type="checkbox" name="codingPart" value="algorithms" checked> 알고리즘</label><br><label><input type="checkbox" name="codingPart" value="debugging" checked> 버그 수정</label></fieldset>
 <p class="help">파트마다 10개 유형의 5가지 변형입니다. 학습용 문제 점수이며 HumanEval이나 종합 실력 점수가 아닙니다.</p>
 <div class="media-options"><label>문제당 수정 기회 <select id="codingRepairs"><option value="0">없음</option><option value="1" selected>1회</option><option value="2">2회</option></select></label><label>가중치 학습 예산 <select id="codingTrainSeconds"><option value="300">최대 약 5분</option><option value="600" selected>최대 약 10분</option><option value="900">최대 약 15분</option></select></label></div>
 <p class="help">문제 풀이 시간은 학습 예산과 별도입니다. 시간·메모리 제한으로 모든 교재를 가중치 학습에 사용하지 못할 수 있습니다. 결과는 원본과 분리해 저장하며 적용 전 별도 점검이 필요합니다.</p>
 <div class="media-options"><button id="startCodingLearning" class="primary-button">새 문제 풀이부터 시작</button><button id="resumeCodingLearning" class="secondary-button" disabled>완료한 풀이로 추가 학습</button><button id="stopCodingLearning" class="secondary-button" disabled>중지</button><button id="refreshCodingLearning" class="secondary-button">새로고침</button></div>
 <label>학습 기록 <select id="codingLearningRun" aria-label="확인할 코딩 학습 기록"></select></label>
 <p id="codingLearningState" role="status" aria-live="polite">기록을 불러오는 중…</p><progress id="codingLearningProgress" max="200" value="0" style="width:100%" aria-label="문제 풀이 완료 수"></progress>
 <div id="codingLearningSummary" class="help"></div><div id="codingPartResults"></div><h3>최근 피드백</h3><pre id="codingCoaching" style="white-space:pre-wrap;overflow-wrap:anywhere"></pre>`;
 document.body.append(dialog);
 const phases={practice:'문제 풀이·검사 중',waiting_for_other_work:'다른 모델 작업이 끝나기를 기다리는 중',waiting_for_memory:'안전한 메모리 확보 대기 · 다른 프로그램은 종료하지 않습니다',paused:'안전 지점에서 대기 중',waiting_for_weight_setup:'가중치 학습 준비 중',weight_training:'실제 가중치 학습 중',trained_pending_review:'학습 완료 · 적용 전 점검 대기',stopped:'중지됨'};
 const names={basics:'기초·경계값',collections:'문자열·자료구조',algorithms:'알고리즘',debugging:'버그 수정'};
 async function refresh(){try{const data=await api('/api/coding-learning');
  if(!viewId)viewId=data.current?.id||data.history?.[0]?.id;
  const records=data.history||[];if(data.current&&!records.some(r=>r.id===data.current.id))records.unshift(data.current);
  $('codingLearningRun').replaceChildren(...records.map(r=>new Option(`${new Date(r.started*1000).toLocaleString()} · ${r.completed}/${r.total}문제`,r.id)));
  $('codingLearningRun').value=viewId||'';active=records.find(r=>r.id===viewId)||data.current;
  if(!active){$('codingLearningState').textContent='아직 실행한 학습이 없습니다.';$('startCodingLearning').disabled=false;$('stopCodingLearning').disabled=true;$('resumeCodingLearning').disabled=true;return;}
  const report=await api('/api/coding-learning/jobs/'+active.id);active=report;
  const error=report.error==='User cancelled learning'?'사용자가 중지한 학습입니다.':report.error;
  $('codingLearningState').textContent=`${phases[report.phase]||report.phase} · ${report.completed}/${report.total}문제${report.practice_reused?' · 기존 풀이 재사용':''}${error?' · '+error:''}`;
  $('codingLearningProgress').max=report.total;$('codingLearningProgress').value=report.completed;
  $('codingLearningSummary').textContent=`최초 통과 ${report.first_passed} · 수정 포함 통과 ${report.repaired_passed} · 교사 예시로 보완 ${report.teacher_examples} · 피드백 ${report.coaching_count}회`;
  $('codingPartResults').replaceChildren();for(const [part,row] of Object.entries(report.parts||{})){const p=document.createElement('p');p.textContent=`${names[part]||part}: ${row.completed}/50 · 최초 ${row.first_passed} · 수정 포함 ${row.repaired_passed}`;$('codingPartResults').append(p);}
  if(report.weight_result){const p=document.createElement('p');p.textContent=`실제 가중치 갱신 ${report.weight_result.optimizer_steps||0}회 · 사용한 교재 ${report.weight_result.seen_ids?.length||0}개`;$('codingPartResults').append(p);}
  $('codingCoaching').textContent=(report.training_diagnostic?report.training_diagnostic+'\n\n':'')+(report.recent_coaching||[]).map(r=>`${r.task_id}\n${r.advice}\n${r.observed_failure}`).join('\n\n');
  const running=Boolean(data.current?.process_alive);$('startCodingLearning').disabled=running;$('stopCodingLearning').disabled=!report.process_alive;$('resumeCodingLearning').disabled=running||!report.can_resume;
 }catch(error){$('codingLearningState').textContent=error.message;}}
 button.onclick=()=>{dialog.showModal();refresh();clearInterval(timer);timer=setInterval(refresh,3000);};
 $('closeCodingLearning').onclick=()=>dialog.close();dialog.addEventListener('close',()=>{clearInterval(timer);timer=null;});
 $('refreshCodingLearning').onclick=refresh;
 $('codingLearningRun').onchange=()=>{viewId=$('codingLearningRun').value;refresh();};
 $('startCodingLearning').onclick=async()=>{try{const parts=[...dialog.querySelectorAll('[name=codingPart]:checked')].map(e=>e.value);if(!parts.length)throw Error('파트를 하나 이상 선택하세요.');$('startCodingLearning').disabled=true;const created=await api('/api/coding-learning/jobs','POST',{parts,repairs:Number($('codingRepairs').value),training_seconds:Number($('codingTrainSeconds').value)});viewId=created.id;await refresh();}catch(error){$('codingLearningState').textContent=error.message;$('startCodingLearning').disabled=false;}};
 $('resumeCodingLearning').onclick=async()=>{try{if(!active)return;$('resumeCodingLearning').disabled=true;const created=await api('/api/coding-learning/jobs/'+active.id+'/resume','POST',{training_seconds:Number($('codingTrainSeconds').value)});viewId=created.id;await refresh();}catch(error){$('codingLearningState').textContent=error.message;$('resumeCodingLearning').disabled=false;}};
 $('stopCodingLearning').onclick=async()=>{try{if(active)await api('/api/coding-learning/jobs/'+active.id+'/cancel','POST',{});await refresh();}catch(error){$('codingLearningState').textContent=error.message;}};
 await refresh();
})().catch(error=>{const note=document.createElement('p');note.setAttribute('role','status');note.textContent='코딩 학습 도구를 불러오지 못했습니다. 새로고침 후 다시 시도하세요. '+error.message;document.getElementById('openSettings')?.before(note);});
