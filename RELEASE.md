# Release Process

This document describes the manual CI/CD release process for Shopee Scraper.

## Quick Release

Use the automated release script:

```bash
# Patch release (0.3.0 -> 0.3.1)
./scripts/release.sh

# Minor release (0.3.0 -> 0.4.0)
./scripts/release.sh minor

# Major release (0.3.0 -> 1.0.0)
./scripts/release.sh major
```

## Prerequisites

1. **Docker logged in**:
   ```bash
   docker login
   ```

2. **Git configured** with push access to origin

3. **On feature branch** or dev branch

## Release Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     MANUAL CI/CD FLOW                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. DEVELOPMENT (feature branch)                                │
│     ├── Write code                                              │
│     ├── Run linting: make lint                                  │
│     ├── Run tests: make test                                    │
│     └── Commit changes                                          │
│                                                                 │
│  2. SYNC & MERGE TO DEV                                         │
│     ├── git fetch origin                                        │
│     ├── git checkout dev                                        │
│     ├── git pull origin dev                                     │
│     ├── git merge feature/xxx --no-ff                           │
│     └── git push origin dev                                     │
│                                                                 │
│  3. SYNC & MERGE TO MAIN                                        │
│     ├── git checkout main                                       │
│     ├── git pull origin main                                    │
│     ├── git merge dev --no-ff                                   │
│     └── git push origin main                                    │
│                                                                 │
│  4. VERSION & TAG                                               │
│     ├── Update version in pyproject.toml                        │
│     ├── git tag -a v0.x.x -m "Release v0.x.x"                   │
│     └── git push origin --tags                                  │
│                                                                 │
│  5. BUILD & PUSH TO DOCKER HUB                                  │
│     ├── docker build -t shopee-scraper .                        │
│     ├── docker tag ... jogiia/shopee-scraper:v0.x.x             │
│     ├── docker tag ... jogiia/shopee-scraper:latest             │
│     └── docker push jogiia/shopee-scraper --all-tags            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Manual Steps

### Step 1: Run CI Checks

```bash
# Format and lint
make format
make lint

# Type check
make type-check

# Run tests
make test
```

Or run all checks at once:

```bash
make ci
```

### Step 2: Update Version

Edit `pyproject.toml`:

```toml
[project]
version = "0.4.0"  # Update this
```

Commit the change:

```bash
git add pyproject.toml
git commit -m "chore: bump version to 0.4.0"
```

### Step 3: Merge to Dev

```bash
git fetch origin
git checkout dev
git pull origin dev
git merge feature/your-branch --no-ff
git push origin dev
```

### Step 4: Merge to Main

```bash
git checkout main
git pull origin main
git merge dev --no-ff -m "Release v0.4.0"
git push origin main
```

### Step 5: Create Git Tag

```bash
make git-tag
# or manually:
git tag -a v0.4.0 -m "Release v0.4.0"
git push origin v0.4.0
```

### Step 6: Build and Push Docker

```bash
make docker-push
# or manually:
docker build -t shopee-scraper .
docker tag shopee-scraper jogiia/shopee-scraper:v0.4.0
docker tag shopee-scraper jogiia/shopee-scraper:latest
docker push jogiia/shopee-scraper:v0.4.0
docker push jogiia/shopee-scraper:latest
```

## Makefile Commands

| Command | Description |
|---------|-------------|
| `make version` | Show current version |
| `make check` | Run lint + type-check + test |
| `make ci` | Full CI (format + check) |
| `make git-sync` | Sync current branch with origin |
| `make git-tag` | Create and push git tag |
| `make docker-build` | Build Docker image |
| `make docker-tag` | Tag with version and latest |
| `make docker-push` | Push to Docker Hub |
| `make release` | Full release (ci + docker-push + git-tag) |

## Customize Docker Repository

Override the default Docker Hub repository:

```bash
# Environment variable
export DOCKER_REPO=yourusername/shopee-scraper
make docker-push

# Or inline
make docker-push DOCKER_REPO=yourusername/shopee-scraper

# Or in release script
DOCKER_REPO=yourusername/shopee-scraper ./scripts/release.sh
```

## Version Scheme

We follow [Semantic Versioning](https://semver.org/):

- **MAJOR** (1.0.0): Breaking API changes
- **MINOR** (0.4.0): New features, backward compatible
- **PATCH** (0.3.1): Bug fixes, backward compatible

## Docker Tags

Each release creates two Docker tags:

- `jogiia/shopee-scraper:v0.4.0` - Specific version
- `jogiia/shopee-scraper:latest` - Latest stable
