# RCA Benchmark Lab — public data gần hệ OCS/MANO

## 1. Chạy trên Visual Studio Code / Windows

**Mục tiêu:** dùng data public để kiểm tra luồng xử lý và baseline trước khi có dữ liệu thật. RCAEval là bài xếp hạng root service gần kiến trúc microservice; TelecomTS là bài anomaly KPI bổ sung domain telecom. Không dùng nhãn TelecomTS thay root CNFC.

### Chuẩn bị môi trường

1. Giải nén gói, mở **File → Open Folder → `rca-benchmark-lab`**. Explorer phải thấy `pipelines`, `configs`, `README.md` ngay cấp đầu.
2. Dùng Python **3.12 x64**, VS Code và extension **Python**, **Python Debugger** của Microsoft từ nguồn được công ty cho phép. Không cần GPU. Gói ZIP chưa chứa Python, NumPy wheel hoặc extension.
3. Chọn **Terminal → New Terminal**, dùng PowerShell tại thư mục gốc lab. Tạo venv:

```powershell
py -3.12 -m venv .venv
```

Nếu không có `py`, dùng đường dẫn Python 3.12 được công ty cài, ví dụ `& 'C:\Python312\python.exe' -m venv .venv` (đổi theo máy thật).

**Máy được phép truy cập kho Python:**

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

**Máy công ty offline:** trên máy staging Windows x64/Python 3.12 đã duyệt, chạy `py -3.12 -m pip download --only-binary=:all: --dest wheelhouse -r requirements.txt`. Đưa wheelhouse vào lab qua kênh nội bộ, kiểm hash/package rồi chạy:

```powershell
.\.venv\Scripts\python.exe -m pip install --no-index --find-links .\wheelhouse -r requirements.txt
.\.venv\Scripts\python.exe -c "import sys,numpy; print(sys.executable); print(numpy.__version__)"
```

4. Nhấn **Ctrl+Shift+P → Python: Select Interpreter → `.venv\Scripts\python.exe`**. Nếu chưa xuất hiện, chọn Enter interpreter path. Mọi lệnh dưới đây gọi trực tiếp Python trong venv, không cần Activate.ps1 hoặc đổi ExecutionPolicy.

### Chạy public dataset có sẵn trong gói

```powershell
# Kiểm tra cài đặt và logic pipeline
.\.venv\Scripts\python.exe -m unittest discover -s tests -v

# Lần đầu: RCAEval CPU/memory
.\.venv\Scripts\python.exe -m pipelines.quickstart --dataset rcaeval

# Gần APP/container mẫu hơn: thêm load, latency, error đã preprocess ở upstream
.\.venv\Scripts\python.exe -m pipelines.quickstart --dataset rcaeval_app

# Bài bổ sung: anomaly trên KPI telecom
.\.venv\Scripts\python.exe -m pipelines.quickstart --dataset telecomts
```

`quickstart` tạo thư mục mới theo thời gian và ID dưới `experiments/`, không ghi đè lần trước. Đợi dòng **COMPLETED**, mở đường dẫn in ra. Lượt chạy RCA có `run/report.html`; TelecomTS có `leaderboard.csv` và `summary.json`. Dùng trình duyệt local mở HTML. Toàn bộ ba lệnh dùng file đã có, không download.

### Debug từng bước với F5

Mở **Run and Debug**, chọn một trong ba cấu hình có sẵn ở `.vscode/launch.json`, nhấn **F5**. Đặt breakpoint tại `pipelines/run.py` (`_run`), `features/resample.py` (`resample`), `rca_bench/data.py` (`build_case`) hoặc `rca_bench/runner.py` (`benchmark`). Theo dõi `cfg`, `rows`, `cases`, `x`, `y`. Dùng **F10** đi tiếp và **F11** đi vào hàm. TelecomTS đi qua `pipelines/telecomts.py` thay vì engine incident của RCA.

