# Kiến Trúc Transformer trong Học Sâu

> **Nguồn tham khảo:** Tài liệu nội bộ — dùng để kiểm thử pipeline MRP với ngữ liệu tiếng Việt ~5 000 token.
> Phiên bản: 1.0 | Cập nhật: 2026-05-24

---

## Tổng quan

Mô hình Transformer (Transformer / TF) là một kiến trúc học sâu (Deep Learning / DL) được giới thiệu lần đầu trong bài báo nổi tiếng *"Attention Is All You Need"* của Vaswani và cộng sự vào năm 2017. Kể từ đó, Transformer đã trở thành nền tảng cho hầu hết các hệ thống xử lý ngôn ngữ tự nhiên (Natural Language Processing / NLP) hiện đại, bao gồm các mô hình ngôn ngữ lớn (Large Language Model / LLM) như GPT-4, Claude, Gemini và Llama.

Điểm đột phá cốt lõi của Transformer là cơ chế chú ý tự hồi quy (Self-Attention Mechanism), cho phép mô hình cân nhắc mối liên hệ giữa tất cả các từ trong chuỗi đầu vào cùng một lúc, thay vì xử lý tuần tự như kiến trúc mạng nơ-ron hồi quy (Recurrent Neural Network / RNN) trước đây. Nhờ đặc tính song song hóa (Parallelization) này, Transformer có thể được huấn luyện hiệu quả trên các tập dữ liệu khổng lồ bằng phần cứng chuyên dụng (Graphics Processing Unit / GPU) và bộ xử lý ma trận thần kinh (Neural Processing Unit / NPU).

Kiến trúc Transformer được ứng dụng rộng rãi trong nhiều lĩnh vực: dịch máy (Machine Translation / MT), tóm tắt văn bản (Text Summarization), trả lời câu hỏi (Question Answering / QA), sinh mã nguồn (Code Generation), xử lý hình ảnh (Image Processing) qua mô hình ViT (Vision Transformer / ViT), và gần đây là các hệ thống đa phương thức (Multimodal System) kết hợp văn bản và hình ảnh.

---

## Lịch sử Phát triển

### Bối cảnh trước Transformer (2014–2017)

Trước khi Transformer ra đời, cộng đồng nghiên cứu trí tuệ nhân tạo (Artificial Intelligence / AI) chủ yếu dựa vào hai nhóm kiến trúc chính:

1. **Mạng nơ-ron hồi quy (RNN / LSTM / GRU):** Mô hình của Hochreiter & Schmidhuber (1997) giới thiệu bộ nhớ ngắn-dài hạn (Long Short-Term Memory / LSTM) để giải quyết bài toán gradient biến mất (Vanishing Gradient Problem). Tuy nhiên, LSTM vẫn xử lý tuần tự và không tận dụng được tính song song của phần cứng hiện đại.

2. **Mạng tích chập (Convolutional Neural Network / CNN):** Được dùng trong các hệ thống dịch ngôn ngữ như ConvS2S (Facebook AI Research, 2017), CNN có tốc độ nhanh hơn RNN nhưng khó nắm bắt phụ thuộc tầm xa (Long-Range Dependency) trong câu.

Cơ chế chú ý (Attention Mechanism) ban đầu được đề xuất bởi Bahdanau và cộng sự năm 2015 như một phần bổ sung cho mô hình mã hóa–giải mã (Encoder-Decoder / Seq2Seq) dựa trên LSTM. Cơ chế này cho phép bộ giải mã (Decoder) tập trung vào các phần liên quan của câu nguồn khi tạo từng từ đầu ra. Dù hiệu quả, Attention khi đó vẫn phụ thuộc vào nền tảng RNN.

### Ra đời của Transformer (2017)

Bài báo *"Attention Is All You Need"* (Vaswani et al., NeurIPS 2017) loại bỏ hoàn toàn thành phần hồi quy (Recurrence) và tích chập, thay vào đó xây dựng toàn bộ kiến trúc xung quanh cơ chế chú ý đa đầu (Multi-Head Attention / MHA). Kết quả thực nghiệm trên bộ dữ liệu WMT En→De đạt điểm BLEU 28.4, vượt mọi mô hình trước đó với thời gian huấn luyện ít hơn đáng kể.

