# Known Issues & Suggestions

## Known limitations

| Issue | Severity | Notes |
|-------|----------|-------|
| Custom image `ravi-ollama:cpu` is not on a public registry | Low | Users must build it or use a pre-made tarball. |
| Binary must match base-image glibc | Medium | Default base is Ubuntu 26.04 (glibc 2.43). Mismatch causes runtime failure. |
| `wait_for_ollama_ready` times out after 30 s | Low | Container is still started; wait and retry. |
| Interactive `docker exec -it` needs a TTY | Info | Prefer `ravi run …` from non-interactive scripts. |
| WSL + sudo PATH | Low | CLI searches common Docker Desktop paths under `/mnt/c`. |

## Suggestions for future improvement

1. Configurable default model via env or `~/.config/ravi/config`.
2. Optional GPU Dockerfile (CUDA / ROCm).
3. `ravi backup` / `ravi restore` for the models volume.
4. Systemd / OpenRC unit files.
5. Signature verification for offline image tarballs.

## Reporting issues

Include:

- Output of `ravi status`
- Docker version (`docker version` or `docker.exe version`)
- Host distribution and glibc version (`ldd --version`)
- Exact command and full error message
