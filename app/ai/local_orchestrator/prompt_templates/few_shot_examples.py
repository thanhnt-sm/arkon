"""
Few-shot examples for MAP (extraction) and REFINE (wiki writing) phases.

All examples are ~200 tokens each. Stored as constants so they can be
referenced from multiple template builders without duplication.
"""

# ---------------------------------------------------------------------------
# MAP phase — extraction examples
# ---------------------------------------------------------------------------

MAP_EXAMPLE_1 = """\
INPUT (đoạn tiếng Anh về Transformer):
"The Transformer architecture, introduced by Vaswani et al. (2017), replaced recurrence with self-attention mechanisms, enabling parallelization and significantly improving performance on NLP tasks."

OUTPUT:
{
  "entities": [
    {
      "name_vi": "Kiến trúc Transformer",
      "name_en": "Transformer Architecture",
      "type": "tech",
      "definition_vi": "Mô hình mạng nơ-ron (neural network) dùng cơ chế tự chú ý (self-attention) thay vì hồi quy để xử lý chuỗi."
    }
  ],
  "claims": [
    {
      "text_vi": "Kiến trúc Transformer được Vaswani và cộng sự công bố năm 2017.",
      "evidence_quote": "introduced by Vaswani et al. (2017)",
      "confidence": 1.0
    },
    {
      "text_vi": "Transformer cho phép xử lý song song (parallelization), cải thiện đáng kể hiệu suất các tác vụ xử lý ngôn ngữ tự nhiên (NLP).",
      "evidence_quote": "enabling parallelization and significantly improving performance on NLP tasks",
      "confidence": 0.95
    }
  ],
  "relations": [
    {
      "subject": "Kiến trúc Transformer",
      "predicate_vi": "thay thế",
      "object": "cơ chế hồi quy bằng tự chú ý",
      "evidence_quote": "replaced recurrence with self-attention mechanisms"
    }
  ],
  "open_questions": ["Hiệu năng so với LSTM (Long Short-Term Memory) trên các benchmark cụ thể?"],
  "summary_vi": "Đoạn giới thiệu kiến trúc Transformer, nhấn mạnh ưu điểm song song hoá và cải thiện hiệu suất (NLP) so với mô hình hồi quy truyền thống."
}"""

MAP_EXAMPLE_2 = """\
INPUT (đoạn tiếng Anh về Docker):
"Docker uses OS-level virtualization to deliver software in packages called containers. Each container is isolated from others and bundles its own software, libraries, and configuration files."

OUTPUT:
{
  "entities": [
    {
      "name_vi": "Container",
      "name_en": "Container",
      "type": "tech",
      "definition_vi": "Gói phần mềm độc lập chứa ứng dụng, thư viện và cấu hình, chạy nhờ ảo hoá cấp hệ điều hành (OS-level virtualization)."
    },
    {
      "name_vi": "Docker",
      "name_en": "Docker",
      "type": "tech",
      "definition_vi": "Nền tảng đóng gói và chạy phần mềm dưới dạng container."
    }
  ],
  "claims": [
    {
      "text_vi": "Docker sử dụng ảo hoá cấp hệ điều hành (OS-level virtualization) để phân phối phần mềm.",
      "evidence_quote": "Docker uses OS-level virtualization to deliver software",
      "confidence": 1.0
    },
    {
      "text_vi": "Mỗi container được cách ly (isolated) với các container khác.",
      "evidence_quote": "Each container is isolated from others",
      "confidence": 1.0
    }
  ],
  "relations": [
    {
      "subject": "Container",
      "predicate_vi": "bao gồm",
      "object": "phần mềm, thư viện và file cấu hình",
      "evidence_quote": "bundles its own software, libraries, and configuration files"
    }
  ],
  "open_questions": ["Docker khác gì so với máy ảo (virtual machine) về hiệu suất?"],
  "summary_vi": "Đoạn mô tả Docker và khái niệm container: đơn vị phần mềm độc lập, cách ly, dùng ảo hoá hệ điều hành."
}"""

# ---------------------------------------------------------------------------
# REFINE phase — wiki paragraph examples
# ---------------------------------------------------------------------------

REFINE_EXAMPLE_1 = """\
EVIDENCE:
[E1] "Kubernetes was originally designed at Google and released as open source in 2014." — source_id=s001
[E2] "Kubernetes automates deployment, scaling, and management of containerized applications." — source_id=s002

OUTPUT (đoạn wiki):
## Lịch sử và mục đích (History and Purpose)

Kubernetes (K8s) là hệ thống điều phối container (container orchestration) mã nguồn mở ban đầu được thiết kế tại Google và công bố vào năm 2014. [E1] Hệ thống tự động hoá việc triển khai (deployment), mở rộng quy mô (scaling) và quản lý các ứng dụng đóng gói trong container. [E2]"""

REFINE_EXAMPLE_2 = """\
EVIDENCE:
[E1] "A REST API uses HTTP requests to perform CRUD operations: GET, POST, PUT, DELETE." — source_id=s010
[E2] "REST stands for Representational State Transfer, an architectural style for distributed systems." — source_id=s011

OUTPUT (đoạn wiki):
## Giao thức và thao tác (Protocol and Operations)

(REST) — viết tắt của Representational State Transfer — là phong cách kiến trúc (architectural style) cho hệ thống phân tán. [E2] Giao diện lập trình ứng dụng REST (REST API) dùng các yêu cầu (HTTP) để thực hiện bốn thao tác cơ bản (CRUD): lấy dữ liệu (`GET`), tạo mới (`POST`), cập nhật (`PUT`) và xoá (`DELETE`). [E1]"""
