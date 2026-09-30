# RCA Benchmark Lab

Pipeline offline cho nghiên cứu RCA trước khi có dữ liệu MANO/OCS thật. Kế thừa engine của `rca_benchmark_v1`, bổ sung adapter, resampling, dataset protocol và hai lượt chạy dữ liệu public. Không cần GPU, Docker, dịch vụ cloud hoặc API LLM.

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
