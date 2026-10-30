# C16 - NinjaTrader first, Ollama leaves 2 cores free (DRAFT for the owner)

Machine: i7-12800H, 14 cores (6 performance + 8 efficiency), 20 threads.

## Already live in the repo (no owner step)
- `tools/local_llm.py` and `tools/qwen_runner.py` send `num_thread: 12` with every Ollama call:
  the part of a model that spills off the GPU uses at most 12 of the 14 cores.
  Override with the env var `AUGUR_LOCAL_LLM_THREADS` (0 = let Ollama decide).
- Note: `OLLAMA_NUM_THREADS` is **not** an Ollama setting; setting it does nothing. Thread count is a
  per-request option (`num_thread`) or a Modelfile line, which is why it lives in our callers.
  Calls that do not go through these two files (Cline in VS Code, the router on :11435, Strata)
  are not capped - see step 3.

## Owner steps (system changes - not applied by any chat)
1. Check what would change (safe, changes nothing):

       powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\xride\OneDrive\Desktop\EDGE-LOG\tools\cpu_priority.ps1

2. Keep it applied - a windowless task at logon and every 15 min (NinjaTrader AboveNormal,
   Ollama BelowNormal; priority resets when a process restarts):

       schtasks /create /tn "EdgeLog CPU priority" /sc minute /mo 15 /ru xride /tr "conhost.exe --headless powershell -NoProfile -ExecutionPolicy Bypass -File C:\Users\xride\OneDrive\Desktop\EDGE-LOG\tools\cpu_priority.ps1 -Apply"

   Undo: `schtasks /delete /tn "EdgeLog CPU priority" /f`.
3. Optional, caps every Ollama caller (Cline, router too): bake the thread count into each model,
   e.g. a Modelfile `FROM 3.qwen3.6:35b-32k` + `PARAMETER num_thread 12`, then
   `ollama create 3.qwen3.6:35b-32k -f Modelfile`. Re-tag only with the model owner's OK
   (MODEL NUMBERS rule: tell the owner before changing models).

Not done on purpose: no AboveNormal->High / Realtime (can freeze input), no core affinity pinning
(efficiency cores would idle while NinjaTrader waits), and llama-server (Strata) is left alone: it
runs AboveNormal today on purpose; whether it yields to NinjaTrader is the owner's call.
