import asyncio
import base64
import json
import os
import subprocess
import time
import urllib.request
import websockets

TARGET_URL = "http://127.0.0.1:8000"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "images")
os.makedirs(OUTPUT_DIR, exist_ok=True)

CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
USER_DATA = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "tubescholar_chrome_shot")

SAMPLE_NOTE_KO = """# 트랜스포머(Transformer)와 어텐션 메커니즘 기초 강의
**카테고리 원형**: `🧠 학술·강의형 (Academics & Lecture)`

> 📌 **핵심 개요 (Executive Summary)**: 오픈AI의 GPT 및 구글 Gemini 등 현대 거대 언어 모델(LLM)의 핵심 근간이 된 **Transformer 아키텍처**와 **Self-Attention 메커니즘**의 동작 원리를 다룹니다. 기존 순환 신경망(RNN)의 순차적 연산 한계를 극복하고 행렬 곱을 통한 대규모 병렬 학습을 실현한 배경과 Query, Key, Value의 수학적 개념을 체계적으로 해설합니다.

---

## 🎯 핵심 요약 (Key Takeaways)
- **병렬 연산 극대화**: 시간 순서대로 처리하던 RNN/LSTM과 달리, 문장 내 전체 단어를 한 번에 병렬 연산하여 GPU 학습 효율을 획기적으로 향상시켰습니다.
- **장거리 문맥 의존성(Long-Term Dependency) 해결**: 문장이 길어져도 정보 소실 없이 토큰 간의 직접적인 연결 통로를 제공합니다.
- **Query, Key, Value 메커니즘**: 검색 기준(Query)과 데이터 색인(Key)의 유사도를 바탕으로 실제 정보(Value)의 가중합을 도출합니다.

---

## ⚖️ 순환 신경망(RNN) vs 트랜스포머(Transformer) 비교표

| 비교 항목 | 순환 신경망 (RNN / LSTM) | 트랜스포머 (Transformer) |
| :--- | :--- | :--- |
| **연산 방식** | 순차 처리 (Sequential Step-by-Step) | **대규모 병렬 처리 (Full Parallelism)** |
| **시간 복잡도** | $O(N)$ (문장 길이에 비례한 계산 지연) | **$O(1)$ 연산 경로 (Attention $O(N^2)$)** |
| **장거리 기억력** | 거리가 멀어지면 기울기 소실(Vanishing Gradient) | **모든 단어 간 직접 어텐션 연결로 영구 보존** |
| **위치 정보 처리** | 입력 순서에 의해 자연스럽게 인식 | **Positional Encoding 벡터 합성으로 처리** |

---

## 🔍 심화 지식 (Deep Dive): 스케일드 닷 프로덕트 어텐션

> 📐 **공식 (Attention Formula)**:
> Attention(Q, K, V) = softmax(QK^T / √d_k) V

- **왜 $\\sqrt{d_k}$로 나누는가?**: 벡터 차원($d_k$)이 커질수록 내적 결과값의 분산이 극도로 커져 소프트맥스(Softmax) 함수의 기울기가 매우 작아지는 포화(Saturation) 현상이 발생합니다. 이를 방지하기 위해 표준편차를 1로 안정화시키는 스케일링 팩터 $\\sqrt{d_k}$를 적용합니다.

---

## 📖 핵심 용어 사전 (Glossary)

| 핵심 용어 | 영문 표기 | 상세 설명 |
| :--- | :--- | :--- |
| **쿼리** | Query (Q) | 현재 단어가 다른 단어들에게 던지는 질문 또는 검색 기준 벡터 |
| **키** | Key (K) | 각 단어가 자신이 어떤 특성을 가지고 있는지 설명하는 색인 레이블 |
| **값** | Value (V) | 검색 유사도 가중치에 따라 최종 합성될 실제 의미 정보 콘텐츠 |
| **멀티헤드** | Multi-Head | 여러 관점(문법, 의미, 어조 등)에서 단어 간 관계를 독립적으로 포착하는 기법 |

---

## ⏱️ 타임라인별 강의 핵심 노트
- [00:00] 🎬 **강의 도입**: 기존 자연어 처리 모델의 한계점과 어텐션의 등장 배경
- [02:15] 🔄 **RNN 병목**: 순차적 은닉 상태 전달 방식의 계산 지연과 장거리 기억 소실
- [05:30] 📐 **Self-Attention 수학적 원리**: Q, K, V 행렬 생성과 내적 유사도 스코어 계산
- [08:45] ⚡ **Multi-Head Attention**: 8개 이상의 독립된 헤드로 다각도 문맥 관계 학습
- [11:20] 📍 **Positional Encoding**: 삼각함수를 활용한 토큰 위치 임베딩 기법
- [13:50] 🚀 **요약 및 결론**: 현대 LLM 및 멀티모달 파운데이션 모델로의 진화

---

## 💡 이해도 점검 퀴즈 (Quiz)
1. **Q**: 어텐션 수식에서 $\\sqrt{d_k}$로 내적 값을 나누는 주된 이유는 무엇인가요?
   - *A*: 차원이 증가함에 따라 내적 값이 지나치게 커져 소프트맥스의 기울기 소멸 현상이 일어나는 것을 방지하기 위함입니다.
"""

