# Bổ sung EDA, BA và Statistical/ML tiết kiệm tài nguyên

## Hai project riêng

`rca-data-workbench` là project độc lập bên cạnh lab: không import engine/model, không cần training hoặc nhãn đầy đủ. Đọc `README.md` của workbench để dùng cho dữ liệu thật. Gói có EDA public và demo dữ liệu bẩn/ít nhãn; demo luôn được ghi synthetic. Chưa có dữ liệu thực của công ty để kết luận chất lượng nguồn nội bộ.

Catalog BA gồm 36 đề xuất, bao phủ APP/business/DB/container/server/topology/network/DQ/label. Mọi công thức, denominator, unit, grain, cửa sổ, code dictionary và SLO đều có trạng thái chờ BA/chủ dữ liệu xác nhận. Label confidence dùng audit, không đưa vào X. EDA dùng train/reference, không dùng test để tự chọn feature.

## Thuật toán ưu tiên

“Static” được hiểu trong tài liệu này là **Statistical** theo các trao đổi trước: robust MAD và EWMA. Nếu cần fixed-threshold rule thì đó là một baseline khác, cần BA chốt ngưỡng/đơn vị/SLO, chưa đánh đồng với MAD.

| Phương pháp | Cần nhãn gì | Chi phí chính | Điều kiện sử dụng |
|---|---|---|---|
| MAD | Không cần root labels khi chỉ xếp deviation; muốn chấm MRR vẫn cần nhãn root | Ước lượng median/MAD, score tuyến tính số feature | Reference có thể nhiễu; không coi mọi outlier là fault |
| EWMA | Tương tự MAD | Cập nhật thống kê gọn | Cần cadence/ordering đúng; bản engine dùng fixed alpha |
| Logistic | Positive root và negative candidate theo incident đã xác nhận | Matrix nhỏ, số epoch giới hạn | Weak/missing label không tự chuyển thành negative |
| PCA | Normal/control history đủ tin cậy | SVD trong training, matrix projection lúc score | Normal không tin cậy thì chưa đánh giá reconstruction là root cause |

Không thêm DL vào lượt ưu tiên chi phí này; các model DL cũ vẫn được giữ để tham khảo. Một seed phù hợp đo chi phí sơ bộ, chưa đủ đánh giá độ ổn định thống kê.

```powershell
.\.venv\Scripts\python.exe -m analysis.efficient --config configs/rcaeval_app_public.json --output experiments/my_efficient
.\.venv\Scripts\python.exe -m analysis.errors --source experiments/final/telecomts_public --output experiments/my_error_review
```

`analysis/efficient.py`: bốn thuật toán, subprocess riêng, một BLAS thread được yêu cầu qua environment, một seed, Logistic 80 epoch, grid nhỏ giữ trong config. `analysis/budget_worker.py`: wall/CPU của pipeline sau import, OS peak resident working set toàn process, p95 scoring và tổng byte artifact trial. Đây không phải GPU profiling; môi trường này chạy CPU.

Kết quả đo [resource_comparison.csv](../experiments/efficient_20261006/resource_comparison.csv): khoảng 6.5–8 giây wall/algorithm và 220 MiB peak RSS trên subset hiện tại; model artifact tổng các trial khoảng 0.5–5.8 KB. Peak RSS bị chi phối bởi nạp raw/feature/report, không đại diện riêng memory model. Chưa có phép đo có kiểm soát trước/sau để tuyên bố giảm RAM theo tỷ lệ. Khi mở rộng corpus, ưu tiên partition theo capture/site/day, giới hạn cardinality và không giữ toàn bộ long-format trong RAM.

Cả bốn MRR=1 trên 5 test CPU incidents nên chưa phân biệt được chất lượng. Chọn baseline nghiên cứu gọn MAD/EWMA trước; bổ sung ML khi feature/nhãn tốt hơn và chứng minh lợi ích trên fault types/system đa dạng. Không chọn model chỉ vì nhanh nhất ở một lần đo nhỏ.

## Phân tích lỗi, kể cả lỗi nhãn

`analysis/errors.py` xuất case_diagnostics và error_review có FP/FN, top-1 sai, root ngoài candidate, lỗi inference và trường BA review. Điểm sai luôn tương đối với nhãn đang có. Không khẳng định mô hình sai khi nhãn còn weak/disputed, cũng không tự sửa nhãn để làm đẹp metric.

Trên TelecomTS test nhỏ, Logistic seed 42 và 123 đều báo FP ở 48/48 window normal; PCA mỗi seed FP 47/48. Đây là tín hiệu để kiểm shift ứng dụng giữa File/Twitch/YouTube, feature scale, threshold validation và chất lượng label. Không đủ bằng chứng để quy kết một nguyên nhân duy nhất. Không gộp seed thành số incident độc lập; xem cột seed/group/id để review đúng.

Các result cũ không bị training lại sau khi xem test errors. Nếu dùng kết quả hậu kiểm để điều chỉnh feature/model, cần holdout mới hoặc protocol validation được thiết kế lại trước khi chấm vòng tiếp theo.
