# Generate quick_setup.sh Script (UV Runtime)

## Role
You are an expert at creating shell setup scripts for cyclic peptide computational tools. Your mission is to create a comprehensive `quick_setup.sh` script that automates the environment setup for an MCP server using **uv** as the package manager.

## Input Parameters
- `README.md`: The README file with installation instructions
- `reports/step3_environment.md`: Environment setup details from Step 3
- `reports/setup_commands.json`: Extracted setup commands (if available)
- `repo/`: The cloned repository with original setup information
- `env/`: The environment (if already created)
- `src/server.py`: The MCP server file
- **Runtime**: `uv` — this script must use `uv venv` and `uv pip install` instead of conda/mamba.

## Task

Create a `quick_setup.sh` script in the MCP root directory that:
1. Creates a virtual environment using `uv venv`
2. Installs all dependencies using `uv pip install`
3. Sets up the MCP server
4. Supports `--help`, `--skip-env`, and `--skip-repo` options

### Step 1: Analyze Environment Requirements

1. **Read reports/step3_environment.md** to understand:
   - Python version required
   - Pip packages needed
   - Any special dependencies

2. **Read README.md** for any additional setup instructions

3. **Check repo/ directory** for:
   - `requirements.txt`
   - `setup.py` or `pyproject.toml`
   - Any install scripts

### Step 2: Create quick_setup.sh

Create a shell script with the following structure:

```bash
#!/bin/bash
# quick_setup.sh - Quick setup script for ${MCP_NAME} (uv runtime)
#
# Usage:
#   bash quick_setup.sh [options]
#
# Options:
#   --help      Show this help message
#   --skip-env  Skip environment creation (use existing env)
#   --skip-repo Skip repository cloning (repo already present)

set -e  # Exit on error

# =============================================================================
# Configuration
# =============================================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MCP_NAME="${mcp_name}"
PYTHON_VERSION="${python_version}"
REPO_URL="${repo_url}"
REPO_NAME="${repo_name}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# =============================================================================
# Helper Functions
# =============================================================================
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

show_help() {
    cat << EOF
${MCP_NAME} Quick Setup Script (uv runtime)

Usage:
    bash quick_setup.sh [options]

Options:
    --help      Show this help message
    --skip-env  Skip environment creation (use existing env)
    --skip-repo Skip repository cloning (repo already present)

Description:
    This script sets up the environment for ${MCP_NAME} MCP server using uv.
    It will:
    1. Create a virtual environment with Python ${PYTHON_VERSION} using uv
    2. Clone the source repository (if not present)
    3. Install all required dependencies via uv pip
    4. Install the MCP server dependencies (fastmcp)

Requirements:
    - uv (https://docs.astral.sh/uv/)
    - git

EOF
    exit 0
}

# =============================================================================
# Parse Arguments
# =============================================================================
SKIP_ENV=false
SKIP_REPO=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --help|-h)
            show_help
            ;;
        --skip-env)
            SKIP_ENV=true
            shift
            ;;
        --skip-repo)
            SKIP_REPO=true
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            ;;
    esac
done

# =============================================================================
# Main Setup
# =============================================================================
cd "$SCRIPT_DIR"
log_info "Setting up ${MCP_NAME} in: $SCRIPT_DIR"

# Check for uv
if ! command -v uv &> /dev/null; then
    log_error "uv not found. Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi
log_info "Using uv: $(uv --version)"

# -----------------------------------------------------------------------------
# Step 1: Clone Repository (if needed)
# -----------------------------------------------------------------------------
if [ "$SKIP_REPO" = false ]; then
    if [ -d "repo/${REPO_NAME}" ]; then
        log_info "Repository already exists at repo/${REPO_NAME}"
    else
        log_info "Cloning repository..."
        mkdir -p repo
        git clone --depth=1 "${REPO_URL}" "repo/${REPO_NAME}" || {
            log_warning "Shallow clone failed, trying full clone..."
            git clone "${REPO_URL}" "repo/${REPO_NAME}"
        }
        log_success "Repository cloned successfully"
    fi
else
    log_info "Skipping repository clone (--skip-repo)"
fi

# -----------------------------------------------------------------------------
# Step 2: Create Environment (if needed)
# -----------------------------------------------------------------------------
if [ "$SKIP_ENV" = false ]; then
    if [ -d "env" ]; then
        log_warning "Environment already exists at ./env"
        read -p "Do you want to remove and recreate it? [y/N] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            log_info "Removing existing environment..."
            rm -rf env
        else
            log_info "Keeping existing environment"
            SKIP_ENV=true
        fi
    fi

    if [ "$SKIP_ENV" = false ]; then
        log_info "Creating virtual environment with Python ${PYTHON_VERSION} using uv..."
        uv venv env --python ${PYTHON_VERSION}
        log_success "Virtual environment created successfully"
    fi
else
    log_info "Skipping environment creation (--skip-env)"
fi

# Verify environment exists
if [ ! -f "env/bin/python" ]; then
    log_error "Environment not found at ./env/bin/python"
    log_error "Please run without --skip-env to create it"
    exit 1
fi

# -----------------------------------------------------------------------------
# Step 3: Install Dependencies
# -----------------------------------------------------------------------------
log_info "Installing dependencies..."

# Install from requirements.txt if exists
if [ -f "requirements.txt" ]; then
    log_info "Installing from requirements.txt..."
    uv pip install --python env/bin/python -r requirements.txt
fi

# Install from repo requirements if exists
if [ -f "repo/${REPO_NAME}/requirements.txt" ]; then
    log_info "Installing from repo requirements.txt..."
    uv pip install --python env/bin/python -r "repo/${REPO_NAME}/requirements.txt"
fi

# Install additional dependencies
# ${PIP_PACKAGES}

# Install fastmcp for MCP server
log_info "Installing MCP dependencies..."
uv pip install --python env/bin/python fastmcp loguru requests

log_success "Dependencies installed successfully"

# -----------------------------------------------------------------------------
# Step 4: Post-install Setup (if any)
# -----------------------------------------------------------------------------
# ${POST_INSTALL_COMMANDS}

# -----------------------------------------------------------------------------
# Step 5: Verify Installation
# -----------------------------------------------------------------------------
log_info "Verifying installation..."

# Test Python environment
./env/bin/python -c "import sys; print(f'Python {sys.version}')" || {
    log_error "Python environment verification failed"
    exit 1
}

# Test MCP server import
./env/bin/python -c "from src.server import mcp; print('MCP server import OK')" 2>/dev/null || {
    log_warning "MCP server import test skipped (server may not be ready yet)"
}

# Test fastmcp
./env/bin/python -c "import fastmcp; print(f'fastmcp {fastmcp.__version__}')" || {
    log_error "fastmcp import failed"
    exit 1
}

log_success "Installation verified successfully"

# =============================================================================
# Done
# =============================================================================
echo
log_success "=============================================="
log_success "  ${MCP_NAME} setup completed! (uv runtime)"
log_success "=============================================="
echo
echo "Next steps:"
echo "  1. Register with Claude Code:"
echo "     claude mcp add ${MCP_NAME} -- \$(pwd)/env/bin/python \$(pwd)/src/server.py"
echo
echo "  2. Or use cpmcp:"
echo "     cpmcp install ${MCP_NAME}"
echo
echo "  3. Test the server:"
echo "     ./env/bin/python src/server.py"
echo
```

