---
license: mit
---
# 📡 TelecomTS: A Multi-Modal Telecom Dataset
<p align="center">
  <a href="https://icml.cc/Conferences/2026"><img alt="ICML 2026" src="https://img.shields.io/badge/ICML-2026-blue.svg"></a>
  <a href="https://arxiv.org/abs/2510.06063"><img alt="arXiv" src="https://img.shields.io/badge/arXiv-2510.06063-b31b1b.svg"></a>
  <a href="https://github.com/Ali-maatouk/TelecomTS">
  <img alt="GitHub" src="https://img.shields.io/badge/GitHub-TelecomTS-181717?logo=github">
  </a>
  <img alt="License" src="https://img.shields.io/badge/license-MIT-green.svg">
</p>

**TelecomTS** is a large-scale, high-resolution, multi-modal dataset derived from a **5G telecommunications testbed**. It is the first public observability dataset to preserve **deanonymized** observability metrics with **absolute scale information**, encompassing by design various downstream tasks beyond forecasting such as **anomaly detection, root-cause analysis, and multi-modal reasoning**.

Observability data, particularly in telecommunications, differs fundamentally from conventional time series (e.g., weather, finance) by being:
- **Zero-inflated**
- **Highly stochastic and bursty**
- **Structurally noisy with minimal discernible temporal patterns**

## 🚀 Key Features
- **32k Data Samples**
- **1M+ Observations** from a live 5G network
- **Multi-modal inputs**:
  - Time series KPIs across PHY, MAC, and network layers
  - Environment descriptions and natural-language Q&A pairs
- **Absolute scale preserved** (no normalization/anonymization)
- **Real and synthetic anomalies**: 10 synthetic types grounded in telecom literature plus one real anomaly (jamming) collected over the air
- **Reasoning traces**: explicit chain-of-thought traces attached to `network` and `anomalies` Q&A entries, for reasoning-aware fine-tuning and RL
- **Downstream tasks supported**:
  - 🔎 **Anomaly detection** 
  - 🛠️ **Root-cause analysis** 
  - ⏱️ **Anomaly duration localization** 
  - 📈 **Forecasting / reconstruction** 
  - 🤖 **Time series and network-level Q&A** 
- **Labels provided**: zone, application, mobility, congestion state, anomaly presence

## 📊 Statistics

| Statistic                | Description                  | Count                                      |
|:-------------------------|:-----------------------------|:-------------------------------------------|
| **Time Series Samples**  | Total samples                | 32,000                                     |
|                          | Sample length                | 128                                        |
| **Channels**             | Total channels               | 18                                         |
|                          | Channel types                | 10 float, 6 integer, 2 categorical         |
| **Anomalies**            | Anomaly types                | 11                                         |
| **Q&A Categories**       | Time Series Q&A categories   | 64                                         |
|                          | Network-Level Q&A categories | 4                                          |
|                          | Anomalies Q&A categories     | 3                                          |
| **Total QA Size**        | Total QA instances           | **2,210,185**                              |

## 📂 Dataset Structure

The main dataset consists of JSONL files containing chunked time series (128 timesteps each) along with multi-modal information. Each sample within the JSONL files includes:

- **start_time / end_time** — temporal boundaries of the chunk
- **sampling_rate_hz** — number of timesteps per second 
- **description** — natural-language summary of the network environment and time series behaviors
- **KPIs** — key performance indicator names and values
- **anomalies** — existence, type, duration, affected KPIs, and troubleshooting tickets
- **statistics** — mean, variance, trend, and periodicity for each KPI
- **labels** — contextual metadata (zone, application, mobility, congestion, anomaly presence)
- **QnA** — natural-language Q&A over the sample, grouped into `timeseries`, `network`, and `anomalies` subcategories. Each entry of has the following structure:

  ```json
  { "q": "What activity was the user engaged in?",
    "a": "Twitch",
    "reasoning": "Sustained downlink throughput in the 2–4 Mbps range with periodic UDP bursts and stable RSRP is consistent with live video streaming..." }
  ```

  The `reasoning` field, present in the last two subcategories, contains an explicit reasoning trace that reveals the intermediate decision-making steps used to derive the final answer. 

Beyond the main dataset, each scenario also includes:

- **`description.txt`** – textual description of the network environment
- **`metrics.csv`** – raw observations for the scenario

## 🧪 Installation & Usage

### Install 🤗 Datasets
```bash
pip install datasets
```

### Load the Dataset
```python
from datasets import load_dataset

# Load the full dataset
dataset = load_dataset(
          "AliMaatouk/TelecomTS",
          data_files={"full": "**/chunked.jsonl"}
)

print(dataset)
```

### Inspect a Sample
```python
sample = dataset["full"][0]
print(sample.keys())
# dict_keys(['start_time', 'end_time', 'sampling_rate', 'KPIs', 'description', 'anomalies', 'statistics', 'labels', 'QnA'])
```


## Citation

You can find the paper with all details at https://arxiv.org/abs/2510.06063. Please cite it as follows:

```bib
@misc{feng2025telecomtsmultimodalobservabilitydataset,
      title={TelecomTS: A Multi-Modal Observability Dataset for Time Series and Language Analysis}, 
      author={Austin Feng and Andreas Varvarigos and Ioannis Panitsas and Daniela Fernandez and Jinbiao Wei and Yuwei Guo and Jialin Chen and Ali Maatouk and Leandros Tassiulas and Rex Ying},
      year={2025},
      eprint={2510.06063},
      archivePrefix={arXiv},
      primaryClass={cs.AI},
      url={https://arxiv.org/abs/2510.06063}, 
}
```
