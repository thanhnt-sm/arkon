# Local AI Migration Playbook

## Context

Arkon currently runs MRP (Map-Reduce-Refine) pipeline against cloud LLM (e.g., `huihui-qwen3.5-27b` via OpenAI-compatible endpoint). This playbook guides production cutover from cloud to local AI orchestrator (Qwen3.6-35B-A3B + Qwen2.5-VL on M1 Max LM Studio).

**Status quo:** MRP ingestion is cloud-dependent, with ~2–3 sec latency per request. Local AI reduces to sub-second LLM calls + one-time model load (2–5 min startup per phase).

**Migration scope:** Switching production `local_ai.mode` from `off` to `max`. Zero schema changes. Rollback is one KV update.

---

## Pre-Migration Checklist

Before starting maintenance window, verify all items:

- [ ] **All in-flight MRP jobs complete**
  - SSH to prod host → run: `psql -c "SELECT COUNT(*) FROM mrp_jobs WHERE status IN ('running', 'queued')"`
  - Result should be **0**
- [ ] **Database backup taken**
  - `pg_dump arkon > arkon-backup-$(date +%Y%m%d-%H%M%S).sql`
  - Verify backup file size > 10MB (contains real data)
- [ ] **Disk space available on host**
  - `df -h /` should show ≥ 100GB free
  - Models total ~47GB; buffer for temp files
- [ ] **Free RAM at start of maintenance window**
  - `vm_stat 1 1` (macOS) or `free -h` (Linux)
  - Should show ≥ 23GB free (peak needed: vision 20GB + embedding 2GB + OS 1GB)
- [ ] **LM Studio server ready on host**
  - All 3 models downloaded (vision, main_llm, embedding)
  - K/V cache quantization q8_0 set per-model in LM Studio UI
  - LM Studio Developer tab → Server running on port 1234
  - Test: `curl http://localhost:1234/api/v1/models` returns JSON
- [ ] **Staging environment validation (optional but recommended)**
  - Run smoke test on dev mirror of prod DB
  - Verify 1 small wiki source ingests successfully in `max` mode
  - Spot-check Vietnamese formatting, no hallucinations
- [ ] **Communication plan**
  - Notify stakeholders of 1–2 hour maintenance window
  - Prepare rollback messaging if needed

---

## Maintenance Window (1–2 hours recommended off-peak)

### Phase 1: Prepare for Cutover (5 min)

**On prod host:**

1. Pause new MRP intake (prevents new jobs queuing)
   ```bash
   psql -c "UPDATE app_config SET value='true' WHERE key='mrp.intake_paused'"
   ```
   Admin UI should show "Intake paused" banner

2. Verify no new tasks arrived:
   ```bash
   psql -c "SELECT COUNT(*) FROM mrp_jobs WHERE status='queued'"
   ```
   Result: **0**

---

### Phase 2: Wait for In-Flight Jobs to Drain (10–30 min)

Poll running job count every 60 sec:

```bash
watch -n 60 psql -c "SELECT COUNT(*) FROM mrp_jobs WHERE status='running'"
```

Once it shows **0 running jobs**, proceed to Phase 3.

**If jobs don't drain after 20 min:**
- Check worker logs: `docker logs arkon_worker 2>&1 | tail -50`
- Look for stuck tasks (hanging LLM call)
- Option: `SIGTERM` worker container to force graceful shutdown, then wait for restart

---

### Phase 3: Switch Mode to Max (2 min)

**Via SQL (fastest):**
```bash
psql -c "UPDATE app_config SET value='max' WHERE key='local_ai.mode'"
```

**Verify:**
```bash
psql -c "SELECT key, value FROM app_config WHERE key='local_ai.mode'"
# Should show: local_ai.mode | max
```

**Or via Admin UI (if preferred):**
- Login as admin
- Navigate to Settings → Local AI
- Mode dropdown: select "Max"
- Click Save
- Wait for success notification

---

### Phase 4: Test Connection (2 min)

**Option 1: Admin UI**
- Still on `/admin/local-ai`
- Click **Test Connection** button
- Should show green ✓ "Connected to LM Studio"

