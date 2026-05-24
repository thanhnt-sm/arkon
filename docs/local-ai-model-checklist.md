# Local AI Model Setup & LM Studio Configuration

## Express Setup (for experienced users)

```bash
# 1. Install LM Studio (lmstudio.ai) ≥ 0.4.x
# 2. Download 3 models in UI:
#    - Qwen2.5-VL-32B-Instruct-4bit (vision, ~19GB)
#    - Qwen3.6-35B-A3B-4bit-DWQ (main LLM, ~21GB)
#    - gte-Qwen2-1.5B-instruct (embedding in arkon Python, NOT LM Studio)
# 3. Per-model in LM Studio UI: Advanced → K/V Cache Type = q8_0
# 4. Developer tab → Start Server → allow CORS → listen 0.0.0.0:1234
# 5. Login arkon admin → /admin/local-ai → Mode: Max → Save → Test Connection
# 6. Submit 1 small wiki source via MRP → verify output in /wiki
```

---

## Full Step-by-Step Guide

### Step 1: Install LM Studio

1. Download [LM Studio](https://lmstudio.ai) version **≥ 0.4.x** (May 2026)
2. macOS: drag `LMStudio.app` to Applications folder
3. Windows/Linux: follow installer prompts
4. Launch LM Studio; verify version in Settings → About

**Why:** LM Studio 0.4.x includes MLX backend for M1/M2/M3 Mac + REST API with CORS support.

---

### Step 2: Download Vision Model

1. Open LM Studio
2. Click **Models** (left sidebar)
3. Search bar: paste `mlx-community/Qwen2.5-VL-32B-Instruct-4bit`
4. Click the model card → **Download**
5. Wait 15–20 min for ~19GB download (on fast connection; slower on home internet)
6. Status should show ✓ Downloaded when complete

**Fallback model** (if space-constrained or OOM): `mlx-community/Qwen2.5-VL-7B-Instruct-8bit` (~14GB)

---

### Step 3: Download Main LLM Model

1. In LM Studio Models search, paste `mlx-community/Qwen3.6-35B-A3B-4bit-DWQ`
2. **IMPORTANT:** Verify this exact repo exists on [HuggingFace](https://huggingface.co/mlx-community)
   - If not found, use the confirmed fallback: `mlx-community/Qwen3-32B-Instruct-4bit` (dense, ~18GB)
3. Click the model card → **Download**
4. Wait 20–25 min for ~21GB download
5. Status ✓ Downloaded

**Why Qwen3.6-35B-A3B:** Mixture-of-Experts (35B total, 3B active params), ~50 tok/s on M1 Max, superior reasoning vs dense models. Falls back to Qwen3-32B if unavailable.

---

### Step 4: Download Embedding Model

1. Search: `Alibaba-NLP/gte-Qwen2-1.5B-instruct`
2. Click → **Download**
3. Wait ~5 min for ~2GB download
4. Status ✓ Downloaded

**Note:** Embedding runs in **arkon Python process** (via `sentence-transformers` library), NOT in LM Studio. This saves a model slot and allows task-specific retrieval prompting.

---

### Step 5: Configure Per-Model K/V Quantization

**CRITICAL STEP:** K/V cache quantization q8_0 **must be set manually in LM Studio UI**—it is not exposed via SDK.

For each of the 3 models (vision, main LLM, embedding):

1. In LM Studio, go to **My Models** (or Models → Downloaded)
2. Find the model card (e.g., Qwen2.5-VL-32B-Instruct-4bit)
3. Right-click (or click ⋮) → **Model Config** or **Edit Config**
4. Open **Advanced** section
5. Look for:
   - **K/V Cache Type** → select `q8_0` (instead of default `f16`)
   - **Flash Attention** → toggle ON (if present)
   - **Context Length** → set to recommended per-phase:
     * Vision: 8192
     * Main LLM: 32768
     * Embedding: (default)
   - **GPU Layers** → set to 100 or "All" (maximize GPU compute)
6. Click **Save** or **Apply**
7. **Repeat for all 3 models**

<!-- SCREENSHOT: lmstudio-kv-quant-ui.png (operator fill in) -->
*Expected: Model card shows "q8_0" badge in config summary; hover over it confirms "K/V Cache Type: q8_0"*

**Impact:** K/V quantization saves ~25–30% memory + ~10–15% speed improvement. **Without this step, inference will be slow (6–10 tok/s vs. expected 50 tok/s).**

---

### Step 6: Verify Downloaded Models

1. In LM Studio, click **Models**
2. Switch to **Downloaded** or **My Models** tab
3. You should see 3 cards:
   - Qwen2.5-VL-32B-Instruct-4bit (✓ Downloaded)
   - Qwen3.6-35B-A3B-4bit-DWQ or Qwen3-32B-Instruct-4bit (✓ Downloaded)
   - gte-Qwen2-1.5B-instruct (✓ Downloaded)
4. Hover each card to verify `q8_0` K/V cache is set

**Verify via CLI (optional):**
```bash
lms ls
# Should list 3 models with status "Downloaded"
```

---

### Step 7: Start LM Studio Server

1. Click **Developer** tab (bottom of sidebar)
2. Under "Local server" section, click **Start Server**
3. Verify console shows:
   ```
   [INFO] Server started at http://0.0.0.0:1234
   [INFO] CORS enabled
   ```
4. **Important for Docker:** Toggle "Listen on 0.0.0.0" (not localhost)
   - This allows arkon container to reach `host.docker.internal:1234` on macOS
   - Linux users: use explicit host IP instead of host.docker.internal

<!-- SCREENSHOT: lmstudio-load-config-ui.png (operator fill in) -->
*Expected: Green "Server running" badge with port 1234*

**Health check:**
```bash
curl http://localhost:1234/api/v1/models
# Should return JSON with empty models array (models load on-demand)
```

---

### Step 8: Configure Arkon Admin Page

1. Log in to arkon admin portal as **admin user**
2. Navigate to **Settings** → **Local AI** (or `/admin/local-ai`)
3. You should see a form with:
   - **Mode:** dropdown (Off / Max / Other)
   - **LMS Host:** text field (pre-filled: `http://host.docker.internal:1234`)
   - **Model IDs:** read-only display of vision, main_llm, embedding

<!-- SCREENSHOT: admin-local-ai-page.png (operator fill in) -->
*Expected: Form loads without errors; Mode dropdown is visible*

4. Select **Mode = "Max"**
5. Click **Save**
6. Wait for confirmation message (green ✓)

---

### Step 9: Test Connection

1. Still on `/admin/local-ai`, click **Test Connection** button
2. Status should briefly show "Testing..." then turn **green** with message:
   ```
   ✓ Connected to LM Studio (models available: 3)
   ```
3. If red with error:
   - Verify LM Studio server is running (Step 7)
   - Check LMS Host URL matches your setup (localhost vs. host.docker.internal vs. IP)
   - See [Troubleshooting](./local-ai-orchestrator.md#troubleshooting) → Issue #1

---

### Step 10: Run Smoke Test

1. Go to arkon **Wiki Manager** or **MRP Ingestion** page
2. Submit a small test document (1–5 pages, < 5K tokens) as a **new wiki source**
3. Click **Start Ingestion** (or equivalent button)
4. Monitor worker logs or UI status for task progress
5. Wait 5–10 min for completion (depends on model, network, disk I/O)
6. Navigate to generated wiki pages in `/wiki/{source-slug}`
7. Spot-check:
   - Vietnamese formatting (entities with `(English / ABBR)` style)
   - No obvious hallucinations
   - Citations match source

**If successful:** Local AI is running! You can now ingest large sources.

**If failed:** Check `/admin/local-ai` status and [troubleshooting guide](./local-ai-orchestrator.md#troubleshooting).

---

## Model Specifications

### Vision Model: Qwen2.5-VL-32B-Instruct-4bit

| Property | Value |
|----------|-------|
| **HF Repo** | `mlx-community/Qwen2.5-VL-32B-Instruct-4bit` |
| **Size** | ~19GB (4-bit quantization) |
| **Architecture** | Vision Transformer (32B param) + MLX 4-bit quantization |
| **Input** | Images (PNG/JPG/GIF) + text prompts (Vietnamese or English) |
| **Max resolution** | ~4096×4096 pixels (handled by MLX batching) |
| **Best for** | Technical diagram captioning, OCR on Vietnamese docs, DocVQA, chart interpretation |
| **Fallback** | `mlx-community/Qwen2.5-VL-7B-Instruct-8bit` (~14GB) if OOM |
| **Context length (config)** | 8192 tokens |

### Main LLM: Qwen3.6-35B-A3B-4bit-DWQ

| Property | Value |
|----------|-------|
| **HF Repo** | `mlx-community/Qwen3.6-35B-A3B-4bit-DWQ` |
| **Requires HF verification** | Yes—exact repo name may differ; check mlx-community list |
| **Size** | ~21GB (4-bit Dynamic Weight Quantization) |
| **Architecture** | MoE (Mixture of Experts): 35B total, 3B active params |
| **Throughput** | ~50–70 tok/s on M1 Max (with q8_0 K/V quant) |
| **Context window** | 32K native (strong fidelity to ~100K with continued pretraining) |
| **Best for** | MRP pipeline (MAP entity extraction, REDUCE planning, REFINE writing, VERIFY audit, DIGEST summary) |
| **Fallback** | `mlx-community/Qwen3-32B-Instruct-4bit` (~18GB dense) if primary unavailable or OOM |
| **Context length (config)** | 32768 tokens |
| **Eval batch size (config)** | 256 tokens |
| **Flash attention** | Enabled (faster, lower memory) |
| **K/V cache offload** | Enabled (disk offload if needed) |

### Embedding Model: gte-Qwen2-1.5B-instruct

| Property | Value |
|----------|-------|
| **HF Repo** | `Alibaba-NLP/gte-Qwen2-1.5B-instruct` |
| **Size** | ~2GB (int8 quantized in arkon) |
| **Architecture** | Dense Transformer 1.5B |
| **Embedding dim** | 1024 |
| **Runtime** | Python (sentence-transformers), NOT LM Studio |
| **Best for** | Semantic retrieval (chunk ranking for REFINE page writing) |
| **Task-specific** | Supports `task="document"` and `task="search_query"` for asymmetric retrieval |
| **Fallback** | `Alibaba-NLP/gte-multilingual-base` (~1.5GB) if slow |
| **Vietnamese MTEB score** | 0.62 retrieval (vs. bge-m3 0.57) |

---

## Disk Space Requirements

| Component | Size | Notes |
|-----------|------|-------|
| Vision model | 19GB | Qwen2.5-VL-32B-4bit |
| Main LLM | 21GB | Qwen3.6-35B-A3B-4bit-DWQ |
| Embedding | 2GB | gte-Qwen2-1.5B-instruct |
| LM Studio app + cache | ~5GB | Includes temporary cache |
| **Total** | **~47GB** | Ensure host has ≥ 100GB free disk |

---

## RAM Requirements & Monitoring

Peak memory usage on M1 Max 32GB unified memory:

| Phase | Loaded Model | Peak RAM | Headroom |
|-------|--------------|----------|----------|
| Vision | Qwen2.5-VL-32B | ~20GB | 12GB available ✓ |
| MAP/REFINE | Qwen3.6-35B + embedding | ~23GB | 9GB available ⚠️ |
| Idle | None | ~11GB | 21GB available |

**Monitor during first run:**
- macOS: open Activity Monitor → Memory tab → watch "Unified Memory" row
- Linux: `watch -n 1 free -h`
- Stop task if RAM usage approaches 31GB (1GB reserved for OS)

---

## Troubleshooting During Setup

| Symptom | Cause | Fix |
|---------|-------|-----|
| Model download stalls | Slow network or LM Studio crash | Restart LM Studio; retry download |
| "Model not found" in LM Studio | HF repo name typo or deleted | Copy exact name from HF; check `mlx-community` list |
| "Server refused connection" at Step 9 | LM Studio not running or port blocked | Verify `lms ls` works; check firewall |
| K/V config not saved | UI bug or cache issue | Refresh page (Ctrl+Shift+R); restart LM Studio |
| Low throughput (~5 tok/s) | K/V quant not applied | Re-check Step 5; ensure model card shows `q8_0` badge |
| Docker container can't reach host | host.docker.internal DNS fail | Use explicit host IP instead (Linux) or check Docker settings (macOS) |

---

## Next: Production Deployment

After successful smoke test, see [Local AI Migration Playbook](./local-ai-migration-playbook.md) for cutover from cloud LLM to local AI orchestrator on production.

**Estimated total setup time:** 45–60 minutes (download time varies with internet speed).
