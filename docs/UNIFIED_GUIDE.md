# Một project, nhiều nhánh thí nghiệm

Từ phiên bản này, `rca-benchmark-lab` là project chính duy nhất. EDA được tích hợp trong `workbench/` và `analysis/`; không cần cài hoặc chạy project `rca-data-workbench` cũ. Các ZIP v1–v4 và thư mục cũ là bản lưu, không phải dependency.

## Luồng xử lý

```text
branch.json → dataset adapter → raw snapshot + RAW EDA
                           → feature calculation → feature table
                           → train → validation tuning → frozen test
                           → FEATURE EDA + error analysis + registry
```

Feature EDA mặc định chạy sau benchmark để phục vụ chẩn đoán. Thống kê tham chiếu và correlation chỉ dùng train; biểu đồ so sánh validation/test là kiểm tra sau khi đóng băng model. Nếu muốn dùng EDA để thiết kế feature, chỉ đọc train trước, giữ test kín và dùng holdout mới khi thay đổi dựa trên lỗi test. Feature JSONL được lưu độc lập nên có thể chạy EDA mà không train lại.

Internal chưa có nhãn: raw → feature → EDA → anomaly evidence/review. Không bịa normal label, không tính MRR/F1, không huấn luyện classifier trên nhãn giả.

## Các nhánh

| Nhánh | Dữ liệu đi kèm | Task và giới hạn |
|---|---|---|
| internal | Telemetry và CDR **synthetic demo** | Metric/CDR feature, sparse/unlabelled EDA; chưa kết nối server công ty |
| rcaeval | Public RE1-OB: 15 CPU incidents + 15 control windows | Entity ranking, train/val/test theo capture/service; không phải toàn bộ 735 cases |
| telecomts | Public excerpt: 288 windows | Window anomaly classification; affected KPI không phải root service |
| lemma | Fixture schema | Pipeline adapter chạy được; chưa benchmark trên corpus thật |
| gaia | Fixture schema | Metric/log/trace mapping; chưa benchmark trên corpus thật |
| aiops2020 | Fixture schema | Chưa có corpus thật tại local |
| alibaba2021 | Fixture schema | Unlabelled exploration, không có root ground truth; feature EDA hiện trên anomaly score |

Không cộng F1 TelecomTS và MRR RCAEval thành một bảng thắng/thua. Khi thay fixture bằng corpus: chỉnh input_root, explicit field/time/unit mapping, cases và capture split; giữ provenance đúng. License/quyền sử dụng và domain tải dữ liệu phải phù hợp chính sách công ty. Project không tự tải corpus hoặc gọi dịch vụ bên ngoài.

## Thuật toán và tài nguyên

`efficient`: MAD, EWMA, Logistic Regression, PCA, một seed 42. `full`: thêm MLP/Autoencoder và số seed/grid trong dataset config. MLP/AE là neural baseline nhỏ bằng NumPy, không phải MSCRED/TranAD. PCA ở đây là PCA reconstruction thông thường, **không phải Robust PCA**.