**Option 2: CLI**
```bash
curl -s http://localhost:1234/api/v1/models | jq '.data | length'
# Should return: 0 (no models pre-loaded; they load on-demand)
```

**If connection fails:**
- Verify LM Studio server is running: `lms ls` should work
- Check firewall: `sudo lsof -i :1234` should show LM Studio listening
- **CRITICAL:** Do NOT proceed if connection fails. See rollback below.

---

### Phase 5: Submit Small Test Source (5 min)

1. Go to Wiki Manager → **Ingest Source**
2. Upload a small test document (1–3 pages, < 2000 tokens)
3. Click **Start Ingestion**
4. Monitor worker logs in real-time:
   ```bash
   docker logs -f arkon_worker 2>&1 | grep -E "(local_ai|Qwen|loading|completion)"
   ```
5. Expected logs (first-time model loads):
   ```
   [local_ai] Loading vision model: mlx-community/Qwen2.5-VL-32B-Instruct-4bit
   [LMS] load() returned instance_id=v1 (took 3.2s)
   [local_ai] Loaded vision; processing 2 images
   [LMS] predict(v1, caption_prompt) → captions (1.2s)
   [local_ai] Unloading vision model
   [local_ai] Loading main_llm model: mlx-community/Qwen3.6-35B-A3B-4bit-DWQ
   [LMS] load() returned instance_id=llm1 (took 5.8s)
   [local_ai] MAP phase: processing 3 chunks
   [LMS] predict(llm1, map_prompt, chunk_1) → JSON (12.3s)
   ...
   ```
6. Wait for ingestion to complete (5–10 min depending on source size)

---

### Phase 6: Verify Output Quality (5 min)

1. Navigate to generated wiki: `/wiki/{source-slug}`
2. Spot-check 3–5 pages:
   - **Vietnamese formatting:** entities should have `(English / ABBR)` suffix
   - **Citations:** each factual claim should have `[^N]` footnote reference
   - **Hallucination check:** re-read claims against source; no obvious falsehoods
   - **Length:** pages should be 500–2000 words (not suspiciously short or long)
3. If quality acceptable, **proceed to Phase 7**. If issues found:
   - Note the problem (e.g., "missing citations", "poor Vietnamese")
   - See rollback section below

---

### Phase 7: Resume Intake & Mark Cutover Complete (2 min)

1. Re-enable new MRP intake:
   ```bash
   psql -c "UPDATE app_config SET value='false' WHERE key='mrp.intake_paused'"
   ```

2. Verify intake is live:
   ```bash
   psql -c "SELECT key, value FROM app_config WHERE key LIKE 'mrp.intake%'"
   # Should show: mrp.intake_paused | false
   ```

3. Admin UI banner should disappear (no longer showing "Intake paused")

4. **Mark cutover complete:**
   - Log timestamp: `date -u +"%Y-%m-%d %H:%M:%S UTC"`
   - Update a status file or ticket: "Cutover completed at [timestamp]. Mode: max. First test source OK."

---

## Rollback Plan (If Something Goes Wrong)

**Symptom:** Test source fails, quality is poor, or LM Studio connection never works.

**Immediate action (2 min):**

1. Set mode back to `off`:
   ```bash
   psql -c "UPDATE app_config SET value='off' WHERE key='local_ai.mode'"
   ```

2. Verify revert:
   ```bash
   psql -c "SELECT key, value FROM app_config WHERE key='local_ai.mode'"
   # Should show: local_ai.mode | off
   ```

3. Pause intake (no new tasks):
   ```bash
   psql -c "UPDATE app_config SET value='true' WHERE key='mrp.intake_paused'"
   ```

4. Restart worker to clear any cached state:
   ```bash
   docker restart arkon_worker
   docker logs arkon_worker 2>&1 | head -20
   # Should show worker re-initializing with cloud profile
   ```

**Why it works:** No schema changes were made. KV table still has all old config. Setting `mode=off` disables orchestrator, and next task route goes back to cloud LLM provider. Cache TTL (60s) ensures fresh profile detection.

