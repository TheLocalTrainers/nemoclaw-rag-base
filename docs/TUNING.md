# vLLM tuning notes — Qwen3.8-27B-NVFP4 on DGX Spark (GB10)

Goal: faster inference for 2–3 coding agents in parallel, and faster startup.
Date: 2026-09-12. vLLM 0.29.0 (`vllm/vllm-openai:latest`), model `/home/dell/models/Qwen3.8-27B-NVFP4`.

## TL;DR

- **Use `serve-v3.sh`** (defaults). Startup 494s → ~224s; cold prefill +37%; 3-agent aggregate decode +17%; box no longer swapping.
- Kernel override `flashinfer_b12x` was tested and is **slower** — stays on `auto`.
- Best untested bets: `KV_DTYPE=auto`, `SPEC_TOKENS=5`, `LOAD_FORMAT=runai_streamer` (see "Next").

## Results (`./bench.py --compare`)

| config | startup | cold prefill | 1 agent | 3 agents: TTFT / per-stream / aggregate | MTP tok/step |
|---|---|---|---|---|---|
| serve-v2 (baseline) | 494s | 1,195 tok/s | 22.4 tok/s | 2.13s / 21.6 / **40.1** | 2.77 |
| **serve-v3 defaults** | 422s cold caches, **224s warm** | **1,634 tok/s** | 25.4 tok/s | 1.44s / 24.9 / **46.9** | 2.86 |
| v3 + `LINEAR_BACKEND=flashinfer_b12x` | – | 1,268 tok/s | 21.1 tok/s | 1.65s / 19.9 / 44.8 | 2.88 |

Benchmark: shared ~2.5k-token system prompt + distinct coding tasks, thinking on, 400 max tokens,
plus one cold ~38k-token prefill. Raw records in `bench-results.jsonl`.

## Baseline diagnosis (serve-v2, `GPU_UTIL=0.80`)

Startup breakdown from the logs (8m14s total):

| phase | time | note |
|---|---|---|
| weight load | 110s (+10s MTP head re-reads shards) | not disk-bound: NVMe reads 1.4 GB/s uncached; loader does ~200 MB/s → mmap/CPU cost |
| torch.compile | 32s | cache was inside the container, lost on every `docker rm -f` |
| profiling/warmup | 37s | |
| CUDA-graph capture | 84s + 91s | 51 shapes because `max_num_seqs` defaulted to a 512-token batch |
| FlashInfer autotune | ~94s (seen in v3 run) | also lost with the container |
| multimodal warmup | 12s | |

Inference issues:
- `GPU_UTIL=0.80` reserved 67 GB of KV (1.75M tokens, 13× a full 131k context); host had 1 GB free and was swapping — hurts the agents *and* vLLM's CPU-side scheduler.
- Prefill chunk was capped at 2048 tokens (`max_num_batched_tokens`), the warning vLLM prints about it was real.

## What serve-v3.sh changes

| change | effect |
|---|---|
| mount `~/.cache/vllm` and `~/.cache/flashinfer` into the container | torch.compile 34s → 0.7s, FlashInfer autotune 94s → 0 on later starts |
| `--max-num-seqs 16` | CUDA-graph capture 175s → ~26s; 2–3 agents (+ subagents) never need 256 slots |
| `--max-num-batched-tokens 8192` | prefill 1,195 → 1,634 tok/s |
| `GPU_UTIL 0.60` (was 0.80) | ~30 GB left for the OS/agents; still 45 GB KV = 1.17M tokens = 9× a full 131k context |
| every tunable exposed as an env var | see below |

Unchanged from v2: NVFP4 checkpoint, `--kv-cache-dtype fp8`, prefix caching, MTP speculative decoding (k=3),
qwen3 reasoning parser, qwen3_coder tool parser, 131k max context, images enabled.

## Findings worth remembering

