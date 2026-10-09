# RCA Benchmark Lab

Một project **Modular Monolith**, hai flow: `rcaeval` và `internal`.

`Raw → kiểm tra chất lượng + EDA → feature + EDA → fit reference → chấm bất thường → ranking → đánh giá/review`

## 1. Mở bằng VS Code

Open Folder `rca-benchmark-lab`. Dùng Python 3.11/3.12; khuyến nghị 3.12.
Trong Terminal tại thư mục project:

```bash
python3.12 -m venv .venv312
source .venv312/bin/activate
```

Nếu đã có `.venv312`, chỉ activate. Windows: `py -3.12 -m venv .venv312`, rồi `.venv312\Scripts\Activate.ps1`.
VS Code → **Python: Select Interpreter** → chọn Python trong `.venv312`.

## 2. Cài thư viện

Trên máy công ty, dùng repository nội bộ do bạn cung cấp:

```bash
python -m pip config --user set global.index-url http://172.20.1.22:8081/repository/pypi-all/simple
python -m pip config --user set global.trusted-host 172.20.1.22
python -m pip config list
python -m pip config debug
python -m pip index versions matplotlib
python -m pip install -r requirements.txt
python -m pip install -e . --no-deps
```

`requirements.txt` ghim `matplotlib==3.10.6`. Các lệnh config thay đổi cấu hình pip của user, chỉ chạy trên môi trường được công ty cho phép. Nếu mirror thiếu phiên bản, nhờ quản trị mirror bổ sung; project không tự chuyển sang nguồn bên ngoài.

## 3. Chạy RCAEval đầy đủ

```bash
python -m rca_lab.cli rcaeval --config config/rcaeval.json --data data/rcaeval --download --output data/runs/rcaeval_full_01
```

Lệnh tải bộ public từ Hugging Face chính chủ, kiểm tra **735 ca**, gồm metric và log/trace khi metadata khai báo có. Không tự giới hạn 15 ca. Nếu mạng chặn, chuyển nguyên thư mục corpus từ môi trường được phép, bỏ `--download`. Chi tiết: [RCAEval](docs/rcaeval.md).

## 4. Chạy dữ liệu internal

Sửa `config/internal.json`: mapping 5 hệ thống/CSV, bật nguồn metric hoặc log. Mặc định tắt vì chưa có dữ liệu thật.

```bash
export RCA_VM_API_URL='http://YOUR_HOST:PORT/select/TENANT/prometheus/api/v1'
export RCA_LOG_ROOT="$HOME/Downloads/rca_logs"
python -m rca_lab.cli internal --config config/internal.json --start 1791507600 --reference-end 1791509400 --end 1791511200 --output data/runs/internal_01
```

Các mốc trên chỉ minh họa UTC epoch; thay bằng thời gian dữ liệu thật. Reference phải đủ ít nhất 20 cửa sổ. VMUI là giao diện; code gọi `query_range` tương ứng. Windows dùng `$env:RCA_LOG_ROOT='C:\Users\YOUR_USER\Downloads\rca_logs'`.
Chi tiết metric/log và feature BA: [Internal](docs/internal.md).

## 5. Đọc kết quả

| Artifact | Đọc để biết |
|---|---|
| `raw_eda/*/distribution.csv` | Phân bố, thiếu, hằng số, outlier của raw |
| `entity_*/feature_eda/` | Phân bố feature, tương quan reference, tương phản reference/current |
| `features.parquet`, `coverage.csv` | Feature thực dùng, số feature đủ dữ liệu |
| `entity_*/model.json`, `reference.parquet` | Tham số model, dữ liệu reference tái lập fit |
| `evidence.csv`, `ranking.csv` | Bằng chứng theo metric/log và thứ hạng entity |
| `benchmark_*.csv`, `case_results.csv` | Hit@1/3/5, MRR, phân tích ca sai — chỉ RCAEval |
| `manifest.json` | Config/artifact/code hash và trạng thái run hoàn tất |

Mỗi lần chạy dùng một thư mục output mới. Khi lỗi, giữ artifact để điều tra; không có manifest hoàn tất.
Ảnh chỉ vẽ tối đa 16 cột và một số entity đầu để tiết kiệm tài nguyên; bảng CSV giữ tất cả cột. Outlier là tín hiệu rà soát, chưa phải nhãn lỗi.

## File nào làm gì?

| File/module | Nhiệm vụ |
|---|---|
| `src/rca_lab/cli.py` | Hai lệnh vào hệ thống |
| `application.py` | Điều phối hai flow, tách fit/score/evaluate |
| `settings.py` | Config phân tích và biến môi trường đường dẫn/endpoint |
| `storage.py` | Ghi JSON, checksum và manifest |
| `domain/contracts.py` | Loại telemetry, chuyển timestamp về UTC |
| `data/ingestion/rcaeval.py` | Tải/chốt revision, kiểm tra corpus đầy đủ |
| `data/ingestion/victoria_metrics.py` | Query theo hệ thống và time chunk; lưu JSON raw |
| `data/ingestion/log_csv.py` | Đọc CSV local theo mapping, lưu bản raw |
| `data/validation.py` | Kiểm tra schema, trùng/xung đột, thiếu/nonfinite |
| `features/metrics.py` | Counter → rate; cửa sổ; đối chiếu request/response |
| `features/logs.py` | Số log, số/ratio keyword lỗi theo cửa sổ |
| `eda.py` | EDA raw/feature, CSV và biểu đồ local |
| `modeling.py` | MAD, N-sigma, IQR, PCA và Isolation Forest |
| `config/*.json` | Đúng hai cấu hình flow |
| `tests/test_two_flows.py` | Kiểm thử offline về dữ liệu/leakage/flow |
| `docs/architecture.md` | Quyết định kiến trúc và giới hạn |
| `docs/conventions/` | Quy ước của bạn, giữ nguyên |
| `__init__.py` | Khai báo Python package |

Kiểm thử: `python -m pip install -r requirements-dev.txt`, sau đó `python -m pytest -q`.

## Quan hệ metric và CDR

Xem [đối chiếu trường và 20 tình huống bất thường](docs/telemetry_review/README.md): danh mục 60 metric từ ảnh, toàn bộ schema CDR trong Excel, điều kiện join, request/response imbalance và phương pháp correlation. Đây là phân tích schema/rule; chưa phải kết quả trên telemetry thật.

Phần code vẽ và threshold đã có: [cách chạy phân tích quan hệ](docs/relationships.md). Chạy độc lập từ `features.parquet` hoặc tự chạy trong flow internal. Module: `src/rca_lab/relationships.py`.
