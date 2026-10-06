import tempfile
import unittest
import json
from pathlib import Path
from analysis.window_rank import deviation
from integrations.cdr.features import aggregate
from integrations.cdr.normalize import normalize
from rca_bench.io import write_jsonl,read_json


class UnifiedTests(unittest.TestCase):
    def event(self,**kw):
        return dict(timestamp=310,available_at=312,site='s',cnf='c',entity_id='e',cdr_type='CDR_Recurring_success',event_uid='1',result='success',amount='12.50',currency='VND',**kw)

    def test_signed_and_two_sided(self):
        self.assertLess(deviation([1,2,3,4,5],[-10],'baro_iqr_signed'),0)
        self.assertGreater(deviation([1,2,3,4,5],[-10],'iqr_two_sided'),0)

    def test_insufficient_reference(self):
        self.assertIsNone(deviation([1],[5],'nsigma_signed'))

    def process(self,rows):
        d=tempfile.TemporaryDirectory();self.addCleanup(d.cleanup);p=Path(d.name)
        write_jsonl(p/'in.jsonl',rows)
        result=aggregate(p/'in.jsonl',dict(as_of=1200,reference_end=600),p/'out')
        return result,read_json(p/'out/raw_eda.json')

    def test_dedup(self):
        event=self.event();rows,report=self.process([event,event])
        self.assertEqual(rows[0]['features']['cdr_count'],1)
        self.assertEqual(report['issues']['exact_duplicate'],1)

    def test_conflicting_duplicate(self):
        a=self.event();b=dict(a,amount='999')
        with self.assertRaises(ValueError):self.process([a,b])

    def test_currency_separation(self):
        rows,_=self.process([self.event(),dict(self.event(),event_uid='2',currency='USD')])
        self.assertEqual(len(rows),2)

    def test_future_exclusion(self):
        rows,report=self.process([self.event(),dict(self.event(),event_uid='2',available_at=1400)])
        self.assertEqual(rows[0]['features']['cdr_count'],1)
        self.assertEqual(report['issues']['not_available_at_cutoff'],1)

    def test_unknown_result_not_failure(self):
        rows,_=self.process([dict(self.event(),result='UNMAPPED')])
        self.assertIsNone(rows[0]['features']['fail_rate'])

    def test_amount_requires_confirmation(self):
        spec=dict(fields={'timestamp':'t','available_at':'a','amount':'v'})
        with self.assertRaises(ValueError):normalize(dict(t=1,a=2,v=300),spec)

    def test_no_ingestion_time_fallback(self):
        with self.assertRaises(ValueError):normalize(dict(a=2),dict(fields={'available_at':'a'}))

    def test_catalog_scope(self):
        catalog=read_json(Path(__file__).resolve().parents[1]/'integrations/cdr/catalog.json')
        self.assertEqual(len(catalog['types']),20)
        fail=next(x for x in catalog['types'] if x['cdr_type']=='CDR_Recurring_fail')
        self.assertEqual(fail['unique_fields'],4)


if __name__=='__main__':unittest.main()
