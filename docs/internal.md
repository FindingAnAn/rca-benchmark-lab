# Internal: 4 loại telemetry

## 1. Chốt mapping trước khi chạy

- `system_id`: tên ổn định do bạn đặt cho từng hệ thống.
- `vnf_instance_name`/`cnf_id`: filter hệ thống; không mặc định `instance` là service vì có thể là địa chỉ exporter.
- APP dùng entity `pod_id`; container thường dùng `pod`; server dùng `node`. Khai báo `entity_label` trên từng metric. Không join chúng chỉ bằng tên giống nhau.
- `namespace` nhóm resource, không chứa node. Pod được schedule trên node; MANO/CNF/VDU là mapping quản lý riêng.
- Cùng Node IP nhưng khác port chưa chứng minh là cùng ứng dụng.

## 2. Metric

1. Thay `REPLACE_SYSTEM_*` bằng label thật; `metric.enabled=true`.
2. Kiểm tra `kind`, `unit`, `cadence_seconds`, `entity_label` từng metric trong config. `process_time_ms` chỉ dùng dạng gauge sau khi xác nhận exporter; `process_time` chưa rõ đơn vị thì chưa thêm.
3. Copy base API của VMUI thành biến môi trường `RCA_VM_API_URL`, kết thúc `/prometheus/api/v1`. Có auth thì đặt `RCA_VM_AUTHORIZATION`; không ghi secret vào config.
4. Chọn cửa sổ tối đa 1 giờ. Code query từng hệ thống/metric theo chunk, từ chối partial response/warning và vượt row budget.
5. Kiểm tra `metric_quality.json` và raw EDA trước khi đọc ranking.

Thêm DB/container/server bằng cấu hình metric; filter scope phải tồn tại ở nguồn. Counter dùng delta/time; reset hoặc gap dài bị bỏ, không gán 0. Cửa sổ dưới 80% sample kỳ vọng bị coi là thiếu. Histogram `_bucket` chưa được suy ra p95 tự động; phải bổ sung phép tính đúng bucket trước khi dùng.

Có thể chạy từ CSV metric chuẩn bằng `--metric-file PATH`. Cột bắt buộc: `timestamp,value,system_id,entity_id,series_id,metric,kind,unit,cadence_seconds,dimensions`. Timestamp UTC giây; `dimensions` là JSON string. Tùy chọn `labels` giữ toàn bộ nhãn nguồn.

## 3. Log CSV cho 5 hệ thống

1. Đặt 5 CSV trong `Downloads/rca_logs`; đặt `RCA_LOG_ROOT` nếu khác.
2. Sửa `log.sources`: file, system_id, timestamp_column, text_column, time_unit (`iso/s/ms/us/ns`), timezone và delimiter.
3. Bật `log.enabled=true`. Tên cột của bạn có thể là `test`; sửa `text_column` tương ứng.
4. Nếu có cột pod, khai báo `entity_column`; nếu không, log chỉ ở entity `system`, không đoán pod từ text.
5. `error_pattern` là regex tín hiệu, không phải ground truth. Cửa sổ không có log giữ trạng thái chưa quan sát, không tự kết luận khỏe.

Metric/log giữ raw riêng. Chỉ hội tụ ở feature theo system/entity/thời gian có mapping rõ. Hiện chưa gọi Elasticsearch trực tiếp; CSV export là đầu vào hiện tại. Trace/alarm giữ `enabled=false`; bật khi chưa có schema sẽ báo lỗi rõ.

## 4. Feature cần BA xác nhận

| Nhóm | Cần BA/owner quyết định |
|---|---|
| Request/response | Cùng command, cùng scope, retry/drop có tính không, delay cho phép |
| Latency | ms/µs/s, trung bình hay tổng, SLA theo command, thời gian cao điểm |
| Result code | Mã thành công/từ chối nghiệp vụ/lỗi kỹ thuật của từng module |
| Recurring/rating | Chu kỳ, retry, mã kết quả, đối soát thiếu/trùng; chưa suy luận thất thoát tiền |
| Aerospike | `ns` DB khác namespace K8s; stop_writes, memory_free, XDR lag và histogram |
| Container/server | Giới hạn CPU/RAM, reset, Pod→Node theo thời điểm, missing exporter |
| Log | Keyword, timezone, parser, log sampling/rotation và mapping hệ thống |

Khi chốt cùng cohort, thêm vào `request_response_rules`:

```json
[{"name":"request_response_imbalance","request":"request_counter_rate","response":"response_counter_rate"}]
```

Công thức `abs(request_rate-response_rate)/request_rate`; request=0 giữ thiếu. Không cộng `command_name=all` với các command con. Nhiều series cùng cohort sẽ báo ambiguity để bạn sửa mapping. Hiện chưa hiệu chỉnh độ trễ giao dịch giữa hai cửa sổ, nên imbalance chỉ là dấu hiệu.

## 5. Review

Reference chưa có nhãn có thể đã chứa sự cố. Bắt đầu bằng giai đoạn owner đánh giá tương đối ổn định; so sánh nhiều reference. Một bộ thuật toán/config chung áp dụng cho các hệ thống, tham số fit tách từng entity/system để tránh trộn phân bố. Score không phải xác suất nguyên nhân. Chưa có ground truth thì không báo accuracy, F1 hay MRR.

## EDA độc lập

Thêm `--eda-only` vào lệnh internal để chạy raw EDA + feature EDA, không fit/ranking. Vẫn đặt `--reference-end` để chia hai giai đoạn so sánh; không cần đủ reference cho model. Dùng chế độ này để định hình và kiểm soát dữ liệu mới.
