# Ravi local models

Default engine: **llama.cpp** (not Ollama).

Default chat GGUF:
- `Qwen3-4B-Instruct-2507-Q4_K_M.gguf` (context 8192)

Also used by the default stack:
- **Voice:** Kokoro-82M ONNX INT8 (`ravi voice on`)
- **Image:** Stable Diffusion 1.5 Q4_0 via stable-diffusion.cpp (`ravi image on`)
- **Video:** optional, off by default (`ravi video on`)

```bash
ravi config backend llama    # default
ravi config backend ollama   # optional
ravi config lang en
ravi local pull
```
