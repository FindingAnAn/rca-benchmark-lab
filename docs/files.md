# Mục đích các file

Đọc README để chạy; dùng bảng này để tìm đúng nơi sửa. Đường dẫn tính từ gốc project.

## Code

| File | Mục đích |
|---|---|
| `src/__init__.py` | Khai báo Python package. |
| `src/application.py` | Điều phối raw → feature → EDA → model → ranking/evaluation. |
| `src/cli.py` | Hai lệnh vào: rcaeval và internal. |
| `src/data/__init__.py` | Khai báo Python package. |
| `src/data/ingestion/__init__.py` | Khai báo Python package. |
| `src/data/ingestion/log_csv.py` | Đọc CSV theo mapping và timezone. |
| `src/data/ingestion/victoria_metrics.py` | Query_range theo hệ thống/chunk, lưu raw JSON. |
| `src/data/validation.py` | Kiểm tra schema, duplicate, thiếu, nonfinite. |
| `src/domain/__init__.py` | Khai báo Python package. |
| `src/domain/contracts.py` | Kiểu telemetry và chuyển thời gian. |
| `src/eda.py` | Phân bố, tương phản, correlation, biểu đồ raw/feature. |
| `src/features/__init__.py` | Khai báo Python package. |
| `src/features/log_parser.py` | Tách multiline, CDR/key-value, feature event và audit. |
| `src/features/logs.py` | Count và keyword error theo cửa sổ. |
| `src/features/metric_mapping.py` | Tính 19 feature tương đương và ghi audit. |
| `src/features/metrics.py` | Counter → rate, resample và feature request/response. |
| `src/modeling.py` | Fit baseline, chấm điểm, xác định điểm cực đại từng feature. |
| `src/rcaeval_expected.json` | Danh sách 735 ca dùng kiểm tra độ đầy đủ. |
| `src/rcaeval_preflight.py` | Kiểm tra tất cả ca trước full run. |
| `src/rcaeval_source.py` | Đọc RCAEval local, inventory, clock-block alignment. |
| `src/relationships.py` | Quan hệ cặp, lag, threshold và báo cáo rule. |
| `src/settings.py` | Đọc config, kiểm tra giới hạn, lấy endpoint/path từ môi trường. |
| `src/storage.py` | Ghi JSON, checksum và manifest kết quả. |

## Cấu hình và lệnh chạy

| File | Mục đích |
|---|---|
| config/internal.json | Nguồn VM/CSV, scope, cửa sổ, model, relationship rules |
| config/rcaeval_local.json | Phân tích RCAEval và override clock từng ca |
| config/feature_mapping.json | Công thức, nguồn, kind, unit để tính metric tương đương |
| config/log_parser.json | Năm schema CDR, provenance và giới hạn parse |
| scripts/run_rcaeval_local.sh | check/smoke/eda/full trên corpus local |
| scripts/run_internal_local.sh | eda/full trên khoảng thời gian nhập vào |
| scripts/package_repo.py | Tạo ZIP allowlist, checksum; không xóa dữ liệu gốc |
| pyproject.toml | Package Python, CLI, cấu hình test/format |
| requirements.txt | Phiên bản thư viện chạy |
| requirements-dev.txt | Công cụ kiểm thử/format |
| .gitignore | Loại dữ liệu, môi trường, output; vẫn giữ src/data |
| .gitattributes | Giữ LF cho script Bash khi chuyển Windows → Ubuntu |
| .vscode/settings.json | Cấu hình editor |
| .vscode/extensions.json | Extension Python gợi ý |
| .vscode/launch.json | F5 cho hai flow, hỏi đường dẫn/thời gian/output |

## Tài liệu

| File | Mục đích |
|---|---|
| README.md | Cài đặt và chạy hai luồng |
| docs/files.md | Bảng nhiệm vụ file này |
| docs/matching.md | Mapping metric/log và điều kiện tương đương |
| docs/analysis.md | EDA, threshold, model, ranking và giới hạn |
| docs/conventions.md | Quy ước ngắn dùng trong project |
| docs/matching/internal_metrics.csv | Danh mục 60 metric internal |
| docs/matching/rcaeval_metrics.csv | Matching metric RCAEval |
| docs/matching/rcaeval_raw_metrics.csv | Matching raw metric RCAEval |
| docs/matching/rcaeval_logs.csv | Matching log RCAEval |
| docs/matching/cdr_fields.csv | Trường CDR theo năm template |

## Kiểm thử

| File | Kiểm tra |
|---|---|
| tests/test_two_flows.py | Hai flow, dữ liệu, model và leakage |
| tests/test_rcaeval_local.py | Reader/corpus RCAEval local |
| tests/test_clock_blocks.py | Clock riêng từng block, quarantine và lỗi cấu trúc |
| tests/test_metric_mapping.py | Công thức metric, đơn vị, reset, missing |
| tests/test_log_parser.py | Multiline, CDR, timestamp, feature và provenance |
| tests/test_relationships.py | Correlation, lag và threshold |
| tests/test_layout.py | Import src, project root và đường dẫn dữ liệu mặc định |
| tests/test_evidence.py | Peak bằng chứng, ranking và EDA reference/current |

`data/`, input Downloads và output run do người dùng quản lý, không đóng gói. Bộ triển khai chỉ lấy danh sách trên; hai flow đều dùng dữ liệu thực có sẵn hoặc query VictoriaMetrics.
