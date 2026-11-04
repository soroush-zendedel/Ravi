# Comprehensive Step-by-Step Execution Guide: Extracting Ravi into an Independent Git Repository

Document Version: 2.0  
Status: Final & Actionable  
Language: English  

---

## 1. Executive Summary & Objective

This guide provides precise, step-by-step instructions (including exact Git, Docker, and PowerShell/Bash commands) to extract the **Ravi** AI infrastructure from the current monolithic repository (`soroush-zendedel.github.io`) into a brand-new, independent open-source Git repository named `ravi` under the MIT license. 

To ensure complete safety and clean history separation, we will use a **Branch-First Extraction Strategy**:
1. Create a dedicated `ravi` branch from the current monolithic repository.
2. Reorganize and clean up files within this branch to form the standalone `ravi` repository structure.
3. Completely detach this branch from `main` (without merging back) to become the standalone `ravi` repository.
4. Clean up and remove all Ravi traces from the monolithic `main` branch.

---

## 2. Phase 1: Creating and Isolating the `ravi` Branch

### Step 1.1: Create and Switch to the `ravi` Branch
Open your terminal in the workspace root and run the following Git command to create and switch to a new branch named `ravi`:

```powershell
git checkout -b ravi
```

### Step 1.2: Verify Current Status
Check that all tracked files are intact in the new branch:

```powershell
git status
```

---

## 3. Phase 2: Restructuring and Customizing for `ravi`

In this phase, we reorganize the files into the independent repository structure and update container names, database names, and Docker volumes to use the `ravi` prefix (`ravi-redis`, `ravi-postgres`, `ravi-proxy`, database `ravi`, and volumes `ravi_redis_data`, `ravi_postgres_data`).

### Step 3.1: Create Required Directories
Create the necessary directories for the standalone repository layout:

```powershell
mkdir -p docs/architecture docs/api docs/deployment
mkdir -p src/core src/integrations src/routing
mkdir -p tests/unit tests/integration
mkdir -p docker/litellm
mkdir -p scripts
```

### Step 3.2: Move and Rename Files
1. Move [`ravi.main.md`](ravi.main.md) to `docs/architecture/ravi.main.md`.
2. Keep [`config.yaml`](config.yaml), [`docker-compose.yml`](docker-compose.yml), and [`docker/litellm/transformation.py`](docker/litellm/transformation.py) in their designated locations.
3. Update [`docker-compose.yml`](docker-compose.yml) to use the `ravi` naming convention. Here is the exact recommended configuration for `docker-compose.yml`:

```yaml
version: '3.8'

services:
  redis:
    image: redis:7-alpine
    container_name: ravi-redis
    restart: unless-stopped
    ports:
      - "6379:6379"
    volumes:
      - ravi_redis_data:/data
    networks:
      - ravi-network

  db:
    image: postgres:18
    container_name: ravi-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: ravi
      POSTGRES_USER: ${POSTGRES_USER:-ravi}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env}
    ports:
      - "5432:5432"
    volumes:
      - ravi_postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d ravi"]
      interval: 5s
      timeout: 5s
      retries: 5
    networks:
      - ravi-network

  litellm:
    image: ghcr.io/berriai/litellm:v1.106.6
    container_name: ravi-proxy
    restart: unless-stopped
    ports:
      - "4000:4000"
    environment:
      DATABASE_URL: postgresql://${POSTGRES_USER:-ravi}:${POSTGRES_PASSWORD}@db:5432/ravi
      LITELLM_MASTER_KEY: ${LITELLM_MASTER_KEY}
      CLOUDFLARE_AI_BASE_URL: ${CLOUDFLARE_AI_BASE_URL}
      CLOUDFLARE_API_TOKEN: ${CLOUDFLARE_API_TOKEN}
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - ./docker/litellm/transformation.py:/app/.venv/lib/python3.13/site-packages/litellm/llms/cloudflare/chat/transformation.py:ro
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_started
    networks:
      - ravi-network

volumes:
  ravi_redis_data:
  ravi_postgres_data:

networks:
  ravi-network:
    driver: bridge
```

