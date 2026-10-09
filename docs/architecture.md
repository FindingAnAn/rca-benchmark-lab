# Kiến trúc đã chọn

**Modular Monolith**, theo lựa chọn của bạn: một Python package, hai flow, chạy local; không thêm service triển khai riêng.

`cli → application → ingestion / validation / features / EDA / modeling → storage`

- `domain` và `settings` chứa contract/config chung; adapter không biết benchmark metric.
- Environment chỉ đọc tại `settings`; thuật toán không biết endpoint/secret.
- Input raw giữ riêng; mỗi run output mới; manifest hash code/config/artifact.
- Internal không có label: evidence/review. RCAEval có label: benchmark sau scoring.
- EDA raw và feature tách artifact. Missing, noise/outlier không bị đổi thành nhãn sự cố.
- Giữ `docs/conventions` làm nguồn quy ước. Python snake_case, type hints, Black/Isort; không áp dụng kiến trúc distributed cho prototype local.

Chưa có: causal graph/MANO topology inference, model serving, trace/alarm parser, Elasticsearch live connector, multimodal model, ngưỡng SLA do BA phê duyệt. Các phần này cần schema/dữ liệu thật; không tạo kết quả giả để lấp chỗ trống.

Mã cũ và flow dataset khác được lưu trong `../rca_before_two_flow_cleanup.zip` trước khi bỏ khỏi project đang chạy. Bản lưu này không phải project thứ hai để vận hành.
