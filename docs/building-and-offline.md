# Building the Image – Fully Offline

Ravi’s Dockerfile never contacts the network. Everything it needs must
be prepared in advance under the `local/` directory.

## Directory layout

```text
local/
├── debs/                          # Ubuntu packages (.deb)
│   ├── ca-certificates_….deb
│   ├── curl_….deb
│   ├── libstdc++6_….deb
│   └── … all dependencies
├── ollama/
│   └── ollama-cpu-build-v0.5.7.tar.gz   # CPU-only binary tree
├── debian/
│   └── ubuntu-26.04.tar                 # (optional) base image
└── ollama-cpu.tar.gz                    # (optional) final image
```

## Step 1 – Prepare the .deb packages

```bash
./scripts/fetch-debs.sh \
    --mirror http://archive.ubuntu.com/ubuntu \
    --suite resolute \
    --no-security
```

`resolute` is the Ubuntu 26.04 codename. The script isolates apt from
the host package database so it works even when the host is a different
distribution or release.

Required packages: `ca-certificates`, `curl`, `libstdc++6` and their
dependency closure.

## Step 2 – Prepare the Ollama CPU binary tree

Place a pre-built CPU-only Ollama tarball into `local/ollama/`.

Expected contents:

```
ollama
llama/
  build/linux-amd64/runners/
    cpu_avx/ollama_llama_server
    cpu_avx2/ollama_llama_server
```

```bash
cp /path/to/ollama-cpu-build-v0.5.7.tar.gz local/ollama/
```

**Important:** the binary must be linked against a glibc version
compatible with the base image (Ubuntu 26.04 / glibc 2.43). Building
the binary on a different distribution will cause runtime failures.

## Step 3 – Base image (when the build host has no internet)

```bash
# On an online machine
docker pull ubuntu:26.04
docker save ubuntu:26.04 -o ubuntu-26.04.tar

# On the offline machine
cp ubuntu-26.04.tar local/debian/
docker load -i local/debian/ubuntu-26.04.tar
```

## Step 4 – Build

```bash
./scripts/build-image.sh
# or:
docker build -t ravi-ollama:cpu -f docker/Dockerfile.ollama-cpu .
```

`build-image.sh` will load the base tarball if needed, verify assets,
and run the build.

## Step 5 – Save the final image (optional)

```bash
docker save ravi-ollama:cpu | gzip > /usr/share/ravi/ollama-cpu.tar.gz
# or
docker save ravi-ollama:cpu | gzip > local/ollama-cpu.tar.gz
```

After this point the target machine does not need internet for the
runtime image.