### Các cột mốc quan trọng (2018–nay)

| Năm | Mô hình | Tổ chức | Cột mốc |
|-----|---------|---------|---------|
| 2018 | BERT | Google | Tiền huấn luyện hai chiều (Bidirectional Pre-training) |
| 2019 | GPT-2 | OpenAI | Sinh văn bản zero-shot quy mô lớn |
| 2020 | GPT-3 | OpenAI | 175B tham số, few-shot learning mạnh |
| 2021 | DALL-E | OpenAI | Transformer cho sinh ảnh từ văn bản |
| 2022 | ChatGPT | OpenAI | Tinh chỉnh theo phản hồi người (RLHF) |
| 2023 | Llama 2 | Meta | Mô hình mã nguồn mở tham số lớn |
| 2024 | Gemini Ultra | Google | Transformer đa phương thức hàng đầu |
| 2025 | Qwen3 | Alibaba | Kiến trúc hỗn hợp chuyên gia (MoE) hiệu năng cao |

---

## Kiến Trúc Chi Tiết

### Tổng quan cấu trúc

Transformer gốc theo kiến trúc mã hóa–giải mã (Encoder-Decoder). Bộ mã hóa (Encoder) nhận chuỗi đầu vào và tạo ra biểu diễn ngữ nghĩa ẩn (Contextual Representation). Bộ giải mã (Decoder) nhận biểu diễn đó cùng với chuỗi đầu ra đã tạo, sinh từ tiếp theo theo xác suất có điều kiện.

Mỗi khối Transformer (Transformer Block / Layer) gồm hai thành phần chính:

1. **Chú ý đa đầu (Multi-Head Attention / MHA):** Tính toán mối liên hệ giữa tất cả các vị trí trong chuỗi.
2. **Mạng nơ-ron truyền thẳng (Feed-Forward Network / FFN):** Biến đổi phi tuyến từng vị trí độc lập.

Cả hai thành phần đều sử dụng kết nối tắt (Residual Connection / Skip Connection) và chuẩn hóa lớp (Layer Normalization / LayerNorm) để ổn định quá trình huấn luyện gradient sâu.

### Cơ chế chú ý tự hồi quy (Self-Attention)

Cho chuỗi đầu vào gồm n token, mỗi token được biểu diễn bằng vector nhúng (Embedding Vector) có chiều d_model. Ba ma trận chiếu (Projection Matrix) học được biến đổi embedding thành ba không gian:

- **Q (Query / Truy vấn):** Đại diện cho câu hỏi "token này muốn chú ý tới cái gì?"
- **K (Key / Khóa):** Đại diện cho "token này có thể cung cấp thông tin gì?"
- **V (Value / Giá trị):** Thông tin thực sự truyền đi khi chú ý được kích hoạt.

Trọng số chú ý (Attention Weight) được tính bằng:

```
Attention(Q, K, V) = softmax(QKᵀ / √d_k) · V
```

Phép chia √d_k (căn bậc hai của chiều khóa) ngăn gradient biến mất khi d_k lớn — đây là kỹ thuật Scaled Dot-Product Attention.

### Chú ý đa đầu (Multi-Head Attention / MHA)

Thay vì tính một chú ý duy nhất, MHA chiếu Q, K, V xuống h không gian con (Head) song song. Mỗi đầu học một kiểu liên hệ khác nhau: một đầu có thể học cú pháp (Syntactic), đầu khác học ngữ nghĩa (Semantic), đầu khác học coreference. Kết quả từ h đầu được ghép lại (Concatenate) và chiếu ngược lên d_model:

```
MultiHead(Q, K, V) = Concat(head_1, ..., head_h) · W_O
where head_i = Attention(Q·W_Q_i, K·W_K_i, V·W_V_i)
```

Trong kiến trúc gốc, d_model = 512, h = 8, d_k = d_v = 64. Các mô hình hiện đại như GPT-4 sử dụng d_model = 12288, h = 96, cùng với biến thể chú ý nhóm truy vấn (Grouped Query Attention / GQA) để giảm bộ nhớ đệm KV (KV Cache).

### Mạng truyền thẳng vị trí (Position-wise FFN)

FFN áp dụng hai phép biến đổi tuyến tính với hàm kích hoạt phi tuyến ở giữa:

