# Typical Workflow

## First-time setup (online preparation machine)

1. Clone the repository.
2. Fetch Ubuntu packages:
   ```bash
   ./scripts/fetch-debs.sh \
       --mirror http://archive.ubuntu.com/ubuntu \
       --suite resolute \
       --no-security
   ```
3. Place the pre-built Ollama CPU tarball:
   ```bash
   cp ollama-cpu-build-v0.5.7.tar.gz local/ollama/
   ```
4. (Optional) Save the base image:
   ```bash
   docker pull ubuntu:26.04
   docker save ubuntu:26.04 -o local/debian/ubuntu-26.04.tar
   ```
5. Build the image:
   ```bash
   ./scripts/build-image.sh
   ```
6. (Optional) Save the final image for offline transfer:
   ```bash
   docker save ravi-ollama:cpu | gzip > ollama-cpu.tar.gz
   ```

## Deployment on the target machine

1. Copy the project (or the CLI plus `ollama-cpu.tar.gz`) to the target.
2. Install the CLI:
   ```bash
   sudo ./install.sh
   ```
3. If the image was not built on this machine, place the tarball:
   ```bash
   sudo mkdir -p /usr/share/ravi
   sudo cp ollama-cpu.tar.gz /usr/share/ravi/
   ```
4. Start the service:
   ```bash
   ravi install
   ```
5. Pull a model (requires network on the target, or a pre-populated volume):
   ```bash
   ravi run pull qwen2.5:0.5b
   ```
6. Chat:
   ```bash
   ravi
   ```

## Day-to-day use

```bash
ravi status          # health check
ravi logs            # follow logs
ravi stop / start    # control the container
ravi run list        # list models
ravi run pull …      # download more models
ravi                 # interactive chat
```

Models remain in the Docker volume `models` across restarts and uninstalls.
