# Development Scripts

Automated scripts for Fantasy Crypto Tournament backend development.

## Quick Start

All tasks are integrated into VS Code/Cursor:

1. Press `Ctrl+Shift+P` (Windows) or `Cmd+Shift+P` (macOS)
2. Select **Tasks: Run Task**
3. Choose the task from the list

## Available Tasks

### Testing

- **Run Tests** - run all tests
- **Run Tests with Coverage** - tests with coverage report
- **Run Single Test File** - run current test file

**CLI alternatives:**
```powershell
# All tests
pytest -v

# With coverage
.\scripts\run_tests.ps1 -Coverage

# Single file
.\scripts\run_tests.ps1 -File tests/test_scoring.py

# By keyword
.\scripts\run_tests.ps1 -Keyword "tournament"

# Fail fast (stop on first failure)
.\scripts\run_tests.ps1 -FailFast
```

### Linting and Formatting

- **Lint (Ruff)** - check code for errors
- **Lint & Fix (Ruff)** - auto-fix issues
- **Format (Ruff)** - format code
- **Type Check (mypy)** - type checking
- **Full Check** - all checks at once

**CLI alternatives:**
```powershell
# Check only
.\scripts\lint.ps1

# With autofix
.\scripts\lint.ps1 -Fix

# With type check
.\scripts\lint.ps1 -TypeCheck

# All together
.\scripts\lint.ps1 -All

# Specific path
.\scripts\lint.ps1 -Fix -Path api/routes/tournaments.py
```

### Database Migrations

- **Create Migration** - create new migration
- **Run Migrations** - apply migrations
- **Rollback Migration** - rollback last migration
- **Show Migration History** - migration history

**CLI alternatives:**
```powershell
# Create migration (interactive)
.\scripts\create_migration.ps1

# With message
.\scripts\create_migration.ps1 -Message "add user notifications table"

# Apply migrations
alembic upgrade head

# Rollback last
alembic downgrade -1

# History
alembic history --verbose

# Current version
alembic current
```

### Docker Environment

- **Start Dev Environment** - start dev environment
- **Stop Dev Environment** - stop
- **Restart Dev Environment** - restart
- **Show Dev Logs** - show logs

**CLI alternatives:**
```powershell
# Start
.\scripts\docker_dev.ps1 start

# Stop
.\scripts\docker_dev.ps1 stop

# Restart
.\scripts\docker_dev.ps1 restart

# Status
.\scripts\docker_dev.ps1 status

# Logs
.\scripts\docker_dev.ps1 logs -Follow

# Logs for specific service
.\scripts\docker_dev.ps1 logs -Service postgres -Follow

# Rebuild (takes a while)
.\scripts\docker_dev.ps1 rebuild

# Clean all (including DB)
.\scripts\docker_dev.ps1 clean
```

### Code Generators

- **Create New Endpoint** - create new API endpoint

**CLI alternative:**
```powershell
# Interactive
.\scripts\create_endpoint.ps1

# With resource name
.\scripts\create_endpoint.ps1 -Name notification
```

#### What is created when generating an endpoint:

1. **Router** (`api/routes/{resource}s.py`):
   - GET /resources - list
   - GET /resources/{id} - single item
   - POST /resources - create (with auth)
   - DELETE /resources/{id} - delete (with auth)
   - Pydantic schemas (Request/Response)
   - Error handling

2. **Service** (`services/{resource}_service.py`):
   - CRUD operations
   - Logging
   - Transaction handling

3. **Tests** (`tests/test_{resource}.py`):
   - Tests for all endpoints
   - Auth checks
   - Placeholders for extension

**After generation:**
1. Create model in `models/{resource}_models.py`
2. Update service to work with the model
3. Register router in `main.py`
4. Create migration for the model
5. Run tests

### NFT Base URI (Local Testing)

When testing NFT packs locally, the HodleagueCards contract must point to your backend for metadata. Use the set_nft_base_uri script:

```powershell
# 1. Add to .env:
#    NFT_METADATA_BASE_URL=https://YOUR_NGROK.ngrok-free.app/nft/cards/
#    NFT_ADMIN_PRIVATE_KEY=0x... (deployer key)

# 2. Expose local backend: ngrok http 8000

# 3. Run script
python -m scripts.set_nft_base_uri
```

**E2E pack open (on-chain, two-step):** `python scripts/test_pack_open_e2e.py --api-url http://localhost:8000 --pack-type-id 1` (backend + .env with Fuji contracts and keys).

**Deploy and run after contract/backend changes (commit-reveal + abandoned-commit job):**
1. **Contract:** Deploy or upgrade HodleaguePacks (must have `commitOpen`, `revealOpen`, `relayerRevealOpen`, `getCommit`). Point `.env` to the proxy address.
2. **Migrations:** `alembic upgrade head` (adds `commit_id`, `relayer_tx_hash` on pack_openings).
3. **Backend:** Restart the API (e.g. docker-compose restart or uvicorn) so scheduler loads the abandoned-commit job (runs every 1h; reveals for users who burned a pack but never revealed, after `ABANDONED_COMMIT_REVEAL_HOURS`, default 24).
4. **Test:** `python scripts/test_pack_open_e2e.py --api-url http://localhost:8000 --pack-type-id 1`.

### Dev Server

- **Run Server (Dev)** - run uvicorn with hot-reload

```powershell
# Or directly
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Keyboard Shortcuts

You can configure shortcuts in VS Code/Cursor:

1. `Ctrl+Shift+P` -> **Preferences: Open Keyboard Shortcuts (JSON)**
2. Add:

```json
[
  {
    "key": "ctrl+shift+t",
    "command": "workbench.action.tasks.runTask",
    "args": "Run Tests"
  },
  {
    "key": "ctrl+shift+l",
    "command": "workbench.action.tasks.runTask",
    "args": "Full Check (Lint + Format + Type)"
  }
]
```

## Recommended Workflow

### Before Commit
```powershell
# 1. Check code
.\scripts\lint.ps1 -All

# 2. Run tests
.\scripts\run_tests.ps1 -Coverage

# 3. Check coverage
# Open htmlcov/index.html in browser
```

### Creating a New Feature
```powershell
# 1. Create endpoint
.\scripts\create_endpoint.ps1 -Name feature

# 2. Create model (manually)
# models/feature_models.py

# 3. Create migration
.\scripts\create_migration.ps1 -Message "add feature table"

# 4. Update service (manually)
# services/feature_service.py

# 5. Run tests
.\scripts\run_tests.ps1 -File tests/test_feature.py

# 6. Run lint
.\scripts\lint.ps1 -Fix
```

## Installing Dev Dependencies

```powershell
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

## Troubleshooting

### PowerShell Execution Policy
If scripts do not run:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Ruff not found
```powershell
pip install ruff
```

### mypy not found
```powershell
pip install mypy
```

### pytest-cov not found
```powershell
pip install pytest-cov
```

## Additional Info

All scripts are in `scripts/`:
- `create_endpoint.ps1` - endpoint generator
- `create_migration.ps1` - create migrations
- `run_tests.ps1` - run tests
- `lint.ps1` - lint and format
- `docker_dev.ps1` - Docker management

VS Code tasks are in `.vscode/tasks.json`.