```
FFN(x) = max(0, x·W_1 + b_1) · W_2 + b_2
```

Chiều ẩn d_ff thường bằng 4 × d_model (2048 trong Transformer gốc). Các mô hình hiện đại dùng hàm SwiGLU hoặc GeGLU thay cho ReLU để tăng hiệu năng.

### Mã hóa vị trí (Positional Encoding / PE)

Vì Transformer xử lý song song, cơ chế chú ý không phân biệt vị trí các token. Do đó, mã hóa vị trí (Positional Encoding) được cộng vào embedding đầu vào. Bài báo gốc dùng sóng sin-cos (Sinusoidal PE):

```
PE(pos, 2i)   = sin(pos / 10000^(2i/d_model))
PE(pos, 2i+1) = cos(pos / 10000^(2i/d_model))
```

Các mô hình hiện đại sử dụng biến thể RoPE (Rotary Positional Embedding) cho phép mở rộng độ dài ngữ cảnh (Context Length Extension) hiệu quả hơn.

### Biểu đồ kiến trúc tổng thể

![Biểu đồ kiến trúc](sample-chart.png)

*Hình 1: Sơ đồ tổng thể kiến trúc Transformer mã hóa–giải mã. Trái: Encoder stack. Phải: Decoder stack. Mũi tên màu xanh biểu thị luồng dữ liệu qua các khối Self-Attention và FFN.*

---

## Các Biến Thể Kiến Trúc

### Chỉ Encoder (Encoder-Only)

Mô hình điển hình: BERT (Bidirectional Encoder Representations from Transformers). Encoder-only phù hợp với các tác vụ phân loại (Classification), gán nhãn chuỗi (Sequence Labeling), và trích xuất đặc trưng (Feature Extraction). BERT huấn luyện bằng hai mục tiêu: dự đoán token bị che (Masked Language Modeling / MLM) và dự đoán câu tiếp theo (Next Sentence Prediction / NSP).

Phiên bản tiếng Việt nổi bật: PhoBERT (VinAI Research, 2020) — được tiền huấn luyện trên 20GB văn bản tiếng Việt, hiện là backbone chuẩn cho các tác vụ NLP tiếng Việt trong môi trường production.

### Chỉ Decoder (Decoder-Only)

Mô hình điển hình: GPT (Generative Pre-trained Transformer) — chuỗi từ GPT-1 đến GPT-4. Decoder-only dùng chú ý nhân quả (Causal Attention / Autoregressive Attention) — mỗi token chỉ chú ý các token phía trước. Phù hợp với sinh ngôn ngữ (Language Generation), hoàn thiện mã (Code Completion), hội thoại (Dialogue).

Kích thước KV Cache (KV Cache Size) tăng tuyến tính theo độ dài ngữ cảnh — đây là điểm thắt cổ chai (Bottleneck) chính về bộ nhớ khi triển khai LLM.

### Kiến trúc hỗn hợp chuyên gia (Mixture of Experts / MoE)

Thay vì kích hoạt toàn bộ FFN, MoE có một mạng định tuyến (Router / Gating Network) chọn k chuyên gia (Expert) trong số E chuyên gia cho mỗi token. Ví dụ: Mixtral 8×7B có 8 chuyên gia, mỗi token dùng 2, tham số tổng ~47B nhưng tham số kích hoạt (Active Parameters) chỉ ~13B — chi phí suy luận (Inference Cost) thấp hơn mô hình dày (Dense Model) cùng chất lượng.

### Vision Transformer (ViT)

ViT (Dosovitskiy et al., 2020) áp dụng Transformer cho ảnh bằng cách chia ảnh thành các mảnh (Patch) 16×16 pixel, làm phẳng và chiếu thành chuỗi embedding. Kết quả: ViT vượt CNN (ResNet) trên ImageNet khi được tiền huấn luyện trên tập dữ liệu đủ lớn.

---

## Ứng Dụng Thực Tế

### Xử lý ngôn ngữ tự nhiên tiếng Việt

Cộng đồng NLP Việt Nam đã ứng dụng Transformer vào nhiều bài toán thực tế:

