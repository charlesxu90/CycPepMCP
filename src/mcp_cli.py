#!/usr/bin/env python3
"""
CycPepMCP CLI - Main Command Line Interface

Provides unified access to CycPepMCP functionality through subcommands:
- cpmcp create: Create new MCP servers from repositories
- cpmcp avail: Show all available MCP servers to install
- cpmcp status: Show downloaded and installed MCP servers
- cpmcp install: Install MCP servers
- cpmcp uninstall: Uninstall MCP servers
"""

import sys
import click
from pathlib import Path
from typing import Optional

from .cycpep_mcp.install_mcp import show_available_mcps, show_status, install_mcp_cmd, uninstall_mcp_cmd, search_mcps, show_info

# Logo for CycPepMCP
LOGO = """\033[36m
   ____           ____           __  __  ____ ____
  / ___|   _  ___|  _ \\ ___ _ __|  \\/  |/ ___| _  \\
 | |  | | | |/ __| |_) / _ \\ '_ | |\\/| | |   | |_) |
 | |__| |_| | (__|  __/  __/ |_)| |  | | |___|  __/
  \\____\\__, |\\___|_|   \\___| .__/|_|  |_|\\____|_|
       |___/               |_|
\033[0m"""


@click.group(invoke_without_command=True)
@click.version_option(version="0.1.0", prog_name="cycpepmcp")
@click.pass_context
def cli(ctx):
    """
    CycPepMCP - Cyclic Peptide Engineering Model Context Protocol Package

    A comprehensive toolkit for creating, installing, and managing MCP servers
    for cyclic peptide design, non-natural amino acids, and peptide engineering.
    """
    click.echo(LOGO)

    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command(name="avail")
@click.option('--local', is_flag=True, help='Show local MCPs only')
@click.option('--public', is_flag=True, help='Show public MCPs only')
def avail_command(local: bool, public: bool):
    """
    Show all available MCP servers that can be installed.

    By default, shows both local MCPs (developed in MCP directory) and
    public MCPs (from public registry). Use --local or --public to filter.

    Examples:

      # Show all available MCPs:
      cpmcp avail

      # Show only local MCPs:
      cpmcp avail --local

      # Show only public MCPs:
      cpmcp avail --public
    """
    show_available_mcps(local_only=local, public_only=public)


@cli.command(name="status")
@click.option('--refresh', is_flag=True, help='Refresh status cache (slower but accurate)')
def status_command(refresh: bool):
    """
    Show status of downloaded and installed MCPs.

    Displays which MCPs are currently downloaded to your system and
    which ones are registered with Claude Code CLI. Use --refresh to
    update the status cache.

    Examples:

      # Show current MCP status:
      cpmcp status

      # Refresh cache and show status:
      cpmcp status --refresh
    """
    show_status(refresh_cache=refresh)


@cli.command(name="install")
@click.argument('mcp_names', nargs=-1, required=True)
@click.option('--cli', type=click.Choice(['claude', 'gemini']), default='claude',
              help='CLI tool to register with (default: claude)')
@click.option('--no-register', is_flag=True,
              help='Install only, do not register with CLI')
@click.option('--skip-env', is_flag=True,
              help='Skip environment creation (use existing env)')
@click.option('--skip-repo', is_flag=True,
              help='Skip repository cloning (repo already present)')
def install_command(mcp_names: tuple, cli: str, no_register: bool, skip_env: bool, skip_repo: bool):
    """
    Install one or more MCP servers and optionally register them with a CLI.

    By default, installs the MCPs and registers them with Claude Code.
    Use --no-register to skip CLI registration.

    The --skip-env and --skip-repo options are passed to quick_setup.sh:
    - --skip-env: Skip environment creation if env/ already exists
    - --skip-repo: Skip repository cloning if repo/ already exists

    Examples:

      # Install a single MCP:
      cpmcp install cycpep_design_mcp

      # Install multiple MCPs at once:
      cpmcp install nnaa_mcp cycpep_struct_mcp

      # Install and register with Gemini CLI:
      cpmcp install cycpep_mcp --cli gemini

      # Install only, don't register:
      cpmcp install head_to_tail_mcp --no-register

      # Install with existing environment:
      cpmcp install cycpep_mcp --skip-env

      # Install with both existing env and repo:
      cpmcp install cycpep_mcp --skip-env --skip-repo
    """
    failed = []
    for mcp_name in mcp_names:
        click.echo(f"\n{'='*60}")
        click.echo(f"Installing: {mcp_name}")
        click.echo('='*60)
        if not install_mcp_cmd(mcp_name, cli=cli, no_register=no_register,
                               skip_env=skip_env, skip_repo=skip_repo):
            failed.append(mcp_name)

    if failed:
        click.echo(f"\nFailed to install: {', '.join(failed)}")
        sys.exit(1)
    elif len(mcp_names) > 1:
        click.echo(f"\nSuccessfully installed all {len(mcp_names)} MCPs")


