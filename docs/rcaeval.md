# RCAEval

## 1. Nguồn và phạm vi

- [RCAEval chính chủ](https://github.com/phamquiluan/RCAEval).
- [Dataset mirror của tác giả](https://huggingface.co/datasets/phamquiluan/RCAEval).
- Revision ghim: `afeacb11bcc94dadfd1c8f483ee4377b2b8b614e`; checksum metadata trong adapter.
- 735 ca, 9 tổ hợp RE1/RE2/RE3 và OB/SS/TT. File local: `cases.parquet`, `<case>/metrics.parquet`, log/trace khi metadata có.

Chỉ tải public theo chính sách mạng công ty. Không dùng proxy/tunnel để vượt chặn. Có thể tải ở môi trường được phép và chuyển corpus offline. Checksum tải lần đầu ghi provenance local, không thay thế chữ ký nhà cung cấp.

## 2. Chạy full

Dùng lệnh trong README. Mặc định kiểm tra đủ 735 ca và mọi modality khai báo. Thiếu file thì dừng, danh sách tại `inventory.json`; không tự chuyển sang sample.
`--download` tiếp tục file còn thiếu, file đang tải dùng `.part`. Muốn tải lại file nghi lỗi, chuyển riêng file đó ra ngoài corpus rồi chạy lại. Mỗi case xử lý tuần tự để giới hạn RAM; log/trace lớn vẫn cần RAM đủ cho một file Parquet.

## 3. Benchmark hiện tại

- Ranking dùng **metric**; log/trace được tải và có EDA/schema, chưa dùng để suy luận multimodal.
- Metric public được xem là feature đã export; không đoán kiểu counter từ tên.
- Fit reference trước injection; bỏ cửa sổ cắt ngang injection. Nhãn chỉ dùng đánh giá.
- MAD, N-sigma, IQR, PCA reconstruction, Isolation Forest đơn biến. Đây là baseline nội bộ, không tuyên bố tái lập chính xác các paper RCAEval.
- Entity lấy tiền tố metric trước `_` theo convention của corpus; kiểm tra mapping khi đổi dataset.
- Xếp entity theo score feature lớn nhất, tie theo tên. MRR, Hit@1/3/5 tính trên tất cả ca, ground truth vắng candidate nhận 0.
- `case_results.csv` giúp lọc ca sai theo fault/dataset. Không tune hyperparameter bằng kết quả test; muốn tune phải chia train/validation/test theo incident trước.

## 4. Thử nhanh và giới hạn

`--smoke-cases 2` chỉ kiểm thử kỹ thuật; manifest ghi `smoke`. Không dùng số liệu smoke để kết luận chất lượng toàn bộ benchmark. Corpus sample cũ 15 ca không phải full.

PCA tối đa 5 components, reference SVD lấy mẫu khoảng 512 dòng. Isolation Forest 32 cây, tối đa 256 samples, một luồng. Model JSON lưu tham số thống kê/PCA; IF tái fit từ `reference.parquet` và seed, không nạp pickle. Tổng thời gian case gồm EDA và mọi thuật toán, không phải latency riêng từng model.

Hyperparameter sửa trong `analysis` của hai config: `window_seconds`, `min_reference_points`, `min_coverage_ratio`, `pca_components`, `forest_trees`, `forest_samples`, `random_seed`. Chạy mỗi cấu hình vào output riêng; ghi quyết định chọn trên validation, không dùng test labels để chọn.
