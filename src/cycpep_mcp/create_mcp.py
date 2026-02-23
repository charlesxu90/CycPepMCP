#!/usr/bin/env python3
"""
MCP Creation Pipeline

This script creates an MCP (Model Context Protocol) server from a GitHub/local repository with tutorials.

Steps:
1. Setup project environment and prepare working directories
2. Clone GitHub repository
3. Setup conda environment & scan common use cases
4. Execute the common use cases in repository (bugfix if needed)
5. Write script for functions to execute common use cases (test and bugfix if needed)
6. Extract MCP tools from use case scripts and wrap in MCP server (test and bugfix if needed)
7. Test Claude and Gemini integration (bugfix if needed)
8. Create comprehensive README documentation
"""

import json
from pathlib import Path
from typing import Optional, List
import click
from loguru import logger

from .mcp_creator import MCPCreator
from .mcp_manager import MCPManager
from .mcp import MCP, make_relative_path
from .status_cache import get_cache
from ..utils import run_claude_with_streaming


# ============================================================================
# Helper Functions
# ============================================================================

def extract_setup_commands_with_claude(mcp_dir: Path, prompts_dir: Path) -> List[str]:
    """
    Extract setup commands from README.md using Claude Code CLI.
    """
    prompt_file = prompts_dir / "extract_setup_commands_prompt.md"
    if not prompt_file.exists():
        logger.warning(f"  ⚠️ Prompt file not found: {prompt_file}")
        return get_default_setup_commands(mcp_dir)

    with open(prompt_file, 'r') as f:
        prompt_content = f.read()

    reports_dir = mcp_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    output_file = mcp_dir / "claude_outputs" / "setup_commands_output.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    logger.info("📝 Extracting setup commands from README using Claude...")

    success = run_claude_with_streaming(prompt_content, output_file, mcp_dir, api_key=None)

    if not success:
        logger.warning("  ⚠️ Claude extraction failed, using default setup commands")
        return get_default_setup_commands(mcp_dir)

    setup_commands_file = reports_dir / "setup_commands.json"
    if setup_commands_file.exists():
        try:
            with open(setup_commands_file, 'r') as f:
                data = json.load(f)
                commands = data.get('setup_commands', [])
                if commands:
                    logger.info(f"  ✅ Extracted {len(commands)} setup commands from README")
                    return commands
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"  ⚠️ Failed to parse setup_commands.json: {e}")

    logger.warning("  ⚠️ No setup commands extracted, using defaults")
    return get_default_setup_commands(mcp_dir)


def get_default_setup_commands(mcp_dir: Path) -> List[str]:
    """Generate default setup commands when Claude extraction fails."""
    setup_commands = []

    env_create_cmd = (
        '(command -v mamba >/dev/null 2>&1 && mamba create -p ./env python=3.10 -y) || '
        '(command -v conda >/dev/null 2>&1 && conda create -p ./env python=3.10 -y) || '
        '(echo "Warning: Neither mamba nor conda found, creating venv instead" && '
        'python3 -m venv ./env)'
    )
    setup_commands.append(env_create_cmd)

    requirements_path = mcp_dir / "requirements.txt"
    if requirements_path.exists():
        setup_commands.append('./env/bin/pip install -r requirements.txt')

    setup_commands.append('./env/bin/pip install --ignore-installed fastmcp')

    return setup_commands


