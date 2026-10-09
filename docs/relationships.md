# Chạy biểu đồ và threshold

Code chính: `src/rca_lab/relationships.py`; tự chạy trong flow internal, kể cả `--eda-only`. Cấu hình tại `config/internal.json` → `relationships`.

## 1. Chạy lại từ feature đã có

```bash
python -m rca_lab.relationships --features data/runs/internal_01/features.parquet --config config/internal.json --reference-end 1791509400 --output data/runs/relationships_01
```

Thay đường dẫn và timestamp UTC giây. Output phải là thư mục mới. Input cũng có thể là CSV chuẩn gồm: `system_id,entity_id,dimensions,feature_name,window_end,value`. `window_end` phải đúng biên cửa sổ theo `analysis.window_seconds`.

Không đưa counter tích lũy vào phép tương quan; dùng feature `_rate` đã tính từ flow internal. Module này không tự đoán loại trường/đơn vị.

## 2. Chọn trường

`fields` mặc định: request_counter_rate, response_counter_rate, process_time_ms, log_error_ratio, log_count. Có thể thay bằng 2–20 feature đã tồn tại, bao gồm CPU, DB hoặc feature CDR bạn đã chuẩn hóa theo template.

Mỗi `(system_id, entity_id, dimensions)` được phân tích riêng. Nhiều series cùng tên trong một nhóm được báo ambiguous, không cộng gộp tự động. Log thiếu pod chỉ ở entity system; không tự join với pod metric. Muốn liên kết phải bổ sung mapping/aggregation cùng scope trước. Chưa có parser CDR raw tự động; không coi bản template Excel là chuỗi sự kiện.

## 3. Đặt rule và ngưỡng

Các phép tính: `value`, `difference=left-right`, `ratio=left/right`, `relative_gap=abs(left-right)/left`. Mẫu số 0 hoặc thiếu dữ liệu trả `unknown`.

- `reference_quantile`: học quantile trên reference, không học từ giai đoạn đang kiểm tra. Mặc định upper P99, ít nhất 20 cửa sổ. Đây là ngưỡng khám phá, cần nhiều reference đại diện hơn để hiệu chỉnh P99 ổn định; reference không được bảo đảm khỏe.
- `fixed`: dùng SLA/giới hạn BA xác nhận.
- `direction`: upper (cao bất thường), lower (thấp bất thường).
- `consecutive_windows`: số cửa sổ liên tiếp vượt ngưỡng; missing làm ngắt chuỗi.
- `min_left`: lọc traffic nhỏ cho phép tính tỷ lệ; đơn vị là đơn vị feature bên trái. Mặc định gap dùng 0.01 request/giây, chỉ là tham số khởi đầu cần hiệu chỉnh.

Ví dụ **minh họa**, không phải SLA đã chốt:

```json
{
  "name": "request_response_gap",
  "left": "request_counter_rate",
  "right": "response_counter_rate",
  "operation": "relative_gap",
  "threshold_mode": "fixed",
  "threshold": 0.02,
  "direction": "upper",
  "min_left": 1,
  "consecutive_windows": 3
}
```

Rule này báo candidate khi lệch >2% trong 3 cửa sổ liên tục và request rate >=1/s. Với window 60 giây, đây là ba cửa sổ phút; không phải kiểm tra latency 3 ms. Rule process_time có thể dùng threshold=100 chỉ sau khi xác nhận metric là ms và SLA 100 ms.

## 4. Đọc output

Mỗi `cohort_XXXX` có `identity.json` để biết hệ thống/entity/dimensions.

| File | Ý nghĩa |
|---|---|
| aligned_features.csv | Dữ liệu đã căn thời gian; missing giữ NA |
| timeline.png | Từng trường theo đơn vị gốc, đường chia reference/current |
| reference/current_pearson/spearman.png | Heatmap từng giai đoạn; hằng số/thiếu để trống |
| correlations.csv | Pearson/Spearman, lag và số cặp hợp lệ n |
| correlation_changes.csv | Chênh lệch correlation current-reference tại lag=0 |
| pair_XX.png | Scatter và đường tương quan theo lag; request/response có đường y=x |
| rule_XX.png | Giá trị feature/rule, ngưỡng và điểm candidate |
| decisions.csv | Thời điểm, rule, giá trị, ngưỡng, số reference, trạng thái |
| ../coverage.json | Scope/config; nhóm ambiguous hoặc không có dữ liệu phù hợp |

Trạng thái: `reference` (dùng học), `within_threshold` (trong ngưỡng rule), `watch` (vượt nhưng chưa đủ liên tiếp), `anomaly_candidate` (đủ điều kiện), `unknown` (chưa đánh giá được). **within_threshold không khẳng định toàn hệ thống khỏe**; các rule chưa phủ hết loại lỗi.

Lag dương k = right đi sau left k cửa sổ. Không nối xuyên đoạn thiếu và không ghép reference với current. Correlation không chứng minh nguyên nhân; response bằng 90% request vẫn có thể correlation=1. Vì vậy xem đồng thời gap, latency và lỗi nghiệp vụ.

Mặc định vẽ 10 cohort, tối đa 6 cặp scatter/cohort để tiết kiệm tài nguyên; CSV vẫn chứa mọi cặp trong nhóm trường được chọn. Thay `max_visual_cohorts` để điều chỉnh.

## 5. Chọn ngưỡng thực tế

Chọn reference theo cùng command/giờ cao điểm/ngày gia hạn; đối chiếu SLA; kiểm tra các điểm bị flag với log/CDR; chia thời gian riêng để hiệu chỉnh và kiểm chứng. Chưa có label thì đo số cảnh báo và tỷ lệ owner xác nhận, không báo accuracy/F1. Không dùng correlation cao/thấp đơn lẻ làm nhãn lỗi.
