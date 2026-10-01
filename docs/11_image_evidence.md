# Đối chiếu 15 ảnh demo và public pipeline

Đã đọc trực tiếp 15 ảnh đính kèm trong lượt bổ sung. Đây là ảnh mô tả/schema và kết quả query mẫu, **không phải chuỗi telemetry gốc**. Không suy ra đã kết nối hoặc benchmark trên hệ thống công ty. Không đưa ảnh, IP/hostname và ID nội bộ vào gói dữ liệu public.

## Bằng chứng từ ảnh

| Ảnh (giờ trong tên file) | Quan sát đọc được | Quyết định thiết kế |
|---|---|---|
| 01_36_38 | Hai service dùng chung Node IP nhưng khác port; cần kiểm service type, nodePort, hostNetwork/hostPort | Không gộp entity bằng IP; lưu service/pod UID và endpoint/port riêng. Endpoint không tự chứng minh quan hệ gọi |
| 01_36_33 và 01_36_06 | MANO → Site → VIM → CNF/VNF → VDU → CNFC/VNFC; VDU tương ứng Deployment/StatefulSet, CNFC gần một pod replica | Mapping semantic theo inventory VHT; không coi đây là chuẩn định danh toàn bộ cloud |
| 01_36_29 | External client → proxy/VIP → endpoint → Kubernetes Service → Pod | Tách traffic path khỏi management graph; cần Service/EndpointSlice/Ingress thực để xác nhận đường truy cập |
| 01_36_24 | Namespace nhóm resource logic; Node chứa pod ở nơi thực thi | Bổ sung entity namespace; validator từ chối namespace contains node |
| 01_36_20 | NFVI, VIM/cluster, control plane, worker, pod có container chính và sidecar | Node-hosts-pod là cạnh placement; không collapse nhiều container thành một entity nếu cần RCA cấp container |
| 01_36_01 | Quan hệ hạ tầng, K8s, nghiệp vụ, DB và exporter | Giữ nhiều loại cạnh; `command_name/type/code` là chiều nghiệp vụ, không phải nhãn root |
| 01_35_56 và 01_35_29 | Container 40s, server 60s; các CPU/fs operation counter có mục chưa query được | Missing/zero-series là trạng thái coverage; không điền zero; resampling cần giữ native cadence |
| 01_35_52 | Aerospike counter, gauge/flag và XDR; có metric độ trễ nhiều đơn vị | Không dùng generic DB proxy để tuyên bố đã xử lý đúng XDR; unit của từng metric phải rõ |
| 01_35_48 và 01_35_05 | APP 10s, DB 20s; process_time có chỗ chưa xác nhận ms/s; histogram read/write có `le` | Chu kỳ được xác nhận từ ảnh demo, chưa xác nhận scrape thực. Không đổi process_time sang ms bằng suy đoán |
| 01_35_45 | `type`/`code` có ý nghĩa thay đổi theo metric/module; recurring có nhiều error/result fields | Giữ nguyên label ngữ cảnh và phân tích theo module; không coi mọi code khác zero là lỗi |
| 01_35_39 | Aerospike `ns`, rack/leaf/zone; K8s namespace, pod/pod_name/pod_id; controller và host_network | `ns != namespace`, telecom zone != DB zone; không join hai namespace chỉ vì tên giống |
| 01_35_35 | `instance/job` thuộc exporter; nhiều trường node/hostname/target instance | Scrape identity khác workload identity; cần bảng alias từ inventory, không cắt IP rồi gán service |

Các ô chữ nhỏ không đủ chắc chắn để xác nhận tên/đơn vị cụ thể không được chép thành rule tự động. Khi có export, cần metric metadata TYPE/HELP, label samples và thời gian scrape để xác minh.

## Public data tương đồng ở đâu?

| Mẫu của hệ thống | Public proxy | Mức tương đồng / phần còn thiếu |
|---|---|---|
| APP request/process time/result | RCAEval `_load/_latency/_error` | Tương đồng hành vi request/latency/error. Đây là giá trị upstream đã preprocess; không phải raw counter OCS, chưa quy đổi đơn vị |
| CPU/memory container | RCAEval `_cpu/_mem` | Tốt để kiểm anomaly-based localization. CPU unit giữ theo nguồn, không tự coi là % |
| Pod + metric/log ES | LEMMA | Gần kiến trúc thu thập. Hiện mới chạy mapped fixture, cần export thực và quyền sử dụng dataset |
| Service metric/log/trace | GAIA | Gần correlation nhiều modality. Chưa chạy corpus thật |
| Business/platform/trace | AIOps2020 | Gần phân tầng APP/container/server. Chưa xác minh schema trên gói được cấp |
| Node/instance/call graph | Alibaba2021 | Gần placement/dependency. Chưa có ground-truth root để tính MRR; reader không biến rpcid thành span_id |
| KPI telecom | TelecomTS | Dùng kiểm anomaly generalization; không mô phỏng OCS billing/charging hoặc Aerospike |
| stop_writes, XDR, recurring business errors, LCM event | Chưa có trong public runs hiện tại | Giữ backlog cho internal validation, không tạo tên giả để tuyên bố đã phủ |

## Cách chạy phần bổ sung

```powershell
.\.venv\Scripts\python.exe -m pipelines.quickstart --dataset rcaeval_app
```

Run này giữ nguyên 15 failure cases, 15 controls, candidates và split của resource baseline; thêm APP proxy. Đây là so sánh nhóm feature trên cùng subset, **không thêm fault diversity hoặc dữ liệu thật công ty**. Test được tái sử dụng để mô tả ablation, không được dùng làm cơ sở chọn model production. Nên mở rộng failure type/system trước khi so sánh chất lượng thuật toán.

Trong code hiện tại, step benchmark là 30s của public subset, không tự áp sampling 10/20/40/60s vào dataset public. Khi nạp internal telemetry, resample theo cửa sổ phù hợp và native cadence; không upsample server 60s thành six observations thật mỗi phút.