- **Dịch máy (Machine Translation):** VinAI Translate đạt BLEU >30 trên cặp VI↔EN.
- **Nhận dạng thực thể có tên (Named Entity Recognition / NER):** PhoBERT fine-tuned đạt F1 >93% trên tập PhoNER.
- **Phân tích cảm xúc (Sentiment Analysis / SA):** Ứng dụng rộng trong hệ thống quản lý thương hiệu (Brand Management).
- **Chatbot tiếng Việt (Vietnamese Chatbot):** Nhiều ngân hàng và sàn thương mại điện tử triển khai Transformer-based chatbot phục vụ khách hàng.

### Sinh mã nguồn (Code Generation)

GitHub Copilot, Amazon CodeWhisperer, và Cursor AI đều dựa trên kiến trúc Decoder-only Transformer (Codex, Claude, GPT-4) được fine-tuned trên kho mã nguồn khổng lồ. Thực nghiệm nội bộ cho thấy Copilot hoàn thiện >40% hàm Python đúng ngay lần gợi ý đầu tiên (Pass@1).

### Hệ thống RAG trong doanh nghiệp

Kiến trúc RAG (Retrieval-Augmented Generation) kết hợp Transformer embedding (tạo vector đặc trưng tài liệu) với LLM decoder (sinh câu trả lời dựa trên ngữ cảnh truy xuất). Arkon sử dụng mô hình embedding GTE-Qwen2-1.5B để lập chỉ mục (Indexing) tài liệu nội bộ và Qwen3 MoE để sinh wiki page.

### Ứng dụng thị giác máy tính (Computer Vision / CV)

Các mô hình đa phương thức như Qwen2.5-VL (Vision-Language) kết hợp ViT encoder và LLM decoder. Chúng có thể mô tả ảnh, trả lời câu hỏi về hình ảnh (Visual QA / VQA), đọc OCR (Optical Character Recognition) tiếng Việt, và phân tích biểu đồ (Chart Analysis) — tác vụ cốt lõi trong pipeline MRP của Arkon.

![Sơ đồ luồng dữ liệu](sample-vi-screenshot.png)

*Hình 2: Sơ đồ luồng dữ liệu trong pipeline Arkon MRP. Giai đoạn Vision Caption dùng Qwen2.5-VL để trích xuất thông tin từ ảnh trước khi đưa vào giai đoạn MAP.*

---

## Hạn Chế và Thách Thức

### Chi phí tính toán bậc hai (Quadratic Complexity)

Chú ý tự hồi quy (Self-Attention) có độ phức tạp O(n²·d) theo độ dài chuỗi n. Với n = 128 000 token (ngữ cảnh Claude 3.5), ma trận chú ý chứa ~16 tỷ phần tử — không thể lưu vào bộ nhớ GPU thông thường. Các giải pháp:

- **Flash Attention (Dao et al., 2022):** Tính toán tile-by-tile trực tiếp trên SRAM, tiết kiệm 5–20× bộ nhớ HBM (High Bandwidth Memory).
- **Chú ý thưa (Sparse Attention):** Chỉ tính chú ý trên tập con token (Longformer, BigBird).
- **Chú ý tuyến tính (Linear Attention):** Xấp xỉ softmax attention bằng kernel function, giảm về O(n·d).

### Vấn đề ảo giác (Hallucination)

LLM dựa trên Transformer có xu hướng sinh ra thông tin sai lệch với độ tin cậy cao (Confident Hallucination). Nguyên nhân: mô hình tối ưu hóa xác suất token tiếp theo (Next-Token Probability) mà không có cơ chế kiểm tra thực tế (Grounding). Arkon giải quyết bằng giai đoạn VERIFY trong pipeline MRP — kiểm tra chéo (Cross-Check) nội dung wiki page với nguồn gốc.

### Bộ nhớ ngữ cảnh (Context Memory)

Transformer thuần túy không có trạng thái dài hạn (Long-Term State) ngoài ngữ cảnh hiện tại. Khi tài liệu vượt quá cửa sổ ngữ cảnh (Context Window), thông tin bị cắt bỏ. Các giải pháp nghiên cứu: bộ nhớ ngoại vi (External Memory), Mamba (State Space Model / SSM), và kiến trúc hồi quy Transformer (Recurrent Transformer như RWKV).

### Chi phí suy luận và độ trễ

