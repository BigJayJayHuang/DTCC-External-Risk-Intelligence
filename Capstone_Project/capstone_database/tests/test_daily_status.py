import importlib.util
from pathlib import Path
import unittest

p=Path(__file__).resolve().parents[1]/'daily_status.py'
s=importlib.util.spec_from_file_location('daily_status',p);M=importlib.util.module_from_spec(s);s.loader.exec_module(M)

class DailyStatus(unittest.TestCase):
    def test_published_does_not_hide_partial_source_failure(self):
        r=M.build({'status':'partial_failure','successful_sources':['fed'],'failed_sources':[{'source_id':'emir','http_status':404}],'partially_successful_sources':['emir']},published=True)
        self.assertEqual(r['snapshot_publication'],'published')
        self.assertEqual(r['collection_status'],'partial_failure')
        self.assertEqual(r['failed_sources'][0]['source_id'],'emir')
        self.assertIn('emir',M.markdown(r))
    def test_unknown_publication_is_not_claimed_published(self):
        r=M.build({'status':'success','failed_sources':[]})
        self.assertEqual(r['snapshot_publication'],'not_confirmed')
    def test_market_refresh_failure_stays_visible(self):
        r=M.build({'status':'success','failed_sources':[]},{'status':'partial_failure','failed_sources':[{'source_id':'cboe','error':'schema changed'}]},published=True)
        self.assertEqual(r['collection_status'],'partial_failure')
        self.assertEqual(r['scoring_input_failures'][0]['source_id'],'cboe')
    def test_no_scores_or_register_are_modified(self):
        r=M.build({'status':'success','failed_sources':[]})
        self.assertFalse(r['event_register_modified'])
        self.assertFalse(r['historical_scores_recomputed'])

if __name__=='__main__':unittest.main()