**Post-rollback:** 
- Investigate root cause (see [Troubleshooting](./local-ai-orchestrator.md#troubleshooting))
- Fix config or LM Studio issue
- Schedule retry (don't repeat same mistake)

---

## Sign-Off Checklist

After successful cutover:

- [ ] **Operator:** Cutover date & time logged
- [ ] **Operator:** Smoke test source ingested successfully
- [ ] **Operator:** Output quality spot-checked (Vietnamese, citations, coherence)
- [ ] **Reviewer:** (Engineering lead) Reviews logs, confirms no errors
- [ ] **Reviewer:** Approves production migration
- [ ] **Timestamp:** `date -u > /var/log/arkon/cutover-completion.txt`

**Sign-off format:**
```
LOCAL AI MIGRATION SIGN-OFF
===========================
Date: 2026-05-24
Time: 14:32 UTC
Operator: [name]
Reviewer: [name]
Status: ✓ COMPLETE

Test source: [wiki-slug]
Mode: max
Estimated model load time: vision 3.2s, main_llm 5.8s
First completion latency: ~45s for 3-page source
Quality: PASS (Vietnamese OK, citations present, no hallucinations)
```

---

## Post-Cutover Operations

### Monitoring

**Daily checks:**
- Admin UI `/admin/local-ai` → Mode should show "Max (active)"
- Worker logs: no recurring OOM errors
- MRP ingestion queue: no stuck tasks

**Weekly summary:**
- Count successful ingestions: `SELECT COUNT(*) FROM mrp_jobs WHERE status='completed' AND updated_at > NOW() - INTERVAL '7 days'`
- Average completion time: `SELECT AVG(EXTRACT(EPOCH FROM (completed_at - created_at))) FROM mrp_jobs WHERE completed_at IS NOT NULL AND created_at > NOW() - INTERVAL '7 days'`

### Model Updates

If a new Qwen version becomes available (e.g., Qwen3.7):

1. Download in LM Studio UI
2. Set K/V cache q8_0 per model config
3. Update `local_ai.main_llm.model_id` in admin UI
4. Test on 1 small source first
5. If OK, continue normal ingestion

### Fallback Activation

If OOM errors occur repeatedly:

1. Check free RAM: `vm_stat 1 1`
2. Increase `ram_headroom_gb` by 1: 
   ```bash
   psql -c "UPDATE app_config SET value='3.0' WHERE key='local_ai.ram_headroom_gb'"
   ```
3. Next OOM will trigger fallback to Qwen3-32B-Instruct-4bit (still good quality, slightly slower)

---

## FAQ: Migration Concerns

**Q: Will users see downtime?**
A: Yes, 1–2 hour maintenance window. Schedule off-peak (night/weekend). No data loss; intake just paused.

**Q: Can I test without touching production?**
A: Yes! Create a staging DB from production backup, switch `local_ai.mode` there first, run smoke tests for 24h, then apply to production.

**Q: What if cloud API goes down during transition?**
A: Cutover is atomic (one KV update). If you're mid-migration and cloud fails, switch to local immediately—local AI is now your safety net.

**Q: Can I run both cloud and local simultaneously?**
A: No (one provider active at a time). But you can A/B test: run local for 1 week, measure quality/speed, then decide. Rollback is instant.

**Q: What's the throughput difference?**
A: Cloud: ~3 sec per MAP call (network RTT). Local: ~0.3 sec (sub-second after first model load). Expect ~50–70 tok/s generation on M1 Max with Qwen3.6-35B.

---

## Contact & Escalation

**If migration fails:**
1. Check [Troubleshooting](./local-ai-orchestrator.md#troubleshooting) section
2. Review worker logs: `docker logs arkon_worker > migration-logs.txt`
3. Rollback immediately (see above)
4. Escalate to engineering lead with logs + notes

**For model verification issues (Qwen3.6-35B-A3B not found on HF):**
1. Check mlx-community org on HuggingFace
2. Use fallback model: `mlx-community/Qwen3-32B-Instruct-4bit`
3. File an issue on the arkon GitHub repo with exact HF URL you found

---

**Migration estimated time:** 1–2 hours (including model load time on first ingestion).

**Last updated:** 2026-05-24

**Related:** [Local AI Orchestrator](./local-ai-orchestrator.md) | [Model Checklist](./local-ai-model-checklist.md)
