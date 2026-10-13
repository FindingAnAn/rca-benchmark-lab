# Quy ước project

- Một ứng dụng, module theo chức năng; CLI có hai flow `rcaeval`, `internal`.
- File/module/hàm/biến: `snake_case`; class: `PascalCase`; hằng: `UPPER_CASE`.
- Tên ngắn theo nhiệm vụ: `log_parser`, `metric_mapping`, `modeling`. Không thêm hậu tố final/v2/new.
- Python: type hint tại interface, docstring ngắn, Black 88 cột, isort profile black.
- Công thức/mapping/giới hạn đặt trong config; kết nối và token qua biến môi trường.
- Timestamp nội bộ là UTC epoch giây; tên feature ghi rõ đơn vị khi cần. Không đoán đơn vị hay nhãn.
- Raw giữ nguyên; biến đổi có audit/provenance. Thiếu dữ liệu không tự thành 0.
- Fit trên reference, không dùng nhãn/đoạn current để chọn baseline.
- Mỗi run output mới; dữ liệu thật và token không đưa vào Git/gói triển khai.
- Test tính đúng, thiếu/reset/clock và chống leakage. Fixture chỉ trong thư mục tạm của test.
- Tài liệu cốt lõi bằng Markdown và bảng CSV; không nhân bản cùng nội dung sang Word/Excel.

Đây là bộ quy ước ngắn áp dụng cho cấu trúc hiện tại: code trực tiếp trong `src/`, import `src.*`, chạy từ gốc project.