### Step 3: Customize the Script

Based on the analysis from Step 1, customize the script:

1. **Set correct Python version** (e.g., 3.10, 3.11, 3.12)

2. **Add pip packages** not in requirements.txt:
   ```bash
   uv pip install --python env/bin/python torch==2.4.0 --index-url https://download.pytorch.org/whl/cu118
   ```

3. **Add post-install commands** if needed:
   ```bash
   # Download model weights
   ./env/bin/python -c "from repo.${REPO_NAME} import download_weights; download_weights()"
   ```

4. **Add verification tests** specific to the tool:
   ```bash
   # Test specific imports
   ./env/bin/python -c "import some_package; print('OK')"
   ```

### Step 4: Write the Script

Write the customized `quick_setup.sh` script to the MCP root directory.

## Expected Output

A `quick_setup.sh` file in the MCP root directory that:
- Is executable (`chmod +x quick_setup.sh`)
- Supports `--help`, `--skip-env`, `--skip-repo` flags
- Creates the virtual environment using `uv venv`
- Installs all dependencies using `uv pip install`
- Verifies the installation
- Provides clear next steps

## Important Notes

- **Use `uv` for all package operations** — `uv venv` for env creation, `uv pip install` for packages
- **Use `--python env/bin/python`** with `uv pip install` to target the correct environment
- **Include error handling** with `set -e` and meaningful error messages
- **Support idempotent runs** — script should work when run multiple times
- **Include verification steps** to ensure setup succeeded
- **Do NOT use conda/mamba** — this is a uv-only setup script