### Step 3.3: Create Helper Scripts (`scripts/Start-Ravi.ps1` and `scripts/Stop-Ravi.ps1`)
Create `scripts/Start-Ravi.ps1`:
```powershell
# Start Ravi AI Infrastructure
Write-Host "Starting Ravi AI Infrastructure..." -ForegroundColor Green
docker compose up -d --build
Write-Host "Ravi is running at http://127.0.0.1:4000" -ForegroundColor Cyan
```

Create `scripts/Stop-Ravi.ps1`:
```powershell
# Stop Ravi AI Infrastructure
Write-Host "Stopping Ravi AI Infrastructure..." -ForegroundColor Yellow
docker compose down
Write-Host "Ravi stopped successfully." -ForegroundColor Green
```

### Step 3.4: Create Root Documentation and License Files
1. Create `LICENSE` with the MIT License text.
2. Create a comprehensive `README.md` for `ravi` detailing its purpose, architecture, and deployment guide.
3. Create `.env.example`:
```env
POSTGRES_USER=ravi
POSTGRES_PASSWORD=your_secure_postgres_password_here
LITELLM_MASTER_KEY=sk-ravi-master-key-here
CLOUDFLARE_AI_BASE_URL=https://api.cloudflare.com/client/v4/accounts/YOUR_ACCOUNT_ID/ai/v1
CLOUDFLARE_API_TOKEN=your_cloudflare_api_token_here
```

### Step 3.5: Commit Changes in the `ravi` Branch
Stage and commit all standalone changes:
```powershell
git add .
git commit -m "feat: structure standalone Ravi repository architecture and compose config"
```

---

## 4. Phase 3: Initializing the Standalone Remote Repository

To detach the `ravi` branch into its own brand-new Git repository while preserving its commit history:

```powershell
# Create a temporary orphan branch or initialize a new git repo in a separate directory, OR push the ravi branch to a new remote repository:
git remote set-url origin <YOUR_NEW_RAVI_GIT_REPOSITORY_URL>
git push -u origin ravi
```
*(Alternatively, you can clone the current repo into a clean folder, checkout `ravi`, remove the old remote, and add the new `ravi` remote URL).*

---

## 5. Phase 4: Cleaning Up the Monolithic Repository (`main`)

Now that `ravi` is fully isolated and extracted, we must completely remove all traces, configuration files, patches, and scripts of Ravi from the monolithic repository (`soroush-zendedel.github.io` on branch `main`).

### Step 4.1: Switch back to `main`
```powershell
git checkout main
```

### Step 4.2: Remove Ravi Files and Artifacts
Execute the following commands to delete Ravi-specific files from the monolithic repository:
```powershell
# Remove Docker transformation patch
git rm -rf docker/litellm/transformation.py

# Remove old scripts
git rm -rf scripts/Start-LiteLLM.ps1 scripts/Stop-LiteLLM.ps1

# Remove root configuration & docker compose files if they belonged solely to Ravi
git rm config.yaml docker-compose.yml

# Remove ravi main markdown document if it's no longer part of DevOS docs
git rm ravi.main.md
```

### Step 4.3: Clean `.env` and `.env.example`
Remove any `LITELLM_*` or `CLOUDFLARE_*` environment variables from `.env.example` and local `.env` files in the monolithic repository.

### Step 4.4: Update Monolithic Documentation
Update [`README.md`](README.md) in the monolithic repository (DevOS) to state that AI infrastructure is now handled externally via the independent **Ravi** service (`http://127.0.0.1:4000`), providing connection instructions via standard OpenAI-compatible API keys.

### Step 4.5: Commit Cleanup on `main`
```powershell
git add .
git commit -m "chore: completely remove Ravi module and LiteLLM infrastructure in favor of independent Ravi service"
git push origin main
```

---

## 6. Phase 5: Verification and Post-Extraction Validation

1. **Verify Independent Ravi Setup:**
   - Navigate to your Ravi workspace/repository directory.
   - Configure `.env` from `.env.example`.
   - Run `docker compose up -d --build`.
   - Test endpoints: `http://127.0.0.1:4000/health` and `http://127.0.0.1:4000/chat/completions`.
2. **Verify Monolithic Cleanup:**
   - Run `docker compose config` in the DevOS repository to ensure no missing references remain.
   - Confirm all site assets, HTML files (`index.html`, `projects.html`), and frontend styles build and run successfully without Ravi dependencies.