SAMPLE_NOTE_EN = """# Lecture Note: Transformer Architecture & Attention Mechanism
**Category Archetype**: `🧠 Academics & Lecture`

> 📌 **Executive Summary**: This study note explores the foundational principles of the **Transformer Architecture** and **Self-Attention Mechanism**, the technological bedrock behind modern Large Language Models (LLMs) such as OpenAI GPT and Google Gemini. It systematically covers how dot-product attention eliminated the sequential constraints of Recurrent Neural Networks (RNNs) and enabled massive parallel training.

---

## 🎯 Key Takeaways
- **Massive Parallelism**: Unlike RNNs that process tokens sequentially, Transformers process all words simultaneously across GPU cores, dramatically slashing training times.
- **Solving Long-Term Dependencies**: Direct attention paths between arbitrary tokens eliminate information decay over long textual sequences.
- **Query, Key, and Value**: Retrieves contextual value representations by computing similarity scores between search targets (Queries) and index descriptors (Keys).

---

## ⚖️ Comparison Table: RNN vs. Transformer

| Dimension | Recurrent Neural Networks (RNN/LSTM) | Transformers |
| :--- | :--- | :--- |
| **Computation** | Sequential (Step-by-step token feeding) | **Fully Parallel Matrix Multiplication** |
| **Path Length** | $O(N)$ (Sequential latency grows with length) | **$O(1)$ Direct Connection ($O(N^2)$ Memory)** |
| **Long-Term Memory** | Suffers from vanishing/exploding gradients | **Direct attention bridges retain full context** |
| **Positional Awareness**| Implicit via input timing | **Explicit via Positional Encodings** |

---

## 🔍 Deep Dive: Scaled Dot-Product Attention

> 📐 **Formula**:
> Attention(Q, K, V) = softmax(QK^T / √d_k) V

- **Why divide by $\\sqrt{d_k}$?**: For large projection dimensions, the dot products grow large in magnitude, pushing the softmax function into regions with extremely small gradients. Scaling by $1/\\sqrt{d_k}$ stabilizes the variance to 1 and preserves active gradient flow.

---

## 📖 Technical Glossary

| Term | Symbol | Definition |
| :--- | :--- | :--- |
| **Query** | Q | The representation vector asking "what information is relevant to me?" |
| **Key** | K | The descriptor label vector indicating "what attributes I contain" |
| **Value** | V | The content vector that gets aggregated according to attention weights |
| **Multi-Head** | MHA | Parallel attention heads capturing diverse linguistic perspectives simultaneously |

---

## ⏱️ Timestamped Timeline Highlights
- [00:00] 🎬 **Introduction**: Limitations of sequential models & the motivation for attention
- [02:15] 🔄 **The RNN Bottleneck**: Why sequential hidden-state recurrence fails at scale
- [05:30] 📐 **Self-Attention Mathematics**: Generating Q, K, V matrices and computing dot-products
- [08:45] ⚡ **Multi-Head Attention**: Splitting subspaces to attend to multifaceted relationships
- [11:20] 📍 **Positional Encodings**: Injecting word order information into order-invariant attention
- [13:50] 🚀 **Summary & Outlook**: Foundations of modern multimodal architectures
"""

