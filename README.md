# Ravi AI

**Ravi AI** is a lightweight command-line tool that runs
[Ollama](https://ollama.com/) (local large-language models) inside a
managed Docker container. It targets minimal environments such as
RaviOS and other BusyBox / POSIX systems, and also works under WSL
with Docker Desktop.

You do **not** need Python, Node.js, or any other heavy runtime – only
a working Docker installation and a POSIX shell.

---

## Quick Start

```bash
# 1. Prepare offline assets (once, on a machine with network access)
./scripts/fetch-debs.sh \
    --mirror http://archive.ubuntu.com/ubuntu \
    --suite resolute \
    --no-security

# Place your pre-built Ollama CPU tarball:
#   local/ollama/ollama-cpu-build-*.tar.gz

# 2. Build the image
./scripts/build-image.sh

# 3. Install the CLI and start the service
sudo ./install.sh

# 4. Pull a model and chat
ravi run pull qwen2.5:0.5b
ravi
```

Type `/bye` to leave the chat.

---

## Requirements

| Component   | Minimum |
|-------------|---------|
| Docker      | Recent version with volume support (Linux `docker` or WSL `docker.exe`) |
| Shell       | POSIX (`sh`, BusyBox ash, dash, bash) |
| Privileges  | Ability to talk to the Docker daemon |
| Disk (image)| ≈ 300–500 MB for the CPU-only image |
| Disk (models)| Depends on the models you pull |

The Ollama binary must be built against a glibc version compatible with
the base image (currently **Ubuntu 26.04 / glibc 2.43**).

---

## Installation

```bash
git clone <repository-url>
cd ravi
chmod +x install.sh scripts/*.sh tools/ravi/ravi
sudo ./install.sh
```

The installer places:

| Path | Content |
|------|---------|
| `/usr/bin/ravi` | CLI entry point (symlink) |
| `/usr/lib/ravi/` | Main script and libraries |
| `/usr/share/ravi/` | Offline image packages |

If the `ravi-ollama:cpu` image is missing and the required assets are
present under `local/`, `install.sh` will attempt to load or build it
automatically.

---

## Obtaining the Ollama image (fully offline)

### 1. Prepare assets (online machine, once)

**Debian/Ubuntu packages**

```bash
./scripts/fetch-debs.sh \
    --mirror http://archive.ubuntu.com/ubuntu \
    --suite resolute \
    --no-security
```

This downloads `ca-certificates`, `curl`, `libstdc++6` and their
dependencies into `local/debs/`.

**Ollama CPU binary tree**

Place a pre-built tarball in `local/ollama/`. Expected layout inside
the archive:

```text
ollama
llama/build/linux-amd64/runners/
  cpu_avx/ollama_llama_server
  cpu_avx2/ollama_llama_server
```

Example:

```bash
cp /path/to/ollama-cpu-build-v0.5.7.tar.gz local/ollama/
```

**Base image (optional, for fully offline builds)**

```bash
docker pull ubuntu:26.04
docker save ubuntu:26.04 -o local/debian/ubuntu-26.04.tar
```

### 2. Build

```bash
./scripts/build-image.sh
# or force a rebuild:
./scripts/build-image.sh --force
```

### 3. Save for later deployment (optional)

```bash
docker save ravi-ollama:cpu | gzip > /usr/share/ravi/ollama-cpu.tar.gz
```

After this point the target machine never needs internet for the image
itself (model pulls still require network unless models are pre-loaded).

---

## Everyday Commands

| Command | Description |
|---------|-------------|
| `ravi` | Interactive chat with the first available model |
| `ravi install` | Ensure volume exists and start the container |
| `ravi start` | Start the container |
| `ravi stop` | Stop the container (models are kept) |
| `ravi restart` | Stop + start |
| `ravi status` | Show container, volume and image status |
| `ravi logs` | Follow container logs |
| `ravi uninstall` | Remove the container, keep the models volume |
| `ravi run <args>` | Run any native ollama command inside the container |
| `ravi help` | Show help |

Unknown verbs are forwarded to ollama:

```bash
ravi pull llama3.2
ravi list
ravi run run llama3.2 "Hello"
```

---

## Persistent model storage

All downloaded models live in a Docker volume named `models`. The
volume survives:

- `ravi stop`
- `ravi uninstall`
- container recreation
- host reboots

Remove models only with an explicit `docker volume rm models`.

---

## Project layout

```text
ravi/
├── install.sh                  # Host installer (+ optional image prep)
├── README.md
├── scripts/
│   ├── fetch-debs.sh           # Download .deb packages for the image
│   └── build-image.sh          # Load base image + docker build
├── docker/
│   └── Dockerfile.ollama-cpu   # Fully offline CPU-only image
├── local/                      # Offline build assets
│   ├── debs/                   # .deb packages
│   ├── ollama/                 # ollama-cpu-build-*.tar.gz
│   ├── debian/                 # optional base image tarball
│   └── README.md
├── docs/
│   ├── architecture.md
│   ├── workflow.md
│   ├── building-and-offline.md
│   ├── troubleshooting.md
│   └── known-issues-and-suggestions.md
└── tools/
    └── ravi/
        ├── ravi                # Main CLI entry-point
        └── lib/
            ├── common.sh       # env detection, docker discovery
            ├── volume.sh       # persistent models volume
            └── container.sh    # lifecycle + image loading
```

---

## WSL / Docker Desktop

On WSL the CLI automatically prefers `docker.exe` when the native
`docker` binary is missing or cannot reach a daemon. Common Docker
Desktop paths under `/mnt/c/Users/.../AppData/...` are also searched
(including when running under `sudo`).

---

## Documentation

- [Architecture](docs/architecture.md)
- [Workflow](docs/workflow.md)
- [Building offline](docs/building-and-offline.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Known issues](docs/known-issues-and-suggestions.md)
