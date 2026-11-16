# Troubleshooting

## “Docker command not found” / “Docker daemon is not running”

- Ensure `docker` or `docker.exe` is available.
- On WSL, start Docker Desktop and confirm `docker.exe info` works.
- Under `sudo`, PATH may not include Windows paths; the CLI also
  searches common Docker Desktop locations under `/mnt/c/Users/...`.

## “Could not obtain image 'ravi-ollama:cpu'”

1. Build it:
   ```bash
   ./scripts/build-image.sh
   ```
2. Or place a saved tarball:
   ```bash
   sudo cp ollama-cpu.tar.gz /usr/share/ravi/
   ravi start
   ```
3. Or temporarily use the official image:
   ```bash
   export OLLAMA_IMAGE=ollama/ollama
   ravi start
   ```

## “GLIBC_2.43 not found” during build or runtime

The Ollama binary was built against a newer glibc than the base image
provides. The project defaults to `ubuntu:26.04` (glibc 2.43). Rebuild
the binary on a matching system, or change `FROM` in the Dockerfile to
match the environment where the binary was compiled.

## Container starts but “API took longer than expected”

Warning only. On slow disks Ollama may take 30–60 s. Wait and retry
`ravi status` or `ravi run list`.

## “No models found in persistent volume”

Pull a model first:

```bash
ravi run pull qwen2.5:0.5b
```

## Models disappeared after `ravi uninstall`

They should not. `uninstall` only removes the container. Verify:

```bash
docker volume ls | grep models
ravi status
```

## Port 11434 already in use

Another process (often another Ollama instance) is bound to the port.

```bash
docker ps -a
# stop or remove the conflicting container, or change the host port
# in tools/ravi/lib/container.sh (the -p line)
```

## `ENDOFFILE: not found` or similar script errors

Ensure you are using the current scripts from the repository. Re-copy
`scripts/build-image.sh` and re-run.