Với LLM 30B+ tham số, mỗi token sinh ra cần ~60 tỷ phép nhân-cộng dấu phẩy động (FLOP). Trên M1 Max 32GB (405 GB/s memory bandwidth), tốc độ lý thuyết ~6–8 token/giây với mô hình 4-bit quantized. Trong thực tế, ngữ cảnh dài làm chậm do KV Cache I/O — điểm thắt cổ chai cần giám sát trong môi trường sản xuất (Production Monitoring).

### Phân biệt ngôn ngữ (Language Discrimination)

Dữ liệu tiền huấn luyện (Pre-training Data) của hầu hết LLM chủ yếu là tiếng Anh (~50–70%). Tiếng Việt chiếm ~0.5–1%. Hệ quả: chất lượng sinh văn bản và lý luận (Reasoning) tiếng Việt thấp hơn tiếng Anh. Giải pháp: tinh chỉnh (Fine-tuning) trên tập dữ liệu VI thuần, dùng mô hình đa ngôn ngữ (Multilingual) như Qwen (Alibaba) được huấn luyện mạnh trên tiếng Trung và tiếng Việt.

---

## Xu Hướng Nghiên Cứu Hiện Tại

### Kiến trúc lai (Hybrid Architecture)

Nhiều nghiên cứu kết hợp Transformer với State Space Model (SSM như Mamba): xử lý ngữ cảnh cực dài với chi phí O(n) thay vì O(n²). Ví dụ: Jamba (AI21 Labs, 2024) xen kẽ khối Mamba và khối Attention.

### Lượng tử hóa (Quantization)

Giảm độ chính xác (Precision) từ FP32 → FP16 → INT8 → 4-bit (GPTQ, AWQ, GGUF) cho phép triển khai LLM lớn trên phần cứng tiêu dùng (Consumer Hardware). MLX (Apple Machine Learning Exchange) tối ưu cho chip Apple Silicon sử dụng 4-bit mixed-precision quantization với Metal Performance Shaders (MPS) — giải pháp triển khai cục bộ (Local Deployment) của Arkon.

### Tăng cường bằng công cụ (Tool Use / Function Calling)

LLM hiện đại được fine-tuned để gọi hàm ngoại vi (External Function) — tìm kiếm web, tra cứu cơ sở dữ liệu, thực thi mã — qua giao thức chuẩn (JSON Schema). Claude của Anthropic và GPT-4o của OpenAI đều hỗ trợ tool calling với độ chính xác cao, là nền tảng cho các hệ thống tác nhân AI (AI Agent System).

### Học tăng cường từ phản hồi người (RLHF / RLAIF)

Sau khi tiền huấn luyện, LLM được tinh chỉnh bằng RLHF (Reinforcement Learning from Human Feedback) hoặc RLAIF (RL from AI Feedback) để tuân theo hướng dẫn (Instruction Following), an toàn (Safety), và hữu ích (Helpfulness). Thuật toán PPO (Proximal Policy Optimization) và DPO (Direct Preference Optimization) là hai phương pháp phổ biến nhất.

---

## Tài Liệu Tham Khảo

1. Vaswani, A., et al. (2017). *Attention Is All You Need*. NeurIPS 2017.
2. Devlin, J., et al. (2018). *BERT: Pre-training of Deep Bidirectional Transformers*. NAACL 2019.
3. Brown, T., et al. (2020). *Language Models are Few-Shot Learners*. NeurIPS 2020.
4. Dao, T., et al. (2022). *FlashAttention: Fast and Memory-Efficient Exact Attention*. NeurIPS 2022.
5. Nguyen, D. Q., et al. (2020). *PhoBERT: Pre-trained Language Models for Vietnamese*. EMNLP 2020 Findings.
6. Dosovitskiy, A., et al. (2020). *An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale*. ICLR 2021.
7. Gu, A., & Dao, T. (2023). *Mamba: Linear-Time Sequence Modeling with Selective State Spaces*. arXiv 2312.00752.

---

*Tài liệu này được tạo cho mục đích kiểm thử pipeline MRP của hệ thống Arkon. Nội dung mang tính bách khoa (Encyclopedic) và phù hợp để kiểm tra định dạng tiếng Việt, khả năng trích xuất thực thể, và sinh wiki page đa chủ đề.*
