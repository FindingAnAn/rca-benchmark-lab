"""Produce one readable report; never pool metrics from different tasks."""
from pathlib import Path
import csv
import html
import json
from collections import defaultdict
from rca_bench.io import read_json


def main():
    root=Path(__file__).resolve().parents[1]
    run=root/'experiments/final'
    def read(path):
        with path.open(encoding='utf-8-sig') as f:return list(csv.DictReader(f))
    rca=read(run/'rcaeval_public/run/leaderboard.csv')
    tel=read(run/'telecomts_public/leaderboard.csv')
    grouped=defaultdict(list)
    for r in tel:grouped[r['algorithm']].append(r)
    def table(headers,rows):
        return '<table><thead><tr>'+''.join('<th>'+html.escape(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join(
            '<tr>'+''.join('<td>'+html.escape(str(x))+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table>'
    rc_table=table(['Algorithm','Hit@1','MRR','Avg@5'],[[r['algorithm'],*[f"{float(r[k]):.3f}" for k in ('hit1','mrr','avg5')]] for r in rca])
    tc_table=table(['Algorithm','F1 trung bình seed','AP trung bình seed'],[
        [name,*[f"{sum(float(r[k]) for r in values)/len(values):.3f}" for k in ('f1','ap')]] for name,values in grouped.items()])
    suite=read_json(run/'suite.json')
    validation=read_json(root/'docs/validation.json')
    body=f'''<!doctype html><html lang="vi"><meta charset="utf-8"><title>RCA Benchmark Lab — kết quả kiểm chứng</title>
<style>body{{font:16px/1.6 system-ui;max-width:1080px;margin:32px auto;padding:24px;color:#213547;background:#f8fafc}}h1{{font-size:30px}}h2{{margin-top:32px}}table{{border-collapse:collapse;width:100%;background:white}}th,td{{padding:9px;border:1px solid #ccd5df;text-align:left}}th{{background:#e8eef4}}.note{{padding:16px;background:#fff2cc;border-left:4px solid #aa7c00}}a{{color:#075b98}}code{{background:#edf0f5}}</style>
<h1>RCA Benchmark Lab</h1><p>Bản nền offline • kiểm chứng 2026-10-01 • Statistical / ML / DL</p>
<p>Đã hoàn tất {len(suite)} lượt chạy cuối: 6 schema fixtures và 2 public subsets. Snapshot/artifact audit: {validation['status']}.</p>
<p class="note">Đây là benchmark nghiên cứu. Chưa có dữ liệu thật của công ty, chưa kiểm chứng VM/ES/MANO live và chưa chạy toàn bộ sáu corpus public. Lượt bổ sung đã đọc 15 ảnh người dùng; xem docs/11_image_evidence.md và kết quả APP + resource ở docs/12_public_app_results.md.</p>
<h2>1. RCAEval: xếp hạng root service</h2>
<p>15 case CPU thật từ RE1-Online Boutique và 15 control lấy trước injection. Chỉ CPU/memory; bin 30s, prewindow 600s, observation 180s. Train: adservice; validation: cartservice; test: checkoutservice. Giữ toàn bộ repetitions cùng nhóm service-fault; test có 5 incident + 5 control, 12 candidates/case.</p>
{rc_table}
<p class="note">Cả sáu MRR=1 trên subset CPU dễ nhận diện. Không đủ căn cứ chọn mô hình tốt nhất hoặc suy rộng sang DB/network/code fault. Injection time đóng vai trò mốc phát hiện đã biết; không đo năng lực detector. Control trước injection là giả định healthy, không phải nhãn healthy độc lập do người vận hành xác nhận. Đây không phải kết quả tái lập bài báo RCAEval.</p>
<p><a href="../experiments/final/rcaeval_public/run/report.html">Báo cáo ranking chi tiết</a> · <a href="../experiments/final/rcaeval_public/run/trials.csv">Tuning trials</a> · <a href="../experiments/final/rcaeval_public/lifecycle.json">Lineage</a></p>
<h2>2. TelecomTS: anomaly classification theo window</h2>
<p>288 windows: train 96 (File), validation 96 (Twitch), test 96 (YouTube); mỗi split gồm normal và jammer. Lấy 48 dòng đầu mỗi file tại revision cố định. Chỉ 16 KPI số tạo feature; loại description, QnA, labels và các trường answer. Threshold/config chọn trên validation.</p>
{tc_table}
<p>F1/AP không cùng ý nghĩa với MRR ở bảng RCA. Hai seed chỉ đo biến thiên huấn luyện; không phải confidence interval về các môi trường telecom. Các windows liền kề tương quan, số capture còn nhỏ. Chưa đánh giá affected-KPI localization hoặc causal root.</p>
<p><a href="../experiments/final/telecomts_public/leaderboard.csv">Chi tiết theo seed</a> · <a href="../experiments/final/telecomts_public/summary.json">Protocol</a> · <a href="../experiments/final/telecomts_public/lifecycle.json">Lineage</a></p>
<h2>3. Các corpus chưa tải</h2>
<p>LEMMA, GAIA, AIOps2020 có adapter local qua mapping, đã chạy fixture tới train/tune/test; chưa xác minh pipeline trên export thực. Alibaba có reader bốn bảng và anomaly exploration; không tính root-cause metric thiếu ground truth. Trace/call được lưu riêng, chưa dùng làm predictor. Không gán fixture thành dữ liệu thật.</p>
<h2>4. Bàn giao</h2><p><a href="../README.md">README</a> · <a href="08_lab_runbook.md">Runbook</a> · <a href="09_system_mapping.md">Mapping hệ thống</a> · <a href="10_dataset_sources.md">Nguồn & revision</a> · <a href="validation.json">Audit</a></p>
<p>Không có upload/LLM/cloud tracking. Chạy offline bằng NumPy; dataset download chỉ là lệnh staging riêng. Model/trials/evidence/registry nằm local, không tự remediate hệ thống.</p></html>'''
    (root/'docs/RESULTS.html').write_text(body,encoding='utf-8')


if __name__=='__main__':main()
