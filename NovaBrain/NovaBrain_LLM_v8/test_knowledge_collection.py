import json,tempfile,unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch
import collect_domain_knowledge as collector
import domain_knowledge as knowledge


class KnowledgeCollectionTests(unittest.TestCase):
    def test_rate_limit_stops_requests_without_short_retry(self):
        error=urllib.error.HTTPError(collector.API,429,'Too Many Requests',{'Retry-After':'1800'},None)
        with patch.object(collector.time,'sleep'),patch.object(collector.urllib.request,'urlopen',side_effect=error) as request:
            with self.assertRaises(collector.RateLimited) as caught:collector.api(list='categorymembers')
            self.assertEqual(caught.exception.delay,1800)
            request.assert_called_once()

    def test_missing_revision_is_not_imported(self):
        self.assertIsNone(collector.candidate({'ns':0,'title':'Example','extract':'x'*120}))

    def test_import_deduplicates_and_never_auto_approves(self):
        with tempfile.TemporaryDirectory() as folder:
            directory=Path(folder)
            pages=[{'pageid':i,'ns':0,'title':title,'extract':'Evidence about computing. '*8,
                    'revisions':[{'revid':i+100}]} for i,title in [(1,'Alpha'),(2,'Alpha'),(3,'Beta')]]
            responses=[{'query':{'categorymembers':[{'pageid':p['pageid'],'ns':0,'title':p['title']} for p in pages]}},
                       {'query':{'pages':pages}}]
            with patch.object(collector,'STORE',directory/'collection'),patch.object(collector,'SEEDS',{'coding':['Programming']}),patch.object(knowledge,'DATABASE',directory/'facts.sqlite'),patch.object(collector,'api',side_effect=responses) as api:
                collector.run(1,5)
                self.assertEqual(api.call_count,2)
                state=json.loads((collector.STORE/'status.json').read_text(encoding='utf-8'))
                self.assertEqual(state['state'],'sources_exhausted_partial')
                self.assertEqual(state['added']['coding'],2)
                summary=next(r for r in knowledge.summary() if r['domain']=='coding')
                self.assertEqual(summary['imported'],2)
                self.assertEqual(summary['approved'],0)
                self.assertEqual(knowledge.retrieve('coding','Alpha'),[])
                rows=knowledge.pending('coding')
                self.assertTrue(all('oldid=' in r['url'] and 'contributors' in r['evidence'] for r in rows))
                api.reset_mock()
                collector.run(1,5)
                api.assert_not_called()
                self.assertEqual(next(r for r in knowledge.summary() if r['domain']=='coding')['imported'],2)


if __name__=='__main__':unittest.main()