@cli.command(name="uninstall")
@click.argument('mcp_names', nargs=-1, required=True)
@click.option('--cli', type=click.Choice(['claude', 'gemini']), default='claude',
              help='CLI tool to unregister from (default: claude)')
@click.option('--remove-files', is_flag=True,
              help='Also remove installation files')
def uninstall_command(mcp_names: tuple, cli: str, remove_files: bool):
    """
    Uninstall one or more MCP servers from CLI and optionally remove files.

    By default, only unregisters the MCPs from the CLI. Use --remove-files
    to also delete the installation files.

    Examples:

      # Unregister a single MCP:
      cpmcp uninstall cycpep_design_mcp

      # Unregister multiple MCPs at once:
      cpmcp uninstall nnaa_mcp cycpep_struct_mcp

      # Unregister and delete files:
      cpmcp uninstall cycpep_mcp --remove-files

      # Unregister from Gemini CLI:
      cpmcp uninstall head_to_tail_mcp --cli gemini
    """
    failed = []
    for mcp_name in mcp_names:
        click.echo(f"\n{'='*60}")
        click.echo(f"Uninstalling: {mcp_name}")
        click.echo('='*60)
        if not uninstall_mcp_cmd(mcp_name, cli=cli, remove_files=remove_files):
            failed.append(mcp_name)

    if failed:
        click.echo(f"\nFailed to uninstall: {', '.join(failed)}")
        sys.exit(1)
    elif len(mcp_names) > 1:
        click.echo(f"\nSuccessfully uninstalled all {len(mcp_names)} MCPs")


@cli.command(name="search")
@click.argument('query')
def search_command(query: str):
    """
    Search for MCP servers by name or description.

    Examples:

      # Search for cyclic peptide MCPs:
      cpmcp search cyclic

      # Search for non-natural amino acid tools:
      cpmcp search nnaa
    """
    search_mcps(query)


@cli.command(name="info")
@click.argument('mcp_name')
def info_command(mcp_name: str):
    """
    Show detailed information about an MCP server.

    Examples:

      # Show info about cyclic peptide design MCP:
      cpmcp info cycpep_design_mcp

      # Show info about NNAA MCP:
      cpmcp info nnaa_mcp
    """
    show_info(mcp_name)


@cli.command(name="create")
@click.option('--github-url', '-g', default='', help='GitHub repository URL to clone')
@click.option('--local-repo-path', '-l', type=click.Path(exists=True, path_type=Path),
              help='Path to local repository (alternative to --github-url)')
@click.option('--mcp-dir', '-d', required=True, type=click.Path(path_type=Path),
              help='Target directory for MCP project')
@click.option('--use-case-filter', '-u', default='',
              help='Filter for specific use cases to focus on')
@click.option('--api-key', '-k', default='', help='API key (optional, uses Claude CLI by default)')
@click.option('--rerun-from-step', '-r', default=0, type=int,
              help='Force rerun from this step number (1-8)')
@click.option('--runtime', type=click.Choice(['uv', 'conda', 'auto']), default='auto',
              help='Runtime for deployment artifacts: uv, conda, or auto-detect (default: auto)')
def create_command(github_url: str, local_repo_path: Optional[Path], mcp_dir: Path,
                   use_case_filter: str, api_key: str, rerun_from_step: int, runtime: str):
    """
    Create an MCP server from a GitHub repository or local code.

    This pipeline will:
    1. Setup project environment
    2. Clone/copy repository
    3. Setup conda environment & scan use cases
    4. Execute common use cases
    5. Write scripts for use case functions
    6. Extract MCP tools & wrap in server
    7. Test integration
    8. Create README documentation
    9. Generate quick_setup.sh script

    Examples:

      # From GitHub repository:
      cpmcp create -g https://github.com/user/repo -d tool-mcps/my_mcp

      # From local repository:
      cpmcp create -l /path/to/repo -d tool-mcps/my_mcp

      # With use case filter:
      cpmcp create -g https://github.com/user/repo -d tool-mcps/my_mcp -u "structure prediction, sequence design"

      # Force uv runtime for lightweight MCPs:
      cpmcp create -g https://github.com/user/repo -d tool-mcps/my_mcp --runtime uv

      # Rerun from step 3:
      cpmcp create -l /path/to/repo -d tool-mcps/my_mcp -r 3
    """
    from .cycpep_mcp.create_mcp import create_mcp
    create_mcp(github_url, local_repo_path, mcp_dir, use_case_filter, api_key, rerun_from_step, runtime)


@cli.command(name="sync")
def sync_command():
    """
    Synchronize MCP registry with filesystem.

    Discovers tool MCPs in tool-mcps/ directory and adds them to the registry.

    Examples:

      # Sync registry:
      cpmcp sync
    """
    from .cycpep_mcp.install_mcp import sync_mcps
    sync_mcps()


def main():
    """Main entry point for the CLI."""
    cli()


if __name__ == '__main__':
    main()
