# Làm việc với BA, SME vận hành và chủ dữ liệu

Phạm vi catalog gồm APP, business, DB, container, server, topology, network và DQ/label audit. Đây là danh sách toàn diện theo các nhóm đã biết trong ảnh, không thể khẳng định đủ mọi feature khi nghiệp vụ chưa chốt. Tất cả dòng bắt đầu PROPOSED_NEEDS_BA_AND_DATA_OWNER.

1. **Chủ dữ liệu:** xác nhận metric kind, unit, timestamp/event-arrival, cadence, scrape duplicates, identity, topology version, mất dữ liệu và giới hạn query. Giải thích khác nhau giữa `namespace` K8s và `ns` Aerospike, exporter `instance` và workload ID.
2. **BA:** định nghĩa transaction/command, success/technical failure/business rejection, denominator, retry, async response, critical flow, SLA và impact. Ví dụ BALANCE_NOT_ENOUGH có thể là kết quả nghiệp vụ đúng, không phải sự cố hạ tầng.
3. **SME vận hành:** phân biệt root với symptom; outage thật với maintenance/change; bằng chứng độc lập và nguyên nhân đã xác minh. Không suy ra root từ metric cao nhất.
4. **Data Science:** báo cáo coverage/drift/outlier/label disagreement theo cohort, thử feature trên train/validation, đo resource cùng chất lượng; giữ holdout mới cho vòng nghiên cứu sau.

Mỗi feature cần: owner; grain/candidate level; công thức; nguồn; unit; window; scope/grouping; missing/zero/reset policy; data availability at cutoff; expected direction; source version; approved_at. Khoảng tham khảo 1/5/15 phút phải được đối chiếu sampling 10/20/40/60 giây và SLO của luồng cụ thể.

Quy trình kiểm soát dữ liệu: **raw immutable → profile/DQ → review → version label/semantic contract → snapshot được duyệt → training**. DQ review không tự xác nhận causal label. Không dùng label_confidence, lỗi hậu kiểm, resolution text hoặc postmortem làm feature có sẵn lúc dự đoán.

Với nhãn ít: báo coverage của nhãn riêng; lấy mẫu review gồm điểm score cao, score thấp và chọn ngẫu nhiên theo layer/site/command để tránh chỉ nhìn vào alert. Theo dõi disagreement giữa reviewer, version và thời điểm nhãn có sẵn. Không tính accuracy trên toàn bộ unlabelled pool bằng cách gán normal. Không coi self-training/pseudo-label là ground truth.

Chưa có normal đáng tin: bắt đầu Statistical robust deviation trên reference được đánh dấu có thể nhiễu; mô hình trả danh sách review, không calibrated probability. PCA/AE cần baseline normal đủ phù hợp; Logistic cần positive root và negative đáng tin. Khi giả định này chưa đạt, hoãn điểm supervised và ghi rõ NOT_EVALUABLE thay vì tạo nhãn.

Ví dụ kiểm soát: counter reset không phải negative rate; CPU quota=-1 không phải chia cho -1; denominator request=0 cho ratio missing/undefined; latency bucket không thể trung bình percentile; nhiều Pod cùng Node abnormal chỉ là shared-host evidence. Business code cần dictionary theo module/command/version, không dùng rule code!=0 chung.