SUBTITLES_DATA = [
    { "start": 0.0, "duration": 3.5, "end": 3.5, "timestamp": "00:00", "text": "Welcome to today's lecture on Transformer architectures and Self-Attention.", "ko_text": "트랜스포머 아키텍처와 Self-Attention에 대한 오늘 강의에 오신 것을 환영합니다." },
    { "start": 3.5, "duration": 4.2, "end": 7.7, "timestamp": "00:03", "text": "Before Transformers, recurrent neural networks struggled with long sequence bottlenecks.", "ko_text": "트랜스포머 등장 이전의 순환 신경망은 긴 시퀀스에서의 병목 현상으로 어려움을 겪었습니다." },
    { "start": 7.7, "duration": 4.5, "end": 12.2, "timestamp": "00:07", "text": "The attention mechanism computes relational weights between every pair of words in context.", "ko_text": "어텐션 메커니즘은 문맥 내 모든 단어 쌍 사이의 상관 관계 가중치를 계산합니다." },
    { "start": 12.2, "duration": 4.0, "end": 16.2, "timestamp": "00:12", "text": "Mathematically, we project input embeddings into Query, Key, and Value vectors.", "ko_text": "수학적으로 입력 임베딩을 Query, Key, Value 벡터로 투영합니다." },
    { "start": 16.2, "duration": 3.8, "end": 20.0, "timestamp": "00:16", "text": "The dot product of Query and Key produces the raw attention alignment score.", "ko_text": "Query와 Key의 내적은 원시 어텐션 정렬 점수를 생성합니다." },
    { "start": 20.0, "duration": 4.2, "end": 24.2, "timestamp": "00:20", "text": "We scale this dot product by square root of d_k to prevent gradient vanishing.", "ko_text": "기울기 소실을 방지하기 위해 이 내적 값을 d_k의 제곱근으로 스케일링합니다." },
    { "start": 24.2, "duration": 4.0, "end": 28.2, "timestamp": "00:24", "text": "Applying Softmax normalizes these scores into a valid probability distribution.", "ko_text": "소프트맥스를 적용하여 이 점수들을 유효한 확률 분포로 정규화합니다." },
    { "start": 28.2, "duration": 4.5, "end": 32.7, "timestamp": "00:28", "text": "Finally, we compute a weighted sum of the Value vectors to form the contextual output.", "ko_text": "마지막으로 Value 벡터들의 가중합을 계산하여 문맥이 반영된 출력을 완성합니다." },
    { "start": 32.7, "duration": 4.0, "end": 36.7, "timestamp": "00:32", "text": "This parallel formulation enables modern LLMs to train efficiently on massive datasets.", "ko_text": "이러한 병렬 연산 구조 덕분에 현대 LLM은 대규모 데이터셋을 매우 효율적으로 학습할 수 있습니다." }
]

LIBRARY_ITEMS = [
    {
        "id": "demo_transformer",
        "title": "AI & Deep Learning: Transformer & Attention Mechanism Explained",
        "channel": "TubeScholar Academy",
        "date": "2026-10-06 15:30:00",
        "icon": "🎓"
    },
    {
        "id": "demo_system_design",
        "title": "System Design: High-Throughput Distributed Microservices Architecture",
        "channel": "Tech Systems Lab",
        "date": "2026-10-05 18:20:00",
        "icon": "🏗️"
    },
    {
        "id": "demo_python_async",
        "title": "Modern Python Architecture: Event Loops, AsyncIO & Concurrency",
        "channel": "Python Software Guild",
        "date": "2026-10-05 14:15:00",
        "icon": "🐍"
    },
    {
        "id": "demo_algorithms",
        "title": "Advanced Graph Algorithms: Shortest Paths, Trees & Optimization",
        "channel": "Algorithm Foundations",
        "date": "2026-10-04 20:10:00",
        "icon": "⚡"
    },
    {
        "id": "demo_vector_db",
        "title": "Database Internals: B-Tree Indexing vs High-Dimensional Vector DBs",
        "channel": "Data Engineering Hub",
        "date": "2026-10-04 16:45:00",
        "icon": "🗄️"
    },
    {
        "id": "demo_vit_vision",
        "title": "Computer Vision: From ResNet to Vision Transformers (ViT)",
        "channel": "Vision & AI Research",
        "date": "2026-10-03 11:30:00",
        "icon": "👁️"
    }
]

print("Script template ready.")
