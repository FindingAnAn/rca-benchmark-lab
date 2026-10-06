import tempfile,unittest
from pathlib import Path
from analysis.errors import run
from rca_bench.io import write_jsonl,read_json,read_csv


class ErrorTests(unittest.TestCase):
    def test_false_positives_preserve_seed_and_no_relabel(self):
        with tempfile.TemporaryDirectory() as d:
            src=Path(d)/'src';src.mkdir()
            write_jsonl(src/'predictions.jsonl',[dict(algorithm='ml_logistic',seed=s,id='normal-window',group='capture-a',label=0,predicted=1,score=.9) for s in (42,123)])
            out=Path(d)/'audit';run(src,out)
            rows=read_csv(out/'error_review.csv')
            self.assertEqual(len(rows),2)
            self.assertEqual({r['seed'] for r in rows},{'42','123'})
            self.assertTrue(all(r['outcome']=='FP' for r in rows))
            self.assertTrue(all(r['ba_label_correct']=='' for r in rows))
            self.assertEqual(read_json(out/'summary.json')['algorithms']['ml_logistic']['FP'],2)


if __name__=='__main__':unittest.main()
