# Chạy và mở rộng pipeline

## 1. Máy staging và máy công ty

Máy staging có Internet được phép tải public dataset/wheel. Máy công ty chỉ nhận gói qua quy trình nội bộ, kiểm SHA256 và chạy offline. Không dùng VPN/proxy hoặc thay cấu hình để vượt chặn website. Nếu Hugging Face không được phép thì chuyển file từ kho nội bộ đã phê duyệt; các pipeline vẫn đọc local.

Core dùng NumPy. Trên máy staging cùng phiên bản Python/Windows với máy đích:

```powershell
python -m pip download --only-binary=:all: --dest wheelhouse numpy==2.3.5
Get-ChildItem wheelhouse -File | Get-FileHash -Algorithm SHA256 | Export-Csv wheelhouse-sha256.csv -NoTypeInformation
```

Trên máy công ty, sau kiểm tra wheel:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install --no-index --find-links wheelhouse numpy==2.3.5
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\python -m pipelines.run --config configs/rcaeval_public.json --output experiments/offline_rca
```

Chạy tại thư mục gốc lab, không cần `pip install -e .`. Tránh cài cùng package Hugging Face `datasets` trong environment này vì tên module local `datasets/` trùng; lab không sử dụng thư viện đó.

## 2. Tái lấy public subset (chỉ máy staging)

```powershell
python -m datasets.fetch_telecomts_sample --output data/new_telecomts --lines 48
python -m datasets.fetch_rcaeval_sample --output data/new_rcaeval
```

Fetch script có HTTPS, allowlist domain/redirect, cap dung lượng, revision và manifest SHA256. Chúng không giải nén hoặc chạy code từ dataset. Manifest ghi SHA của file tải về, không phải chữ ký xác thực nhà phát hành. Không chứa credential.

Chuyển RCAEval Parquet chỉ cần ở staging; cài PyArrow bằng wheel đã duyệt:

```powershell
python -m datasets.prepare_rcaeval_sample --input data/new_rcaeval --output data/new_rcaeval_csv --config configs/rcaeval_new.json
python -m pipelines.run --config configs/rcaeval_new.json --output experiments/new_rca
```

Đổi `input_root` trong bản sao cấu hình TelecomTS nếu dùng đường dẫn mới. Không sửa config hoặc dữ liệu của run đã nghiệm thu.

## 3. Nạp một dataset local mới

Sao chép config `*_fixture.json` tương ứng thành `*_local.json`, đổi `input_root`, `provenance` thành `local_reviewed`, `dataset_version`, mapping và nhãn. Fixture là ví dụ contract, không phải cam kết tên cột gốc của mọi release.

Mỗi metric khai báo `entity`, `metric`, `kind` (`gauge/rate/counter`), `unit`, `layer`, `time_unit`. Wide CSV dùng `columns`; long CSV dùng `entity_column`, `metric_column`, `value_column`. File tách theo capture có `capture_id` trùng `source_capture_id` trong cases. Continuous telemetry không đặt capture_id.

- RCAEval: column-to-entity mapping tường minh; không suy ra service bằng split `_` tổng quát. Tool chuyển subset hiện chỉ đọc hậu tố `_cpu/_mem` đã đối chiếu. Catalog chính thức là nguồn label.
- LEMMA: ES JSON dùng `hits.hits[]._source`; `field` hỗ trợ nested path như `kubernetes.pod.name`. Prometheus JSON thêm `format: prometheus_matrix`, timestamp/value cùng entity label đã chọn. NPY chỉ numeric, `allow_pickle=False`, phải cung cấp `npy_columns/start_time/sample_seconds`. Không chạy `.pkl` hoặc object-NPY. Cần đối chiếu file/readme ground truth của release; không lấy tên pod bất thường làm root mặc định.
- GAIA: metric `timestamp,value`, thời gian ms; entity/metric lấy từ danh mục file được duyệt. Business log khai báo `role: observed`. Run/injection log chỉ dùng lập cases. Trace với `start_time/end_time` có thể khai báo `start_column/end_column/duration_to_ms:1000`; timestamp ISO không timezone bắt buộc `utc_offset_minutes`. Phần release không có trace để trống, không điền giả.
- AIOps2020: khai báo mapping theo header thực trong gói được cấp. Fault time/location/type chuyển thành cases riêng; giữ cùng incident/campaign một split. Trace `id/pid` lần lượt là span/parent qua mapping. Adapter chưa xác minh trên bản dữ liệu gốc.
- Alibaba: `table` là `node/resource/metrics/callgraph`, `time_origin` bắt buộc. Thời gian 0..43200000 là ms tương đối. CSV cần header; thêm header đúng tài liệu nếu file gốc không có. `MCR` đã là calls/s; RT là ms. CallGraph giữ cả caller/callee observations, không biến rpcid thành span_id. Đường chạy hiện nạp vào RAM nên phải phân vùng file/cửa sổ trước khi chạy corpus lớn; chưa phải engine streaming 60+ GB.
- TelecomTS: nguồn JSONL `KPIs`, `anomalies.exists`; khai báo KPI số. Giữ chung original capture và augmentation cùng `capture_group`. Loại categorical protocol trong mẫu hiện tại. Không đưa description/QnA/statistics/labels/troubleshooting vào X. `affected_kpis` không phải ground truth causal root.

## 4. Incident contract

Xem `data/fixtures/rcaeval/cases.jsonl` và `data/public/rcaeval_csv_v2/cases.jsonl`.
Các trường bắt buộc: incident_id, group_id, t0, detected_at, cutoff, root_entities, candidates, is_incident, label_tier, label_source, label_available_at, availability_mode, log_coverage_complete.
`candidates` phải được chốt từ inventory trước biết root label; root ngoài inventory được giữ lại để candidate recall phản ánh thiếu phủ.

Default split theo thời gian + group + embargo, kiểm label availability. Public campaign holdout khai báo `split/campaign_id/source_capture_id`; group/capture không được đi qua split. Đây là đánh giá tổng quát hóa sang campaign độc lập, không mô phỏng thời gian vận hành thực. Không dịch timestamp để vượt kiểm tra split.

Prewindow >=5 observations; missing không thay bằng 0; không forward/backward fill. Counter giảm được coi reset và bỏ increment không xác định. Bin thời gian gắn nhãn phải, available_at không sớm hơn điểm đóng bin. Dữ liệu arriving sau cutoff không được dùng.

## 5. Artifact và đọc kết quả

Run RCA tạo raw/prepared snapshots, DQ, split, model/trọng số, trial, prediction/evidence, ranking metrics, HTML, registry SQLite. TelecomTS tạo features, models/threshold, trials, predictions, leaderboard và summary riêng. `lifecycle.json` bao gồm hash code/config/artifacts cho các run mới; `lab_registry.sqlite` theo dõi RUNNING/FAILED/COMPLETED.

```powershell
python -m rca_bench registry --db experiments/lab_registry.sqlite
python -m rca_bench score --model PATH_TO_MODEL_JSON --features PATH_TO_FEATURES_JSONL --output predictions.jsonl
```

Lệnh score ở trên dành cho RCA candidate feature schema; TelecomTS score cần thống kê KPI và threshold riêng của run, không đưa TelecomTS feature file vào CLI RCA.

```powershell
python -m pipelines.predict_telecomts --model experiments/final/telecomts_public/models/dl_mlp-42.json --input data/public/telecomts_sample/YouTube-jammer.jsonl --output experiments/replay_predictions.jsonl
python -m pipelines.verify
```

Lệnh predict nhận cả window chưa có label; chỉ đọc KPIs. File mẫu ở đây là replay test đã có, không phải đánh giá trên tập mới.

VM/ES: dùng lệnh `python -m rca_bench ingest --sources configs/sources.example.json --context ... --output ...` sau khi cấu hình endpoint/schema/env credential theo file ví dụ đang có trong configs. Chỉ khai báo modality có dữ liệu. MDA là import ranking để so sánh; MANO là inventory/topology, chưa có adapter API nhà cung cấp hoặc quyền thao tác hệ thống.
