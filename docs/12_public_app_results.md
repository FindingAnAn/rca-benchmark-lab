# Kết quả bổ sung: APP + resource public subset

Đã chạy sáu baseline trên cùng 15 failure CPU RE1-OB và 15 control của bản resource-only. Thêm các cột APP load/latency/error cùng entity inventory. Không dùng ảnh demo làm dữ liệu train.

| Algorithm | Hit@1 | MRR | Avg@5 |
|---|---:|---:|---:|
| stat_mad | 1.000 | 1.000 | 1.000 |
| stat_ewma | 1.000 | 1.000 | 1.000 |
| ml_logistic | 1.000 | 1.000 | 1.000 |
| ml_pca | 1.000 | 1.000 | 1.000 |
| dl_mlp | 1.000 | 1.000 | 1.000 |
| dl_autoencoder | 1.000 | 1.000 | 1.000 |

Đây là ablation feature trên subset CPU dễ, không phải dataset/fault mới và không phải kết quả trên OCS. Không chọn model production từ tập test đã dùng lại. Cần mở rộng failure types và system trước kết luận.

[Báo cáo run](../experiments/rcaeval_app-20261001T001643Z-f3306df1/run/report.html) · [Trials](../experiments/rcaeval_app-20261001T001643Z-f3306df1/run/trials.csv) · [Lineage](../experiments/rcaeval_app-20261001T001643Z-f3306df1/lifecycle.json)

Kiểm chứng: 35 unittest đạt; CLI quickstart APP chạy thành công; cấu hình VS Code là JSON hợp lệ. Chưa kiểm chứng UI F5 trên máy công ty. Python kiểm thử: 3.12; NumPy: 2.3.5.

Lượt này đã đọc trực tiếp 15 ảnh bổ sung; xem [bảng đối chiếu](11_image_evidence.md).
