# EDA và đọc bằng chứng

## 1. EDA raw

- Metric: kiểm tra timestamp, trùng/xung đột, thiếu, nonfinite; phân bố và đồ thị từng series. Counter raw tăng dần không dùng trực tiếp để kết luận tương quan nghiệp vụ.
- Log: coverage theo file/hệ thống, độ dài message, số record theo cửa sổ, blank và duplicate. Duplicate được báo cáo, không tự xóa giao dịch.
- RCAEval: kiểm kê ca và modalities trước khi chạy; EDA numeric theo thời gian gốc.

## 2. EDA sau feature

| Output | Dùng để xem |
|---|---|
| distribution.csv | Count, thiếu, zero, constant, percentile, IQR outlier |
| contrast.csv | Count/mean/median/P95/missing reference so với current |
| reference/current_pearson.csv | Quan hệ tuyến tính |
| reference/current_spearman.csv | Quan hệ đơn điệu |
| *_pair_counts.csv | Số cặp quan sát thật cho từng hệ số |
| correlation_fields.csv, scope.json | Thứ tự cột và giới hạn báo cáo |
| distributions.png, time_series.png, *_spearman.png | Phân bố, chuỗi thời gian, heatmap |

Raw không chia reference dùng tiền tố `all_`. IQR feature fit trên reference; outlier không đồng nghĩa nhãn lỗi. Không nội suy để tạo bằng chứng.

Phân bố giữ tất cả cột. Tương quan giới hạn 128 cột đầu; histogram 16 cột; time series 4 cột; heatmap 20 cột. Config `analysis.eda_max_*` điều chỉnh phạm vi. Visual mặc định 5 entity internal, 2 entity mỗi ca RCAEval; raw log tối đa 5 hệ thống. Xem identity.json để biết đối tượng thực tế.

## 3. Quan hệ và threshold

`relationships` trong config tạo phân tích cặp, lag và rules từ feature. Chỉ đối chiếu cùng hệ thống/entity/dimensions; chưa có mapping thì không nối log với metric.

| Tình huống | Bằng chứng cần xem | Cách đặt ngưỡng |
|---|---|---|
| Request và response lệch | rate, relative gap, tải, độ trễ | P99 reference, kéo dài 3 cửa sổ; xác nhận semantics 1:1 |
| process_time tăng | gauge latency và phân bố theo tải | P99 reference hoặc SLA do BA chốt |
| Timeout/error tăng | rate hoặc ratio, mẫu số | Ngưỡng reference; loại cửa sổ tải quá thấp |
| DB chậm kèm APP chậm | DB latency/error và APP latency, lag | Tăng đồng thời là giả thuyết, chưa chứng minh nguyên nhân |
| Node/container áp lực | RAM, CPU cores, IO, topology | So baseline và giới hạn tài nguyên đúng cấp |
| Log giảm đột ngột | count và coverage/export | Phân biệt ít giao dịch với mất telemetry |

P99 và 3 cửa sổ là cấu hình khởi đầu, chưa phải threshold sản xuất. Reference không có nhãn vẫn có thể nhiễm lỗi: chọn khoảng ổn định, kiểm tra EDA, review rồi mới đóng băng ngưỡng. Đánh giá false alarm trên khoảng thời gian khác. Correlation/lag không chứng minh nhân quả; request và response lệch có thể do retry, đang xử lý hoặc ranh giới cửa sổ.

## 4. Model và ranking

| Method | Điểm bất thường | Tài nguyên |
|---|---|---|
| mad | Độ lệch robust so median | Nhẹ |
| nsigma | Độ lệch so mean/std | Nhẹ, nhạy outlier reference |
| iqr | Khoảng cách vượt vùng IQR | Nhẹ |
| pca | Sai số tái dựng theo feature | Giới hạn số component |
| isolation_forest | Bất thường từng feature | 32 cây, tối đa 256 mẫu/cây mặc định |

Fit riêng từng system/entity trên reference, chấm current. `feature_ranking.csv` xếp từng feature-series trong system và method; `ranking.csv` lấy điểm feature lớn nhất của entity. Không so trực tiếp score MAD với IF. Đây là anomaly ranking, chưa phải causal model hoặc feature importance có giám sát.

`evidence.csv` giữ feature, series, dimensions, peak_window_end (UTC epoch), peak_value, reference median/P95, số mẫu và score. `model.json` giữ tham số fit; `reference.parquet` giữ dữ liệu reference. Dùng các file này để giải thích ai đứng đầu và tín hiệu xuất hiện khi nào.

RCAEval có Hit@1/3/5 và MRR theo ground truth; internal không có nhãn nên không công bố accuracy. RCAEval hiện ranking từ metrics; logs/traces được kiểm tra schema/coverage, chưa tham gia model đa phương thức.

## 5. Ca hai cột time và kiểm thử

`re1ob_productcatalogservice_cpu_3` có override `align_blocks`, vị trí time [1,53] trong config. Reader gắn mỗi block metric với clock riêng rồi outer join timestamp chính xác; không lấy clock đầu cho toàn hàng. Giá trị không có clock được quarantine. Preflight ghi chất lượng và trạng thái alignment/quarantine; ca khác vẫn kiểm tra nghiêm.

Override dựa trên cấu trúc danh mục cung cấp; cần kiểm tra quality trên corpus thật. Dừng khi sai layout, không bỏ ca để đạt 735. Bộ unit test dùng dữ liệu tạm kiểm tra thuật toán/reader, không thay cho chạy đủ corpus trên máy công ty.