Lệnh theo module `python -m ...` giữ đúng import package. Không bấm Run Python File cho `pipelines/run.py` riêng lẻ. Các bước chọn interpreter/debug dựa trên [tài liệu môi trường VS Code](https://code.visualstudio.com/docs/python/environments) và [tài liệu debugger](https://code.visualstudio.com/docs/python/debugging). Đã kiểm tra CLI; chưa kiểm chứng thao tác F5 trên máy công ty.

## 2. Thứ tự xử lý và nơi sửa

| Bước | File thực hiện | Input → output |
|---|---|---|
| Chọn experiment | `pipelines/quickstart.py`, `configs/*_public.json` | Dataset, mapping, split, grid → thư mục run mới |
| Đọc và chuẩn hóa schema | `datasets/readers.py` | CSV/JSON/Parquet → metric/log/trace/call giữ identity, unit và label |
| Chuẩn hóa thời gian | `features/resample.py` | Gauge/rate/counter → bin theo thời gian; bỏ increment qua reset, giữ missing |
| Tạo dataset RCA | `rca_bench/data.py` | Incident + telemetry → feature từng candidate, label, split, DQ |
| Huấn luyện | `rca_bench/models.py`, `rca_bench/runner.py` | Train, grid và seed → weights/scaler, validation trials |
| Đánh giá | `rca_bench/evaluation.py` | Test ranking → Hit/Recall@k, MRR, MAP, NDCG; detection riêng |
| TelecomTS | `pipelines/telecomts.py` | KPI windows → feature thống kê, train/tune threshold, F1/AP |
| Lưu và kiểm tra | `rca_bench/io.py`, `registry.py`, `pipelines/verify.py` | Dataset/run → hash, manifest, SQLite, audit |

Muốn đổi model/hyperparameter: sửa **bản sao config**, mục `benchmark.algorithms/seeds`. Muốn đổi feature RCA: `rca_bench/data.py`. Muốn thêm schema nguồn: `datasets/readers.py`. Muốn đổi split: config và `data.py`; luôn giữ cùng incident/capture trong một tập. Không sửa trọng số hoặc file của run cũ.

## 3. Nhiệm vụ từng file code

| File | Nhiệm vụ |
|---|---|
| `pipelines/run.py` | Orchestrator dataset local, snapshot, prepare, benchmark, lifecycle RUNNING/FAILED/COMPLETED |
| `pipelines/quickstart.py` | Entry point dễ dùng cho terminal/F5; tạo output mới tự động |
| `pipelines/suite.py` | Chạy nhiều config tuần tự; ghi mọi lỗi vào suite, không bỏ qua âm thầm |
| `pipelines/telecomts.py` | Training/tuning/test riêng cho anomaly windows, không dùng QnA/description làm feature |
| `pipelines/predict_telecomts.py` | Load model và threshold đã đóng băng, score KPI windows không cần label |
| `pipelines/make_fixtures.py` | Sinh dữ liệu giả kiểm thử schema; không phải tải dataset thật; không chạy lại khi chỉ muốn benchmark public |
| `pipelines/verify.py` | Kiểm checksum snapshot, artifact và file public đã tải |
| `pipelines/report.py` | Tạo `docs/RESULTS.html` từ các run mốc `experiments/final`; không tự tổng hợp mọi run mới |
| `pipelines/package.py` | Đóng ZIP, loại venv/dependency tạm/cache, tạo SHA256 |
| `datasets/readers.py` | Reader chung có mapping; reader native bốn bảng Alibaba; giữ call_id và observer side |
| `datasets/fetch_rcaeval_sample.py` | Chỉ staging: tải 15 case RE1-OB CPU tại revision pin, giới hạn dung lượng |
| `datasets/fetch_telecomts_sample.py` | Chỉ staging: tải 6 trích đoạn JSONL, kiểm host/redirect và ghi manifest |
| `datasets/prepare_rcaeval_sample.py` | Offline Parquet → CSV 30s; tạo cases/control/split; `--include-app` thêm APP proxy |
| `features/resample.py` | Causal resampling, timestamp/available_at, duplicate conflict, reset counter |
| `rca_bench/data.py` | Normalize incident, split temporal/campaign, feature metric/log/change/topology, seal prepared |
| `rca_bench/models.py` | Implementation NumPy của MAD, EWMA, Logistic, PCA, MLP, Autoencoder; save/load |
| `rca_bench/runner.py` | Grid/seed, chọn bằng validation MRR, frozen test, evidence/report/model cards |
| `rca_bench/evaluation.py` | Ranking, threshold detection, bootstrap theo group, metric nhiều root |
| `rca_bench/connectors.py` | Query VM có chunk; Elasticsearch PIT/search_after; credential từ environment |
| `rca_bench/adapters.py` | Import RCAEval explicit mapping và đánh giá ranking MDA bên ngoài |
| `rca_bench/io.py` | JSON/JSONL/CSV, UTC, SHA256, seal/verify, tránh ghi đè |
| `rca_bench/registry.py` | SQLite runs/reviews; không deploy hoặc restart dịch vụ |
| `rca_bench/monitoring.py` | PSI drift giữa feature reference và current |
| `rca_bench/synthetic.py` | Sinh demo lifecycle nội bộ; không dùng kết quả làm hiệu năng production |
| `rca_bench/cli.py`, `__main__.py` | CLI legacy cho demo/prepare/benchmark/ablate/ingest/score/drift/review |
| `baselines/statistical/__init__.py` | API tạo MAD/EWMA, dùng engine chung |
| `baselines/ml/__init__.py` | API tạo Logistic/PCA |
| `baselines/dl/__init__.py` | API tạo MLP/Autoencoder |
| `integrations/mano/__init__.py` | Validate typed inventory, topology as-of, chuyển dependency thành heuristic propagation |
| `integrations/victoriametrics/__init__.py` | Export API `vm_extract` |
| `integrations/elasticsearch/__init__.py` | Export API `es_extract` |
| `integrations/mda/__init__.py` | Export API so sánh ranking ngoài |
| `features/__init__.py`, `models/__init__.py`, `evaluation/__init__.py`, `baselines/__init__.py` | API import ngắn cho engine chung; không có model khác ẩn trong các wrapper |
| Các `__init__.py` còn lại | Khai báo Python package; không phải script chạy riêng |
| `tests/test_benchmark.py` | Test engine, metric, model serialization, leakage, connector và lifecycle |
| `tests/test_lab.py` | Test adapter, time/unit, capture split, label exclusion và typed topology |

## 4. Config, dữ liệu và kết quả

| File/thư mục | Ý nghĩa |
|---|---|
| `configs/rcaeval_public.json` | Cấu hình RCAEval resource-only; 15 failure + 15 pre-injection controls |
| `configs/rcaeval_app_public.json` | Cùng protocol/candidates, thêm APP load/latency/error proxy; đơn vị upstream chưa quy đổi sang OCS |
| `configs/telecomts_public.json` | KPI số, File/Twitch/YouTube capture holdout, grid/seed |
| `configs/{rcaeval,lemma,gaia,aiops2020,alibaba2021,telecomts}_fixture.json` | Kiểm thử đường chạy từng schema; không phải dữ liệu public thực |
| `configs/demo.json` | Demo synthetic đầy đủ metric/log/change/topology |
| `configs/internal.example.json`, `sources.example.json` | Ví dụ chuẩn bị nguồn nội bộ; cần thay endpoint/schema và quyền truy cập |
| `data/public/rcaeval_sample/` | Parquet gốc được tải kèm catalog và download_manifest |
| `data/public/rcaeval_csv_v2/`, `rcaeval_app_csv/` | CSV chuyển đổi, cases.jsonl, conversion_manifest; dùng để chạy không cần PyArrow |
| `data/public/telecomts_sample/` | 288 JSONL windows public và download_manifest |
| `data/fixtures/` | Dữ liệu giả cho kiểm thử sáu adapter |
| `examples/`, `catalog/` | Contract incident/topology/MDA và survey kế thừa v1; nguồn cập nhật ở docs/10 |
| `requirements.txt` | Dependency core pin NumPy; đủ train cả ML/DL |
| `requirements-staging.txt` | Core + PyArrow cho converter RCAEval; không bắt buộc ở máy chạy CSV |
| `pyproject.toml` | Metadata package/entry point; chạy tại root không cần cài editable |
| `.vscode/settings.json`, `launch.json`, `extensions.json` | Interpreter/test discovery, ba cấu hình F5, extension gợi ý |
| `THIRD_PARTY.md`, `docs/upstream/` | Attribution, license metadata và source cards |
| `docs/11_image_evidence.md` | Mapping đã cập nhật từ 15 ảnh người dùng; phân biệt quan sát và giả định |

Mỗi run RCA có: `raw/` (telemetry/labels/seal), `prepared/features.jsonl` (feature candidate), `prepared/splits.csv` (phân tập), `prepared/dq_report.json` (DQ), `run/models/` (trọng số), `run/model_cards/` (phạm vi), `run/trials.csv` (tuning), `run/predictions/` (ranking/evidence), `run/leaderboard.csv`, `run/report.html`, `lifecycle.json` (hash/provenance). SQLite nằm ở thư mục cha của run. Các artifact lặp theo thuật toán/seed có cùng vai trò, không cần sửa thủ công.

TelecomTS lưu `models/`, `features.jsonl`, `trials.csv`, `predictions.jsonl`, `leaderboard.csv`, `sources.json`, `summary.json` ngay cấp run. `root_cause_metrics=null` có chủ đích vì đây là anomaly classification.

## 5. Xử lý lỗi thường gặp

| Hiện tượng | Cách xử lý |
|---|---|
| `No module named numpy` | Cài requirements bằng chính `.venv\Scripts\python.exe`, kiểm interpreter VS Code |
| `No module named pipelines` | Open Folder đúng root lab; dùng `-m`, không chạy file rời |
| `FileExistsError` | Dùng quickstart hoặc output tên mới; không xoá run đã có để chạy đè |
| Activate.ps1 bị chặn | Gọi trực tiếp Python trong venv như ví dụ; không đổi chính sách bảo mật |
| Thiếu pyarrow | Chỉ converter cần nó; chạy CSV public sẵn bằng quickstart không cần |
| Metric coverage failed | Kiểm timestamp/unit/capture/candidate/window và missing; không hạ ngưỡng chỉ để pass |
| Host download bị chặn | Dùng dữ liệu từ staging/kho nội bộ đã duyệt; không thêm proxy để vượt chặn |
| Namespace/ID không khớp | Phân biệt Kubernetes namespace, Aerospike `ns`, pod UID, exporter instance theo docs/11 |

## 6. Phạm vi và kết quả bàn giao

Pipeline offline cho nghiên cứu RCA trước khi có dữ liệu MANO/OCS thật. Kế thừa engine của `rca_benchmark_v1`, bổ sung adapter, resampling, dataset protocol và hai lượt chạy dữ liệu public. Không cần GPU, Docker, dịch vụ cloud hoặc API LLM.

**Bổ sung từ ảnh và lượt chạy APP:** [đối chiếu 15 ảnh](docs/11_image_evidence.md), [kết quả APP + resource](docs/12_public_app_results.md).

**Bắt đầu:** mở [báo cáo tổng hợp](docs/RESULTS.html), đọc [hướng dẫn chạy](docs/08_lab_runbook.md) và [mapping hệ thống](docs/09_system_mapping.md).

## Mức độ đã triển khai

| Dataset | Đường đọc dữ liệu | Đã kiểm chứng |
|---|---|---|
| RCAEval | Parquet → CSV wide → entity features → train/tune/test | 15 case CPU RE1-OB thật + 15 control lấy trước injection; sáu baseline |
| TelecomTS | JSONL KPI windows → capture holdout → anomaly classification | 288 windows public từ 6 capture excerpts; sáu baseline |
| LEMMA-RCA | JSON record/ES hits, Prometheus matrix, numeric NPY với mapping rõ | Schema fixture; chưa xác minh toàn bộ export gốc |
| GAIA/MicroSS | CSV metric theo series; business log/trace qua field mapping | Schema fixture; chưa chạy corpus gốc |
| AIOps 2020 | Business/platform/trace export qua field mapping | Schema fixture; phải đối chiếu header và fault labels của bản được cấp |
| Alibaba 2021 | Node/MSResource/MSRTQps/CallGraph CSV có header | Schema fixture; anomaly score + call records, không có điểm root-cause |

**Không có leaderboard chung giữa RCA và anomaly classification.** Bản này chưa tái lập các thuật toán chính thức của RCAEval, chưa chạy đầy đủ mọi dataset, chưa kết nối VM/ES/MANO thật. Trace được đọc và lưu riêng nhưng chưa dùng làm feature huấn luyện; graph hiện là heuristic từ topology đã duyệt. Aerospike/XDR và LCM chưa có dữ liệu tương đương để xác minh.

## Chạy offline

Python 3.10+ và NumPy. Các CSV public đã chuyển đổi có sẵn nên lượt chạy chính không cần Pandas/PyArrow.

```powershell
python -m unittest discover -s tests -v
python -m pipelines.run --config configs/rcaeval_public.json --output experiments/my_rcaeval
python -m pipelines.run --config configs/telecomts_public.json --output experiments/my_telecomts
```

Tên output phải mới. Không ghi đè run hoặc dataset đã đóng băng. Hướng dẫn cài NumPy từ wheelhouse nằm trong runbook.

```powershell
python -m pipelines.suite --configs configs/rcaeval_fixture.json configs/lemma_fixture.json configs/gaia_fixture.json configs/aiops2020_fixture.json configs/alibaba2021_fixture.json configs/telecomts_fixture.json --output experiments/my_schema_suite
```

Fixture chỉ kiểm tra phần mềm, không đại diện dữ liệu hay hiệu năng public dataset.

## Lifecycle

```mermaid
flowchart LR
  A[Public dataset ở máy staging] --> B[Revision + SHA256 + kiểm tra nội bộ]
  B --> C[Raw local, từng modality riêng]
  C --> D[Schema, đơn vị, counter rate, resample]
  D --> E[Incident/capture split và feature]
  E --> F[Train + tuning trên validation]
  F --> G[Test một lần cho config đã chọn]
  G --> H[Model, metric, evidence, SQLite registry]
  H --> I[Review để nghiên cứu hoặc đề nghị shadow]
```

Các bước phân tích không gọi mạng. Chỉ `datasets.fetch_*` và connector VM/ES được gọi tường minh mới sử dụng network. Không tự tải model, gửi log hoặc đồng bộ kết quả ra ngoài.

## Cấu trúc

`data/`: raw public, CSV chuyển đổi, schema fixtures. `datasets/`: readers và công cụ staging. `features/`: chuẩn hóa thời gian và feature. `baselines/{statistical,ml,dl}/`: API ba nhóm thuật toán. `models/`: load/save qua engine; trọng số từng run nằm trong `experiments/`. `evaluation/`: ranking/detection metric. `pipelines/`: điều phối từng dataset/suite. `integrations/{victoriametrics,elasticsearch,mano,mda}/`: integration API. `configs/`: mapping, split và hyperparameters. `tests/`: kiểm thử. `docs/`: thiết kế/runbook/kết quả. `rca_bench/`: engine dùng chung, giữ một implementation cho các module API để tránh lặp code.

## Baseline và lựa chọn

- RCA: MAD, EWMA, Logistic, PCA, MLP, Autoencoder. MLP và AE có huấn luyện/trọng số thật bằng NumPy.
- TelecomTS: max/mean robust-z trên thống kê window, Logistic, PCA, MLP, AE. Mean robust-z không được gọi là EWMA trong kết quả.
- Tuning chọn grid bằng validation MRR cho RCA, validation F1 cho TelecomTS; test không dùng chọn threshold/config. Seed và trial đều lưu.
- Không coi candidate không phải root là bình thường để fit PCA/AE của RCA: chỉ dùng control windows. Những candidate đó vẫn có thể là symptom.

Nguồn, revision và license theo dataset card: [danh mục nguồn](docs/10_dataset_sources.md). Không diễn giải nguồn phổ biến thành mặc định được phép truy cập trên máy công ty.
