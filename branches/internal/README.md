# internal

Chạy từ project root: `python -m pipelines.project --branch internal --profile efficient`.

Provenance: **synthetic_internal_demo**. `branch.json` chỉ đến adapter/config riêng; engine và EDA dùng chung.

Profile `full` thêm MLP/Autoencoder nếu task có benchmark. Không so trực tiếp F1 TelecomTS với MRR RCAEval.
