# RCA Benchmark Lab — một project duy nhất

Project thử nghiệm RCA cho Data Science: **raw EDA → feature → benchmark → feature EDA → phân tích lỗi**. Chạy offline với dữ liệu mẫu đi kèm. Nhánh nội bộ dùng VictoriaMetrics + structured CDR từ Elasticsearch; chưa có kết nối hoặc dữ liệu production.

## Bắt đầu trên Windows / VS Code

1. Giải nén ZIP; trong VS Code chọn **File → Open Folder → rca-benchmark-lab**.
2. Cài Python 3.12, mở Terminal tại đúng thư mục chứa README này.
3. Chạy:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pipelines.project --branch internal
.\.venv\Scripts\python.exe -m pipelines.project --branch rcaeval --profile efficient
.\.venv\Scripts\python.exe -m pipelines.project --branch telecomts --profile full
```

Không cần activate PowerShell hoặc đổi execution policy. Trong VS Code: **Python: Select Interpreter → .venv**. Mỗi lệnh in ra thư mục kết quả riêng; mở `index.html` bằng trình duyệt, đọc CSV bằng VS Code/Excel. Không ghi đè run cũ.

Báo cáo đã chạy để xem ngay: [Internal](experiments/unified/internal-v5/index.html), [RCAEval](experiments/unified/rcaeval-v5/index.html), [TelecomTS](experiments/unified/telecomts-v5/index.html).

## Ubuntu và cài đặt offline

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pipelines.project --branch internal
```

Nếu máy công ty không có Internet, trên máy được phép tải, **cùng OS/architecture/Python với máy đích**, chạy `python -m pip download --only-binary=:all: -r requirements.txt -d wheelhouse`. Chuyển wheelhouse qua kênh nội bộ đã duyệt rồi:

```bash
.venv/bin/python -m pip install --no-index --find-links wheelhouse -r requirements.txt
```

Windows dùng `.\.venv\Scripts\python.exe` thay executable trên. Không dùng wheel Windows trên Ubuntu. Core yêu cầu NumPy/Matplotlib; đọc Parquet/DOCX/XLSX cần dependencies tùy chọn của công cụ tương ứng. Hai tài liệu đính kèm đã được trích schema, không cần cài openpyxl/python-docx để chạy benchmark.

## Chọn nhánh và phương pháp

```text
python -m pipelines.project --branch internal
python -m pipelines.project --branch rcaeval --profile efficient
python -m pipelines.project --branch telecomts --profile full
python -m pipelines.project --branch lemma
python -m pipelines.project --branch gaia
python -m pipelines.project --branch aiops2020
python -m pipelines.project --branch alibaba2021
```

Nhánh là thư mục cấu hình trong cùng project, không cần checkout Git. `efficient` dùng Statistical/ML và một seed; `full` thêm DL nhỏ nếu task hỗ trợ. Mỗi dataset có task/nhãn riêng. RCAEval và TelecomTS có **mẫu public thật**; bốn nhánh còn lại mới chạy **fixture schema**, chưa là kết quả trên corpus thật. Internal là **synthetic demo**, không phải dữ liệu công ty.

Thử cấu hình riêng: copy JSON được trỏ trong `branches/<dataset>/branch.json`, chỉnh grid/seeds/modalities và chạy `--config configs/my_experiment.json`. Cùng dataset/split/candidate universe mới so sánh thuật toán. Manifest và effective_config lưu theo từng run.

## EDA độc lập trong chính project

```text
python -m workbench.eda --config eda_configs/local_unlabelled.json --output experiments/my_raw_eda --scope all
python -m workbench.eda --config eda_configs/rcaeval_app_public.json --output experiments/my_train_eda --scope train
python -m analysis.errors --source experiments/unified/telecomts-v5/benchmark --output experiments/my_error_review
```

Feature EDA tự chạy trong lệnh project. Gọi riêng trong Python:

```python
from analysis.feature_eda import run
run('experiments/unified/rcaeval-v5/benchmark/prepared/features.jsonl',
    'experiments/my_feature_eda')
```

Reference/correlation chỉ fit train. Biểu đồ test là chẩn đoán sau đóng băng, không dùng chọn feature/hyperparameter. Outlier chỉ vào review queue, không tự xóa hay sửa nhãn. Missing và unlabelled được giữ rõ.