def register_created_mcp(mcp_info: dict, github_url: str = "", local_repo_path: str = "") -> bool:
    """Register a newly created MCP to the mcps.yaml registry and update status cache."""
    try:
        mcp_name = mcp_info.get('name', '')
        mcp_dir = mcp_info.get('mcp_dir', '')
        server_file = mcp_info.get('server_file')
        source_url = mcp_info.get('source_url', github_url or local_repo_path)
        setup_script = mcp_info.get('setup_script', '')
        python_version = mcp_info.get('python_version', '3.10')

        if not mcp_name or not mcp_dir:
            logger.error("❌ Missing MCP name or directory in mcp_info")
            return False

        if not mcp_name.endswith('_mcp'):
            registry_name = f"{mcp_name}_mcp"
        else:
            registry_name = mcp_name

        readme_path = Path(mcp_dir) / "README.md"
        description = f"MCP created from {source_url}"
        if readme_path.exists():
            try:
                content = readme_path.read_text()
                lines = content.split("\n")
                for line in lines:
                    line = line.strip()
                    if not line or line.startswith("#") or line.startswith("```"):
                        continue
                    if len(line) > 10:
                        description = line[:100] + "..." if len(line) > 100 else line
                        break
            except Exception:
                pass

        server_args = []
        if server_file:
            server_path = Path(server_file)
            mcp_path = Path(mcp_dir)
            try:
                relative_server = server_path.relative_to(mcp_path)
                server_args = [str(relative_server)]
            except ValueError:
                server_args = [server_file]

        # Check if quick_setup.sh was generated
        quick_setup_path = Path(mcp_dir) / "quick_setup.sh"
        if quick_setup_path.exists() and not setup_script:
            setup_script = "quick_setup.sh"
            logger.info("  📜 Found quick_setup.sh, will use it for installation")

        # Only extract setup_commands if no quick_setup.sh exists (legacy fallback)
        setup_commands = []
        if not setup_script:
            script_dir = Path(__file__).parent
            prompts_dir = script_dir.parent / "prompts"
            mcp_path_obj = Path(mcp_dir)
            logger.info("📋 Extracting setup commands from README (no quick_setup.sh found)...")
            setup_commands = extract_setup_commands_with_claude(mcp_path_obj, prompts_dir)

        mcp = MCP(
            name=registry_name,
            url=github_url if github_url else "",
            description=description,
            source="Tool",
            runtime="python",
            python_version=python_version,
            server_command="python",
            server_args=server_args,
            path=mcp_dir,
            setup_script=setup_script,
            setup_commands=setup_commands,
            env_vars={},
            dependencies=[]
        )

        manager = MCPManager()
        mcps = manager.load_installed_mcps(force_reload=True)
        mcps[registry_name] = mcp
        manager.save_installed_mcps(mcps)
        logger.info(f"✅ Added '{registry_name}' to mcps.yaml registry")

        cache = get_cache()
        cache.set_status(f"{registry_name}:claude", "both")
        logger.info(f"✅ Updated status cache for '{registry_name}'")

        return True

    except Exception as e:
        logger.error(f"❌ Failed to register MCP: {e}")
        return False


# ============================================================================
# CLI Command
# ============================================================================

def create_mcp(github_url: str, local_repo_path: Optional[Path], mcp_dir: Path,
               use_case_filter: str, api_key: str, rerun_from_step: int = 0):
    """
    Create an MCP (Model Context Protocol) server from a GitHub repository or local code.
    """
    if not github_url and not local_repo_path:
        logger.error("❌ Error: Either --github-url or --local-repo-path must be provided")
        return

    if github_url and local_repo_path:
        logger.warning("⚠️  Warning: Both --github-url and --local-repo-path provided. Using --local-repo-path")

    script_dir = Path(__file__).parent
    prompts_dir = script_dir.parent / "prompts"

    if not prompts_dir.exists():
        logger.error(f"❌ Error: Prompts directory not found: {prompts_dir}")
        logger.error(f"   Please ensure prompts are in: {prompts_dir}")
        return

    mcp_dir = mcp_dir.resolve()

    logger.info("🚀 Starting MCP Creation Pipeline\n")
    if local_repo_path:
        logger.info(f"📦 Repository: {local_repo_path} (local)")
    else:
        logger.info(f"📦 Repository: {github_url} (GitHub)")
    logger.info(f"📁 MCP Directory: {mcp_dir}")
    logger.info(f"🔍 Use Case Filter: {use_case_filter or 'None'}")
    logger.info(f"🤖 Using: Claude Code CLI (logged-in account)")
    logger.info(f"📂 Prompts Directory: {prompts_dir}")
    if rerun_from_step > 0:
        logger.info(f"🔄 Rerun From Step: {rerun_from_step}")
    logger.info("\n" + "-"*50 + "\n")

    creator = MCPCreator(
        mcp_dir=mcp_dir,
        script_dir=script_dir,
        prompts_dir=prompts_dir,
        github_url=github_url,
        local_repo_path=str(local_repo_path) if local_repo_path else "",
        use_case_filter=use_case_filter,
        api_key=api_key,
        rerun_from_step=rerun_from_step
    )

    try:
        creator.run_all()

        logger.info("\n" + "="*50)
        logger.info("📝 Registering MCP to CycPepMCP registry...")
        logger.info("="*50 + "\n")

        mcp_info = creator.get_created_mcp_info()
        local_path_str = str(local_repo_path) if local_repo_path else ""

        if register_created_mcp(mcp_info, github_url=github_url, local_repo_path=local_path_str):
            mcp_name = mcp_info.get('name', '')
            registry_name = mcp_name if mcp_name.endswith('_mcp') else f"{mcp_name}_mcp"

            logger.info("\n🎉 MCP successfully created and registered!")
            logger.info(f"   View with: cpmcp status")
            logger.info(f"   Info with: cpmcp info {registry_name}")
            logger.info(f"   Install with: cpmcp install {registry_name}")
        else:
            logger.warning("\n⚠️  MCP created but failed to register to mcps.yaml")
            logger.warning("   You can manually add it using: cpmcp install <mcp_name>")

    except Exception:
        raise Exception("MCP Creation Pipeline failed")
