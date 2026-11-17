"""Before/after real GGUF coding probes; generated code runs only in WASI."""
import json,sys,os,re,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent;SOURCE=ROOT.parent/'NovaBrain/NovaBrain_LLM_v8'
os.environ['NOVERA_DATA_DIR']=str(ROOT/'artifacts/qwen-guard-benchmark')
sys.path[:0]=[str(ROOT/'src'),str(SOURCE)]
from desktop import Controller,atomic,DATA
from sandbox_eval import Sandbox
from coding_workflow import extract_source,check_source
CASES=[
 ('ordered_unique','Write Python function ordered_unique(values). Remove duplicates but preserve their first appearance order. Return a list. Empty input returns [].',"assert ordered_unique([3,1,3,2,1])==[3,1,2]\nassert ordered_unique([])==[]\nassert ordered_unique([0,0])==[0]"),
 ('largest_prime_factor','Write Python function largest_prime_factor(n) for positive integers. Return the largest prime factor, or None for n=1. Do not return the first factor unless it is the largest.',"assert largest_prime_factor(1) is None\nassert largest_prime_factor(49)==7\nassert largest_prime_factor(13195)==29\nassert largest_prime_factor(2)==2"),
 ('binary_search_first','Write Python function binary_search_first(nums,target) for an ascending sorted integer list. Return the FIRST matching index when duplicates exist, otherwise -1. Handle an empty list.',"assert binary_search_first([],3)==-1\nassert binary_search_first([1,2,2,2,4],2)==1\nassert binary_search_first([-3,-2],-2)==1\nassert binary_search_first([1,3],2)==-1"),
 ('decode','Write complete Python code. Keep this exact helper behavior unchanged: def encode(s): return "".join(chr(ord(c)+3) for c in s). Implement function decode(s) that reverses encode. Include encode and decode, handle empty strings.',"assert encode('A')=='D'\nassert decode('D')=='A'\nassert decode(encode('abcXYZ'))=='abcXYZ'\nassert decode('')==''"),
 ('max_subarray_sum','Write Python function max_subarray_sum(nums). For nonempty input return the maximum sum of a NONEMPTY contiguous subarray. For empty input return 0. All-negative inputs must not incorrectly return 0.',"assert max_subarray_sum([])==0\nassert max_subarray_sum([-5,-2,-3])==-2\nassert max_subarray_sum([4,-1,2,1])==6\nassert max_subarray_sum([0])==0")]
ctl=Controller();sandbox=Sandbox();results={'cases':[],'executed_only_in':'offline WASI CPython, 256MiB, 10 seconds, no sockets','started':time.time()}
try:
 for enabled in [False,True]:
  for name,prompt,checks in CASES:
   result=ctl.chat([{'role':'user','content':prompt}],512,guards=enabled)
   row={'case':name,'guards':enabled,'response':result}
   try:row['check']=check_source('\n\n'.join(re.findall(r'```(?:python|py)\s*\n(.*?)```',result['text'],re.S|re.I)) or extract_source(result['text']),sandbox=sandbox,tests=checks)
   except Exception as e:row['check']={'tests_passed':False,'error':str(e)}
   results['cases'].append(row);atomic(DATA/'results.json',results)
   print('GUARDS',enabled,name,row['check']['tests_passed'],flush=True)
 results['model']=ctl.loaded
 results['baseline_passed']=sum(r['check']['tests_passed'] is True for r in results['cases'] if not r['guards'])
 results['guarded_passed']=sum(r['check']['tests_passed'] is True for r in results['cases'] if r['guards'])
finally:
 ctl.close();results['elapsed']=time.time()-results['started'];atomic(DATA/'results.json',results)
