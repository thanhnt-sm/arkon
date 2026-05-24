# Test Fixtures — Source Documents

These fixtures feed the end-to-end integration test
`tests/integration/test_local_orchestrator_e2e.py`.

---

## Files

| File | Purpose | Size |
|------|---------|------|
| `small-vi-wiki-source.md` | Primary test corpus — Vietnamese technical article on Transformer architecture | ~5 000 tokens |
| `sample-chart.png` | Placeholder 1×1 PNG — architecture diagram stub | 67 bytes |
| `sample-vi-screenshot.png` | Placeholder 1×1 PNG — Vietnamese OCR screenshot stub | 67 bytes |
| `create-placeholder-pngs.py` | Script to regenerate the placeholder PNGs from scratch | — |

---

## Token Count Approximation

```
word count  ≈  wc -w small-vi-wiki-source.md      →  ~3 800 words
token count ≈  word_count × 1.3                   →  ~4 940 tokens
```

Vietnamese text tokenises slightly higher than English (compound words, diacritics).
This file is intentionally sized just under 5 000 tokens so it fits comfortably in
a single MAP chunk without triggering hierarchical splitting.

---

## Replacing Placeholder PNGs

The stub PNGs are valid 1×1 transparent images — enough for the e2e test fixture
loader to verify file existence and upload to MinIO.  They will produce low-quality
vision captions ("a 1×1 transparent image") which is acceptable for a scaffold run.

**Before running the live e2e test for real quality validation**, replace them with:

- `sample-chart.png` — a real Transformer architecture diagram (e.g. exported from
  draw.io or a screenshot of the original Vaswani et al. figure).
- `sample-vi-screenshot.png` — a screenshot of Vietnamese text (e.g. a paragraph from
  a Vietnamese Wikipedia article rendered in a browser).

Suggested minimum size: 400×300 px, < 2 MB each.

To regenerate the 1×1 stubs (e.g. after a bad merge):

```bash
python3 tests/fixtures/sources/create-placeholder-pngs.py
```

---

## Notes

- Do **not** commit real proprietary documents or personal data to this directory.
- The Vietnamese markdown content is encyclopedic and contains no PII.
- Image fixtures are intentionally minimal; vision caption quality is tested
  separately in unit tests with mocked LM Studio responses.
