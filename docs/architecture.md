# Architecture

Ravi AI is a thin, POSIX-compatible CLI wrapper around a managed Ollama
container. It avoids heavy runtime dependencies (Python, Node, etc.) so
it can run on BusyBox-based systems and under WSL.

## High-level components

```
┌─────────────────────────────────────────────────────────────┐
│                        Host                                 │
│                                                             │
│  /usr/bin/ravi  ─────────────────────────────────────────┐  │
│       │                                                   │  │
│       ▼                                                   │  │
│  /usr/lib/ravi/                                           │  │
│  ├── ravi               (main entry-point)                │  │
│  └── lib/                                                 │  │
│      ├── common.sh      (env detection, Docker discovery) │  │
│      ├── volume.sh      (persistent models volume)        │  │
│      └── container.sh   (lifecycle + image loading)       │  │
│                                                             │
│  /usr/share/ravi/       (offline image packages)          │  │
│  └── ollama-cpu.tar.gz                                    │  │
│                                                             │
│  Docker (docker or docker.exe)                              │
│  ├── volume "models"  ←→  /models inside container         │  │
│  └── container "ravi-ollama"                               │  │
│        image: ravi-ollama:cpu                              │  │
│        port:  127.0.0.1:11434 → 11434                      │  │
└─────────────────────────────────────────────────────────────┘
```

## Design principles

1. **Persistence first**  
   Model weights live in a named Docker volume (`models`).  
   Removing or recreating the container never deletes user data.

2. **Offline / air-gapped friendly**  
   The CLI can load a pre-packaged image tarball from  
   `/usr/share/ravi/` (or the project’s `local/` directory during
   development). No registry access is required after the initial
   packaging step.

3. **Minimal host footprint**  
   Only a POSIX shell and a working Docker daemon are required.
   All AI logic runs inside the container.

4. **WSL-aware Docker discovery**  
   Prefer native `docker` when it works; otherwise use `docker.exe`
   (Docker Desktop) including common AppData install paths.

5. **Fail-safe defaults**  
   - Port is bound only to localhost.  
   - Labels (`com.ravios.managed=true`) identify managed resources.  
   - Zero-byte placeholder files are ignored.

## Image resolution order

When the required image (`ravi-ollama:cpu` by default) is missing:

1. Load any non-empty `.tar` / `.tar.gz` found in `LOCAL_DIR`.
2. Load the classic offline path `/usr/share/ravi/ollama-cpu.tar.gz`.
3. Attempt `docker pull` (useful when `OLLAMA_IMAGE` is overridden).
4. Emit a clear, actionable error message.

## Ollama binary layout inside the image

The CPU-only image is built from a pre-compiled tarball that contains:

```
ollama                          # main binary → /usr/bin/ollama
llama/build/linux-amd64/runners/
  cpu_avx/ollama_llama_server
  cpu_avx2/ollama_llama_server
```

Runners are installed under `/usr/lib/ollama/runners/` so that Ollama’s
discovery logic can locate them at runtime.

The base image is **Ubuntu 26.04** to match the glibc version (2.43)
used when the binary was built.