## Nhiệm vụ các thành phần

| Đường dẫn | Nhiệm vụ |
|---|---|
| `branches/*/branch.json` | Chọn config, EDA và provenance cho từng dataset |
| `configs/*` | Mapping dataset, split, budget, algorithm grid; internal export/CDR examples |
| `eda_configs/*` | Mapping raw dữ liệu, kind/unit, labels và reference window |
| `data/public`, `inputs/public` | Snapshot public và input EDA đã có tại local; không cần tải khi chạy |
| `inputs/demo` | Telemetry/CDR/label synthetic để kiểm thử logic |
| `datasets/readers.py` | CSV/JSON/JSONL/Parquet và adapter dataset; time/unit/entity mapping |
| `features/resample.py` | Resampling, counter→rate, reset/gap và availability |
| `workbench/eda.py`, `local.py` | Raw EDA public/local, quality issues, hình và review queue |
| `workbench/feature_catalog.py` | Đề xuất feature và câu hỏi BA |
| `analysis/feature_eda.py` | Phân bố feature, correlation, redundancy, contrast, train-reference shift |
| `analysis/window_rank.py` | Dummy, N-Sigma signed, BARO-IQR signed, IQR hai phía |
| `analysis/errors.py` | FP/FN, sai entity, coverage và hàng chờ review |
| `analysis/efficient.py`, `budget_worker.py` | Đo wall/CPU/RSS bằng process riêng |
| `rca_bench/data.py` | Incident window, feature metric/log/change/topology, split chống leakage |
| `rca_bench/models.py` | MAD/EWMA, Logistic/PCA, MLP/Autoencoder; lưu model JSON |
| `rca_bench/runner.py`, `evaluation.py` | Validation tuning, frozen test, ranking/detection metrics |
| `rca_bench/io.py`, `registry.py` | Hash/seal/verify và SQLite lifecycle |
| `pipelines/project.py` | Entry point hợp nhất các nhánh và report index |
| `pipelines/run.py`, `telecomts.py` | Orchestrator dataset và TelecomTS classification |
| `pipelines/internal.py` | Feature metric/CDR, EDA và unlabelled anomaly evidence |
| `pipelines/export_internal.py` | VM/ES export giới hạn, read-only, không cần nhãn incident |
| `pipelines/import_cdr_catalog.py` | Trích schema từ DOCX/XLSX local, không lấy sample PII |
| `integrations/cdr/catalog.json` | 20 CDR, field khác nhau/trùng, chu kỳ tài liệu và source hashes |
| `integrations/cdr/normalize.py` | Explicit field/position/time/amount/result mapping, loại identifier khỏi X |
| `integrations/cdr/features.py` | Dedup, cutoff, currency, aggregate CDR và raw CDR EDA |
| `integrations/mano` | Typed topology; không đồng nhất namespace/node/service |
| `integrations/victoriametrics`, `elasticsearch`, `mda` | Kết nối và wrapper tích hợp |
| `baselines`, `models`, `evaluation` | API wrapper cho cấu trúc project, không nhân bản thuật toán |
| `experiments/unified` | Kết quả từng run: HTML/CSV/JSON, models, features, manifest |
| `tests` | Leakage, connector, split, model round-trip, CDR correctness |
| `docs` | Hướng dẫn, mapping hệ thống, BA, nguồn dữ liệu, validation |

[Nhiệm vụ từng file Python](docs/file_inventory.md) · [Hướng dẫn kiến trúc, thuật toán và Ubuntu/internal](docs/UNIFIED_GUIDE.md) · [Feature/BA](docs/BA_AND_DATA_CONTROL.md) · [Trạng thái thuật toán gợi ý](docs/algorithm_registry.csv).

## Kiểm thử và giới hạn

```text
python -m unittest discover -s tests -v
```

RCAEval subset CPU nhỏ dễ đạt điểm cao; không suy ra thuật toán tốt nhất hoặc sẵn sàng production. TelecomTS chấm anomaly, không chấm root entity. CDR thiếu expected ledger/nhãn không được kết luận thất thoát. CIRCA/RCD/TORAI và các paper model khác trong registry chưa tích hợp; N-Sigma/BARO hiện là local scoring variants, không phải tái lập nguyên repo. Chi tiết bằng chứng bàn giao nằm trong `docs/validation_unified.json`.
