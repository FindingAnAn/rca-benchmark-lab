# Nguồn dữ liệu và quyết định sử dụng

Đối chiếu 2026-10-01. Link upstream xác định nhà phát hành; quyền truy cập và điều kiện sử dụng trong doanh nghiệp vẫn theo chính sách nội bộ. Không tải full corpus hoặc tự tìm mirror khác khi nguồn bị chặn.

| Dataset | Nguồn chính | Quyết định trong lab |
|---|---|---|
| RCAEval | [GitHub](https://github.com/phamquiluan/RCAEval), [HF dataset](https://huggingface.co/datasets/phamquiluan/RCAEval) | Dùng public subset RE1-OB CPU, dataset card MIT; HF revision `afeacb11bcc94dadfd1c8f483ee4377b2b8b614e` |
| TelecomTS | [HF của tác giả](https://huggingface.co/datasets/AliMaatouk/TelecomTS) | Dùng public excerpts, dataset card MIT; revision `1b3a88a440f4922edfcd1e230e42c003c0e13bdf` |
| LEMMA-RCA | [Code](https://github.com/KnowledgeDiscovery/rca_baselines), [raw](https://huggingface.co/datasets/Lemma-RCA-NEC/Cloud_Computing_Original), [preprocessed](https://huggingface.co/datasets/Lemma-RCA-NEC/Cloud_Computing_Preprocessed) | Adapter local; chưa tải corpus. Card preprocessed ghi CC-BY-NC-4.0, cần làm rõ quyền sử dụng cho dự án doanh nghiệp trước khi nhập |
| GAIA | [CloudWise repo](https://github.com/CloudWise-OpenSource/GAIA-DataSet) | Adapter local; chưa tải corpus. Đối chiếu license/release cụ thể khi nhập; không xem GPL của repo là bằng chứng mọi file có cùng điều kiện |
| AIOps2020 | [NetManAIOps repo](https://github.com/NetManAIOps/AIOps-Challenge-2020-Data) | Nhận gói qua kênh nội bộ được duyệt. Không tự dùng link drive/login hoặc mirror chưa kiểm chứng; mapping và labels cần kiểm trên bản được cấp |
| Alibaba2021 | [Clusterdata](https://github.com/alibaba/clusterdata/tree/master/cluster-trace-microservices-v2021) | Local CSV adapter. Corpus lớn, không chạy fetchData.sh. Không có nhãn fault/root chuẩn cho bảng đang dùng; chỉ exploration |

RCAEval có 735 failure cases trên ba hệ thống, nhưng availability metric/log/trace khác theo suite/case. Lab chỉ dùng các resource metric của 15 case đã tải. Tên thuật toán trong lab là baseline nội bộ, không phải implementation BARO/RCD/TORAI chính thức.

LEMMA preprocessed tách metric và unstructured log theo pod; không mặc định mỗi gói preprocessed có trace. GAIA release cập nhật có thể khác bộ ban đầu, vì vậy kiểm file thật trước bật modality. TelecomTS có anomaly labels, không có root CNFC/VDU được xác minh cho mục tiêu của hệ OCS.

File `download_manifest.json` lưu URL pin, byte count, SHA256. RCAEval conversion manifest ghi file đầu vào, phép đổi sang 30s mean resource metrics và SHA đầu ra. File trong gói trích đoạn có chọn lọc, không đại diện phân phối đầy đủ và không phải bản mirror chính thức.

Không đưa các DOCX nội bộ, nội dung notebook nội bộ hoặc credential vào download request. Gói lab không sao chép các tài liệu nội bộ gốc. Nguồn hình ảnh trong shared chat không truy cập được nên không được ghi là đã kiểm chứng.