1. **Prefix cache granularity is 1600 tokens, and the last full block is never reused.**
   vLLM aligns the attention page to the Mamba/GDN state page for this hybrid model (log: "Setting attention block
   size to 1600 tokens"). Consequences: prompts under ~3.2k tokens get 0% hits (a 2,420-token prompt sent 3× → 0 hits;
   a 6,620-token prompt → 4,800 hit tokens = 3 blocks). Every agent turn re-prefills up to ~3.2k tail tokens (~2s).
   fp8 KV makes this *coarser* (smaller attention pages → more tokens per block); bf16 KV should give 800-token blocks.
2. **Weight load (~104s) is CPU/mmap-bound, not IO.** Page cache warm or cold makes no difference.
   `runai_streamer` (installed in the image) bypasses mmap and is the fix to try.
3. **MTP is working well**: 2.86 accepted tokens/step, 62% of drafts accepted; per-position acceptance
   76% / 58% / 44% — position 3 still contributes, so k=4–5 may help. Decode here is memory-bandwidth-bound
   (~21 GB weights over ~273 GB/s ≈ 13 tok/s without MTP), so spec decoding is what makes 25 tok/s possible.
4. Async scheduling is already on by default (MTP counts as EAGLE-type). FlashInfer attention + FlashInfer-CUTLASS
   NVFP4 GEMM are the auto-selected kernels and beat the SM12x-specific `flashinfer_b12x`.
5. Model dir has macOS `._*` sidecar files (copied from a Mac) — harmless, but they can be deleted.

## Knobs (`serve-v3.sh` env vars)

| var | default | notes |
|---|---|---|
| `MODEL` | `~/models/Qwen3.8-27B-NVFP4` | local dir (mounted at /model) or HF id |
| `GPU_UTIL` | `0.60` | unified memory: whatever vLLM takes, the agents can't have |
| `MAX_SEQS` | `16` | concurrent sequences; also drives how many CUDA graphs are captured |
| `BATCHED_TOKENS` | `8192` | prefill chunk; bigger = faster TTFT, longer decode stalls for other agents during a big prefill |
| `MAX_LEN` | `131072` | native 262144 |
| `SPEC_TOKENS` | `3` | MTP draft tokens per step; `0` disables spec decoding |
| `KV_DTYPE` | `fp8` | `auto` = bf16 (halves prefix-cache block to 800 tok, ~12% slower decode at 100k ctx) |
| `LINEAR_BACKEND` | `auto` | `flashinfer_b12x` tested: slower |
| `ATTN_BACKEND` | (auto = FLASHINFER) | `TRITON_ATTN` untested |
| `LOAD_FORMAT` | `auto` | `runai_streamer` untested |
| `MM_IMAGES` | `4` | `0` = text-only, skips 12s vision warmup |
| `WAIT` | `0` | `1` = block until `/v1/models` answers, print startup seconds |
| `NAME`, `PORT`, `IMAGE` | `vllm-qwen`, `8000`, `vllm/vllm-openai:latest` | |

Extra args after the script are passed straight to `vllm serve`.

## Tools

- `./serve-v3.sh` — start/replace the container. `docker start vllm-qwen` restarts the same config (auto-starts on boot).
- `./bench.py --label <name> [--concurrency 1,2,3] [--rounds 2] [--max-tokens 400]` — run the agent-style benchmark
  against the live server and append to `bench-results.jsonl`. `./bench.py --compare` prints the table.
- `./tune.sh <label> VAR=val ... [-- bench args]` — restart with overrides, time startup, run the benchmark, record it.
  e.g. `./tune.sh kv-bf16 KV_DTYPE=auto`. Each run ≈ 4 min startup + 3–5 min bench and **restarts the server**.

## Next (untested, in order of expected payoff)

1. `KV_DTYPE=auto` — 800-token prefix blocks → half the re-prefill per agent turn. Check "Setting attention block size" in the logs.
2. `SPEC_TOKENS=5` — watch `MTP tok/step` in the bench; keep if it rises without hurting per-stream tok/s.
3. `LOAD_FORMAT=runai_streamer` — startup only; compare "Loading weights took" in `docker logs`.
4. `ATTN_BACKEND=TRITON_ATTN` — long shot; FlashInfer falls back to "rebuilding attention metadata between draft steps" with MTP.
5. `MM_IMAGES=0` if you never send images — 12s startup and a little memory.
