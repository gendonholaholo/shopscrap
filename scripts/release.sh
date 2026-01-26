#!/bin/bash
# ============================================================================
# Shopee Scraper - Manual Release Script
# ============================================================================
#
# Usage:
#   ./scripts/release.sh [patch|minor|major]
#   ./scripts/release.sh              # patch release (0.3.0 -> 0.3.1)
#   ./scripts/release.sh minor        # minor release (0.3.0 -> 0.4.0)
#   ./scripts/release.sh major        # major release (0.3.0 -> 1.0.0)
#
# Prerequisites:
#   - Docker logged in: docker login
#   - Git configured with push access
#   - On feature branch or dev branch
#
# ============================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Docker Hub repository
DOCKER_REPO="${DOCKER_REPO:-jogiia/shopee-scraper}"

# Get current version from pyproject.toml
get_version() {
    grep -m1 'version = ' pyproject.toml | cut -d'"' -f2
}

# Bump version
bump_version() {
    local current_version=$1
    local bump_type=$2

    IFS='.' read -r major minor patch <<< "$current_version"

    case $bump_type in
        major)
            major=$((major + 1))
            minor=0
            patch=0
            ;;
        minor)
            minor=$((minor + 1))
            patch=0
            ;;
        patch|*)
            patch=$((patch + 1))
            ;;
    esac

    echo "${major}.${minor}.${patch}"
}

# Update version in pyproject.toml
update_version() {
    local new_version=$1
    sed -i.bak "s/^version = \".*\"/version = \"${new_version}\"/" pyproject.toml
    rm -f pyproject.toml.bak
}

# Print step header
step() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# Print success
success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Print warning
warning() {
    echo -e "${YELLOW}! $1${NC}"
}

# Print error and exit
error() {
    echo -e "${RED}✗ $1${NC}"
    exit 1
}

# ============================================================================
# Main Release Flow
# ============================================================================

main() {
    local bump_type="${1:-patch}"
    local current_version=$(get_version)
    local new_version=$(bump_version "$current_version" "$bump_type")
    local current_branch=$(git branch --show-current)

    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║          SHOPEE SCRAPER - RELEASE SCRIPT                   ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "  Current version: ${current_version}"
    echo "  New version:     ${new_version}"
    echo "  Bump type:       ${bump_type}"
    echo "  Current branch:  ${current_branch}"
    echo "  Docker repo:     ${DOCKER_REPO}"
    echo ""

    # Confirm release
    read -p "Continue with release? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Release cancelled."
        exit 0
    fi

    # ========================================================================
    # Step 1: Run CI Checks
    # ========================================================================
    step "Step 1/7: Running CI checks (lint, type-check, test)"

    echo "→ Formatting code..."
    uv run ruff format src tests
    uv run ruff check --fix src tests || true

    echo "→ Running linter..."
    uv run ruff check src tests || error "Linting failed"
    success "Linting passed"

    echo "→ Running type checker..."
    uv run mypy src || warning "Type checking has warnings (continuing)"

    echo "→ Running tests..."
    uv run pytest tests -v || error "Tests failed"
    success "All tests passed"

    # ========================================================================
    # Step 2: Update version
    # ========================================================================
    step "Step 2/7: Updating version to ${new_version}"

    update_version "$new_version"
    success "Version updated in pyproject.toml"

    # ========================================================================
    # Step 3: Commit version bump
    # ========================================================================
    step "Step 3/7: Committing version bump"

    git add pyproject.toml
    git commit -m "chore: bump version to ${new_version}" || warning "Nothing to commit"
    success "Version bump committed"

    # ========================================================================
    # Step 4: Sync and merge to dev
    # ========================================================================
    step "Step 4/7: Syncing and merging to dev"

    echo "→ Fetching from origin..."
    git fetch origin

    if [[ "$current_branch" != "dev" ]]; then
        echo "→ Pushing current branch..."
        git push origin "$current_branch"

        echo "→ Switching to dev..."
        git checkout dev
        git pull origin dev

        echo "→ Merging ${current_branch} into dev..."
        git merge "$current_branch" --no-ff -m "Merge ${current_branch} into dev for v${new_version}"
    fi

    git push origin dev
    success "Dev branch updated"

    # ========================================================================
    # Step 5: Merge to main
    # ========================================================================
    step "Step 5/7: Merging dev to main"

    git checkout main
    git pull origin main
    git merge dev --no-ff -m "Release v${new_version}"
    git push origin main
    success "Main branch updated"

    # ========================================================================
    # Step 6: Create and push git tag
    # ========================================================================
    step "Step 6/7: Creating git tag v${new_version}"

    git tag -a "v${new_version}" -m "Release v${new_version}"
    git push origin "v${new_version}"
    success "Tag v${new_version} pushed"

    # ========================================================================
    # Step 7: Build and push Docker image
    # ========================================================================
    step "Step 7/7: Building and pushing Docker image"

    echo "→ Building Docker image..."
    docker build -t shopee-scraper .

    echo "→ Tagging image..."
    docker tag shopee-scraper "${DOCKER_REPO}:v${new_version}"
    docker tag shopee-scraper "${DOCKER_REPO}:latest"

    echo "→ Pushing to Docker Hub..."
    docker push "${DOCKER_REPO}:v${new_version}"
    docker push "${DOCKER_REPO}:latest"
    success "Docker image pushed to ${DOCKER_REPO}"

    # ========================================================================
    # Done!
    # ========================================================================
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                    RELEASE COMPLETE!                       ║${NC}"
    echo -e "${GREEN}╠════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║  Version:  v${new_version}                                        ║${NC}"
    echo -e "${GREEN}║  Git Tag:  v${new_version}                                        ║${NC}"
    echo -e "${GREEN}║  Docker:   ${DOCKER_REPO}:v${new_version}             ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    # Return to original branch
    if [[ "$current_branch" != "main" && "$current_branch" != "dev" ]]; then
        git checkout "$current_branch"
        success "Returned to ${current_branch}"
    fi
}

# Run main
main "$@"
