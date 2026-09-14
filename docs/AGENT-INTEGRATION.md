# Using the Qwen3.8-27B endpoint from an agent

OpenAI-compatible. Anything that speaks `/v1/chat/completions` works (openclaw, hermes, LangChain, the `openai` SDK).

## Connection

| | |
|---|---|
| base URL | `http://localhost:8000/v1` |
| model name | `qwen3.8-27b` |
| API key | any non-empty string (e.g. `none`) |
| readiness | `GET /v1/models` returns 200 (takes ~4 min after a restart) |
| also available | `/v1/responses`, `/v1/messages` (Anthropic-style), `/v1/completions`, `/metrics` |

## Limits

- **Context: 131,072 tokens** (prompt + generation). Requests over that are rejected — count/trim before sending.
- **Concurrency: 16 in-flight requests** server-wide (`MAX_SEQS`). Requests beyond that queue. 2–3 agents with a few parallel tool calls each is fine; don't fan out 20 subagents at once.
- **Images: max 4 per request**, no video.
- No rate limits or auth.

## Thinking / reasoning

Thinking is **ON by default** with `reasoning_effort` **`xhigh`** — this is the slow path. For agent loops:

```json
"chat_template_kwargs": {"enable_thinking": true, "reasoning_effort": "low"}
```
- `reasoning_effort`: `low` | `medium` | `xhigh` (default). Anything else is rejected by the template.
- `"enable_thinking": false` turns thinking off entirely (fastest, lower quality on hard tasks).
- Streaming responses put reasoning in `delta.reasoning_content` (or `delta.reasoning`), the answer in `delta.content`. Non-streaming: `message.reasoning_content` + `message.content`. Show/log them separately; **never feed reasoning_content back into the next turn**.
- Thinking tokens count against `max_tokens`. A run that hits the cap mid-thought returns empty `content` with `finish_reason: "length"`.

## Sampling (from the model card — the server defaults are already the thinking-mode values)

| mode | temperature | top_p | top_k | presence_penalty |
|---|---|---|---|---|
| thinking (default) | 1.0 | 0.95 | 20 | – |
| non-thinking | 0.7 | 0.8 | 20 | 1.5 |

Don't send `temperature: 0` for thinking mode — it degrades reasoning and causes repetition loops.

## max_tokens

- Set it explicitly; the default is "until context is full", which with thinking on can mean minutes.
- Suggested: **4,096–8,192** for agent turns with `reasoning_effort: low/medium`; **16k+** only for `xhigh` on hard problems.
- At ~25 tok/s per stream, 4k tokens ≈ 2.7 min worst case. Set client timeouts accordingly (10 min is safe).

## Tool calling

- Server-side parsing is on (`--enable-auto-tool-choice`, parser `qwen3_coder`). Send OpenAI-style `tools` and `tool_choice: "auto"`; you get structured `tool_calls` back.
- `tool_choice: "required"` / a named function works; `"none"` works.
- Return results as `role: "tool"` messages with `tool_call_id`, standard OpenAI shape.
- Parallel tool calls are supported (the model may emit several `tool_calls` in one turn).
- Structured output: `response_format: {"type": "json_schema", ...}` works, but combine with `enable_thinking: false` or expect the reasoning to eat tokens first.

## Prefix caching — the thing that decides your TTFT

The server caches KV for prompt prefixes, but for this model in **1,600-token blocks, and the last full block is never reused**. So:

- **Keep the start of the prompt byte-identical across turns**: same system prompt, same tool definitions, same order. Append-only conversation history. Put anything volatile (timestamps, random ids, "current time is…") at the **end** of the system prompt or in the user message, never at the start.
- Prompts **under ~3,200 tokens never hit the cache** — a short system prompt is re-prefilled every turn anyway, so don't contort things to shorten it.
- Each turn re-prefills roughly the last 1,600–3,200 tokens (~1–2s) even with a perfect cache hit. Budget for it.
- Cold prefill runs at ~1,600 tok/s: a fresh 50k-token context costs ~30s TTFT. Once cached, the same context costs ~2s. **Don't rebuild the context from scratch every turn** (e.g. re-summarizing or reordering messages) — that throws away the cache.
- Compaction/summarization resets the cache; do it rarely and when the agent is idle anyway.

## Expected performance (measured, 3 agents in parallel)

| | |
|---|---|
| decode | ~25 tok/s per stream, ~47 tok/s aggregate |
| TTFT, warm prefix | ~1.5s |
| TTFT, cold | prompt_tokens / 1,600 s |

Throughput is memory-bandwidth-bound: adding a 2nd and 3rd agent barely slows each one down, so **run agents concurrently rather than serially** — but a 4th–6th will start to.

## Streaming

Use `stream: true` and `stream_options: {"include_usage": true}` to get `usage` in the last chunk (prompt_tokens / completion_tokens) — useful for context accounting and for measuring cache hits (`prompt_tokens` is total, not uncached; watch `/metrics` `vllm:prefix_cache_hits_total` for that).

## Minimal request

```bash
curl localhost:8000/v1/chat/completions -H 'content-type: application/json' -d '{
  "model": "qwen3.8-27b",
  "messages": [{"role":"system","content":"You are a coding agent."},
               {"role":"user","content":"List the files in src/."}],
  "tools": [{"type":"function","function":{"name":"run","description":"Run a shell command",
             "parameters":{"type":"object","properties":{"cmd":{"type":"string"}},"required":["cmd"]}}}],
  "tool_choice": "auto",
  "max_tokens": 4096,
  "stream": true,
  "stream_options": {"include_usage": true},
  "chat_template_kwargs": {"enable_thinking": true, "reasoning_effort": "low"}
}'
```

## Ops

- Restart: `docker start vllm-qwen` (same config) or `MODEL=/home/dell/models/Qwen3.8-27B-NVFP4 ./serve-v3.sh`. ~4 min to ready; requests during that window get connection refused — retry with backoff on `/v1/models`.
- Logs: `docker logs -f vllm-qwen`. Live throughput/cache-hit lines every 10s.
- Health: `/health`, `/metrics` (Prometheus; Grafana is already running on this box).
- Memory is unified with the GPU: the server holds ~73 GB, so the agents + everything else share the remaining ~48 GB.
