import unittest,tempfile
from pathlib import Path
from workbench.local import label_state,collect_local
from workbench.eda import describe,case_state
from workbench.io import write_csv,write_jsonl


class Tests(unittest.TestCase):
    def test_configured_missing_label_file_not_silent(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):
                collect_local({'labels_file':'absent.jsonl'},Path(d))

    def test_unknown_is_never_normal(self):
        self.assertEqual(label_state([],'pod',1),'unlabelled')
        self.assertEqual(case_state({},1),'unlabelled')

    def test_conflicting_labels_disputed(self):
        labels=[dict(entity_id='a',start=0,end=10,status=s) for s in ('normal_confirmed','incident_confirmed')]
        self.assertEqual(label_state(labels,'a',5),'disputed')

    def test_outlier_kept(self):
        values=[1,1,1,1,1,100]
        profile,z=describe(values,[1]*5)
        self.assertEqual(profile['n'],6);self.assertGreater(z[-1],6);self.assertEqual(values[-1],100)

    def test_missing_reference_not_assumed_normal(self):
        profile,z=describe([1,2,3],[])
        self.assertEqual(profile['status'],'INSUFFICIENT_TRAIN_REFERENCE')

    def test_quality_checks_duplicates_reset_and_unknown(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            rows=[dict(t=t,entity='a',metric='requests',v=v) for t,v in [(0,1),(1,3),(1,4),(2,5),(3,1),(4,'bad')]]
            write_csv(root/'raw.csv',rows)
            cfg=dict(reference_end=2,sources=[dict(file='raw.csv',time_column='t',time_unit='s',entity_column='entity',metric_column='metric',value_column='v')],metric_contract={'requests':dict(kind='counter',unit='requests')})
            cfg,series,sources,labels=collect_local(cfg,root)
            self.assertEqual(labels['unlabelled'],4)
            self.assertIn('conflicting_duplicate',cfg['_quality']['issue_counts'])
            self.assertIn('counter_reset_or_discontinuity',cfg['_quality']['issue_counts'])
            self.assertEqual(len(next(iter(series.values()))),4)
            self.assertEqual(len(rows),6)


if __name__=='__main__':unittest.main()
