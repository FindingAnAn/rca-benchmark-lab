import tempfile
import unittest
from pathlib import Path
from copy import deepcopy
from datasets.readers import timestamp, local_path, read_alibaba, read_telemetry
from datasets.fetch_telecomts_sample import validate_url
from features.resample import resample
from pipelines.telecomts import extract, run
from rca_bench.io import write_csv, write_jsonl
from rca_bench.data import temporal_split


class LabTests(unittest.TestCase):
    def metric(self,t,value,kind='counter',capture='a'):
        return dict(timestamp=t,value=value,kind=kind,unit='requests',series_id='x',capture_id=capture,available_at=t)

    def test_counter_reset_and_no_future_values(self):
        values=resample([self.metric(1,10),self.metric(11,30),self.metric(21,2),self.metric(31,12)],10)
        self.assertEqual([r['value'] for r in values],[2,1])
        self.assertEqual([r['timestamp'] for r in values],[20,40])
        self.assertTrue(all(r['available_at']>=r['timestamp'] for r in values))

    def test_conflicting_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            resample([self.metric(1,10),self.metric(1,12)],10)

    def test_capture_isolation(self):
        values=resample([self.metric(1,10,'gauge','a'),self.metric(1,12,'gauge','b')],10)
        self.assertEqual(len(values),2)

    def test_relative_time(self):
        self.assertEqual(timestamp(30000,dict(time_unit='relative_ms',time_origin=1000)),1030)

    def test_naive_time_requires_offset(self):
        with self.assertRaises(KeyError): timestamp('2021-01-01 00:00:00',dict(time_unit='iso'))

    def test_path_escape(self):
        with self.assertRaises(ValueError): local_path(Path.cwd(),'../outside.csv')

    def test_download_hosts(self):
        validate_url('https://huggingface.co/datasets/example')
        for url in ('http://huggingface.co/x','https://huggingface.co.evil.test/x','https://example.com/x'):
            with self.assertRaises(ValueError): validate_url(url)

    def test_labels_not_features(self):
        row={'KPIs':{'a':[1,2,3,4,5]},'description':'root A','anomalies':{'exists':True}}
        before=extract(row,['a'])
        row.update(description='root B',anomalies={'exists':False},QnA=['answer'])
        self.assertEqual(before,extract(row,['a']))

    def test_campaign_overlap_rejected(self):
        cases=[dict(incident_id=s,split=s,group_id=s,campaign_id=s,source_capture_id='same') for s in ('train','validation','test')]
        with self.assertRaises(ValueError): temporal_split(cases,{'split_protocol':'campaign_holdout'})

    def test_injection_log_cannot_be_predictor(self):
        with tempfile.TemporaryDirectory() as d:
            write_jsonl(Path(d)/'run.jsonl',[dict(time=1,service='a',message='root cause')])
            spec=dict(file='run.jsonl',modality='log',role='injection',time_column='time',time_unit='s')
            with self.assertRaises(ValueError): list(read_telemetry(d,[spec]))

    def test_alibaba_signed_rt_keeps_both_observers(self):
        with tempfile.TemporaryDirectory() as d:
            write_csv(Path(d)/'call.csv',[dict(timestamp=1000,traceid='t',rpcid='0.1',um='a',dm='b',rt=v,rpctype='rpc') for v in (13,-10)])
            rows=list(read_alibaba(d,[dict(file='call.csv',table='callgraph',time_origin=0)]))
            self.assertEqual([r['duration_ms'] for r in rows],[13,10])
            self.assertEqual([r['observation_side'] for r in rows],['caller','callee'])
            self.assertNotIn('span_id',rows[0])

    def test_telecom_duplicate_window_cross_split_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for split in ('train','test'):
                write_jsonl(root/f'{split}.jsonl',[dict(KPIs={'a':[1,2,3,4,5]},anomalies={'exists':False})])
            cfg=dict(input_root='.',sources=[dict(file=f'{s}.jsonl',split=s,capture_group=s) for s in ('train','test')],kpis=['a'])
            with self.assertRaisesRegex(ValueError,'crosses splits'): run(cfg,root,root)

    def test_prometheus_matrix_retains_labels(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'matrix.json'
            path.write_text(json.dumps({'status':'success','data':{'resultType':'matrix','result':[
                {'metric':{'pod':'p','code':'200'},'values':[[1,'4'],[2,'5']]}]}}))
            spec=dict(file=path.name,format='prometheus_matrix',modality='metric',time_column='timestamp',time_unit='s',
                      entity_column='pod',metric='requests',kind='counter',unit='requests',layer='APP',value_column='value',labels={'code':'code'})
            rows=list(read_telemetry(d,[spec]))
            self.assertEqual(rows[0]['labels'],{'code':'200'})
            self.assertEqual(rows[1]['value'],5)

    def test_gaia_span_interval_to_ms(self):
        with tempfile.TemporaryDirectory() as d:
            write_csv(Path(d)/'trace.csv',[dict(timestamp=1,service_name='s',trace_id='t',span_id='c',parent_id='p',start_time=3,end_time=3.05)])
            spec=dict(file='trace.csv',modality='trace',time_column='timestamp',time_unit='s',entity_column='service_name',
                      trace_column='trace_id',span_column='span_id',parent_column='parent_id',start_column='start_time',end_column='end_time',duration_to_ms=1000)
            self.assertAlmostEqual(list(read_telemetry(d,[spec]))[0]['duration_ms'],50)

    def test_typed_topology_semantics_and_asof(self):
        from integrations.mano import validate_inventory,influence_edges,as_of
        entities=[dict(entity_id='n',entity_type='node'),dict(entity_id='p',entity_type='pod')]
        edges=[dict(source='n',target='p',relation='hosts',valid_from=0,valid_to=20,available_at=10)]
        self.assertTrue(validate_inventory(entities,edges))
        self.assertEqual(as_of(edges,5,5),[])
        self.assertEqual(influence_edges(edges)[0]['source'],'n')
        edges[0].update(source='p',target='n')
        with self.assertRaises(ValueError):validate_inventory(entities,edges)


if __name__=='__main__': unittest.main()