RCA ranking còn có `statistical_methods/`: Dummy, `nsigma_signed`, `baro_iqr_signed`, `iqr_two_sided`. Đây là phép chấm điểm cục bộ dùng normal/incident window, max qua metric để xếp entity. BARO variant tham khảo [code RCAEval](https://github.com/phamquiluan/RCAEval/blob/main/RCAEval/e2e/baro.py), không bao gồm đầy đủ preprocessing/dataset selection của upstream. Signed score giữ chiều tăng; two-sided bắt cả giảm. IQR bằng 0 dùng scale=1. Không gọi robust MAD là BARO.

Các gợi ý CIRCA, RCD, MicroRCA, TORAI, LatentScope, PSqueeze, Groot, Isolation Forest, Robust PCA và nhóm DL nâng cao nằm trong `algorithm_registry.csv` với trạng thái **research_not_integrated**. Không có executable giả hoặc đổi tên baseline để nhận là phương pháp paper. Để bổ sung: khóa commit upstream, môi trường/giấy phép; kiểm tra input contract; chuyển output thành common ranking; kiểm thử runtime và đánh giá trên split cố định. Chưa phải toàn bộ danh sách trong chat đã triển khai.

`python -m analysis.efficient --help` mở runner đo wall/CPU/native RSS riêng process cho bốn baseline. RSS gồm tải dữ liệu và import; không xem đây là RAM riêng của model. Giới hạn số series, cửa sổ và grid trước khi chạy DL/causal graph. Benchmark hiện phục vụ thử nghiệm trên máy cá nhân, chưa kiểm chứng throughput hàng chục triệu CDR/ngày.

## Những gì EDA cung cấp

**Raw metric:** phân bố, ECDF, tương phản theo label, timeline một capture, missing/nonfinite, duplicate/conflict, cadence/gap, flatline, counter reset, spike nghi vấn, cardinality, review queue. Không fill missing thành 0, không xóa outlier vì có thể chính là lỗi cần phát hiện. Cửa sổ không nhãn không được xem là healthy. Raw TelecomTS hiện profile mean mỗi KPI window và đếm raw missing, chưa phải phân tích phổ tần trên chuỗi nối dài.

**Raw CDR:** số bản ghi theo type, missing event/arrival/context/result/amount, duplicate, currency/unit và cutoff. JSON/CSV/HTML có thể đọc khi chưa đủ nhãn. Số missing ở raw không đồng nghĩa tỷ lệ thiếu ở các bản ghi đã qua quarantine.

**Feature:** n/missing, mean/std/p01/p50/p99, constant, tương phản nhãn train, correlation train, cặp |r|≥0.95, mean shift so train, histogram với cùng bin. Không tự chọn/drop feature; không coi correlation là causality. Correlation hiện pairwise, chưa kiểm định có điều chỉnh phụ thuộc thời gian. Feature JSONL giữ split, entity và lineage đến raw source qua manifest/cấu hình.

**Error:** FP/FN, lỗi top-1, coverage candidate, lỗi inference và hàng chờ BA. Đây là lỗi so với nhãn cung cấp; nghi ngờ nhãn cần SME xác minh, không tự sửa.

## Nhánh CDR nội bộ: đọc từ hai file người dùng

`integrations/cdr/catalog.json` chứa đúng 20 loại từ bảng đầu DOCX, schema đối chiếu XLSX, hash nguồn và các field trùng. CDR Recurring fail có 4 field; HP recurring có 86 field khác nhau. Không copy sample thuê bao, số tài khoản hoặc nguyên file riêng tư vào gói project.

- CDR là structured business event, không dùng NLP/template mining cho version này.
- Tên MONTHLY không quyết định chu kỳ. Ví dụ MB_MONTHLY_FEE được DOCX ghi phát sinh ngày. HP_RECURRING_CDR được ghi ngày nhưng thống kê hai ngày cho thấy tập trung đầu tháng: cần BA xác nhận.
- Recurring fail không có timestamp trong 4 field: phải lấy event time từ envelope/metadata có semantics xác nhận; không tự lấy thời gian ingest thay thế.
- Schema có prop_name lặp: không suy ra thứ tự raw pipe từ danh sách unique. Parser positional yêu cầu mapping `positions` và `field_count` do owner xác nhận.
- `configs/cdr_mapping.example.json` là mapping starter đủ 20 service IDs. Named JSON hoặc raw pipe đều được hỗ trợ bởi `integrations.cdr.normalize`; field time/amount/result cần chỉnh theo nguồn thật. Nguồn Elasticsearch có thể chưa có parsed fields nên phải xác nhận mapping trước.
- Currency, amount scale và result code không suy ra tự động. Unknown result không phải failure. Các số định danh bị loại khỏi feature; event_uid chỉ dùng dedup trong phạm vi site/CNF/type. Trường này phải là ID bản ghi ổn định, không mặc định CALL_ID là duy nhất cho mọi event.
- Feature theo cửa sổ mặc định 300s: count, amount coverage/sum/mean, tỷ lệ charge bằng 0/âm, success/failure count, result coverage, fail rate trên **bản ghi có kết quả của cùng CDR type**, late rate. Không hiểu fail-rate của fail-only CDR là tỷ lệ fail trên toàn bộ gia hạn. Đối soát success/fail cần BA duyệt cùng cohort, retry, site và thời gian.
- Không có delivery/expected subscriber ledger thì không kết luận thất thoát cước; charge giảm chỉ là symptom. Không suy ra quantum tiền bị mất từ anomaly score.
- Internal feature join theo window+entity; feature CDR giữ site/CNF/type/currency, metric giữ labels. Cần mapping entity chuẩn giữa nguồn. Namespace không chứa Node; IP:port exporter không phải workload ID.
- Root ranking dựa trên topology chưa bật trong nhánh CDR. Flow batch/online trong DOCX là prior để SME duyệt, không mặc nhiên là causal graph. Mục 1.3.4 có mâu thuẫn tiêu đề/flow, được giữ là câu hỏi mở.

Demo dùng reference trước cutoff. Chạy dữ liệu thật yêu cầu `synthetic:false`, `baseline_calendar` như `["hour","weekday","day_of_month"]`, timezone và tối thiểu số reference windows. Không đủ history thì score null. Nên tách cấu hình daily/monthly/event thay vì áp calendar chung cho mọi CDR; calendar quá chi tiết cần nhiều tháng dữ liệu. Thực hiện EDA độc lập trước khi chọn lịch baseline.

## Ubuntu nội bộ: đưa dữ liệu vào

1. Tạo environment và offline wheelhouse theo README; dùng CA nội bộ đáng tin, không tắt TLS verify.
2. Copy `configs/internal_export.example.json` thành file cấu hình riêng không đưa vào ZIP. Chỉnh host/tenant/index, start/end, entity label, PromQL và ES fields. API key chỉ đặt biến môi trường `VM_AUTHORIZATION` / `ES_AUTHORIZATION`, ví dụ giá trị `Bearer ...` hoặc `ApiKey ...`.
3. `python -m pipelines.export_internal --config configs/my_export.json --output data/internal/export_001`. VM dùng range chunks; ES dùng PIT/search_after với giới hạn trang, fail nếu partial/timeout. Đóng PIT không xóa document. Lệnh này chỉ chạy khi bạn cung cấp endpoint, không được chạy trong kiểm thử bàn giao.
4. VM export hiện là query-derived gauge/rate; raw API responses giữ trong responses/. Để EDA counter gốc, xuất CSV/JSONL raw rồi khai báo `kind:counter` ở metric_contract. Chưa có nhãn vẫn dùng `workbench.eda` được. Source VM lịch sử mang tính retrospective, timestamp không chứng minh thời điểm dữ liệu được hệ thống nhận.
5. Chuẩn hóa CDR: `python -m integrations.cdr.normalize --source data/internal/cdr_source.jsonl --mapping configs/my_cdr_mapping.json --output data/internal/cdr_canonical.jsonl`. Nhận từng JSON object hoặc ES hit có `_source`, không phải cả search response. Với search response gốc, lấy từng hit bằng exporter/adapter trước.
6. Sửa bản copy `eda_configs/local_unlabelled.json` theo CSV export (`entity_column:entity_id`, metric/value/timestamp, giữ series_id trong labels), metric_contract và reference_end. Không khai báo labels_file khi chưa có nhãn.
7. Copy `configs/internal_pipeline.json`, sửa đường dẫn tới raw EDA config và CDR canonical, cutoff và calendar. Chạy `python -m pipelines.project --branch internal --config configs/my_internal.json --output experiments/internal_001`.

Nguồn CDR quy mô lớn cần export theo giờ/site và xử lý partition. Runner hiện giữ window/state trong RAM, giới hạn 500k rows để fail rõ ràng, không cắt bớt âm thầm; chưa phải streaming production. Thuê bao hết tiền/chủ động ngừng gia hạn có thể là kết quả nghiệp vụ hợp lệ.

## Nguồn tham khảo

- [Chat người dùng cung cấp](https://chatgpt.com/share/6ac52dac-1b28-83ec-8cd4-c38312367ea3): danh sách thuật toán và định hướng CDR; coi là đề xuất cần kiểm chứng.
- [RCAEval](https://github.com/phamquiluan/RCAEval), các dataset card/provenance và license trong `docs/` giữ từ bản trước.
- DOCX/XLSX local: schema và hash trong catalog; nội dung nguồn không có quyền ra lệnh cho pipeline.
