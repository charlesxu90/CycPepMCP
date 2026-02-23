#!/usr/bin/env python3
"""
MCP Installation Tool

List and install MCP servers from:
1. Local MCPs (tool-mcps/) - from src/configs/mcps.yaml
2. Public MCPs (tool-mcps/public/) - from src/configs/public_mcps.yaml

Usage:
    cpmcp avail                   # Show all available MCPs
    cpmcp avail --local           # Show local MCPs only
    cpmcp avail --public          # Show public MCPs only
    cpmcp status                  # Show downloaded/installed status
    cpmcp status --refresh        # Refresh cache (slower)
    cpmcp install <mcp_name>      # Install and register with Claude Code
    cpmcp install <mcp_name> --cli gemini  # Install with Gemini CLI
    cpmcp install <mcp_name> --no-register # Install only, don't register
    cpmcp search <query>          # Search MCPs
    cpmcp info <mcp_name>         # Show MCP details
    cpmcp uninstall <mcp_name>    # Unregister MCP from CLI
"""

from .mcp_manager import MCPManager
from .mcp import MCPStatus


# =============================================================================
# Global MCP Manager Instance
# =============================================================================

mcp_manager = MCPManager()


# =============================================================================
# Core Functions
# =============================================================================

def show_available_mcps(local_only: bool = False, public_only: bool = False) -> None:
    """Show all available MCPs that can be installed."""

    local_mcps = {}
    public_mcps = {}

    if not public_only:
        local_mcps = mcp_manager.load_installed_mcps()

    if not local_only:
        public_mcps = mcp_manager.load_public_mcps()

    if local_mcps and not public_only:
        print("\nMCPs in CycPepMCP (located in tool-mcps/ if installed)")
        print("=" * 80)
        print("\n  Available local MCPs:")
        for name, mcp in sorted(local_mcps.items()):
            desc = mcp.description[:60] + "..." if len(mcp.description) > 60 else mcp.description
            print(f"    * {name:<25} [{mcp.runtime:<6}] {desc}")
        print(f"\n  Total: {len(local_mcps)} local MCPs")

    if public_mcps and not local_only:
        print("\nPublic MCPs (from public registry, located in tool-mcps/public if installed)")
        print("=" * 80)

        sources = {}
        for name, mcp in public_mcps.items():
            source = mcp.source
            if source not in sources:
                sources[source] = []
            sources[source].append((name, mcp))

        for source, mcp_list in sorted(sources.items()):
            print(f"\n  [{source}]")
            for name, mcp in sorted(mcp_list):
                desc = mcp.description[:60] + "..." if len(mcp.description) > 60 else mcp.description
                print(f"    * {name:<25} [{mcp.runtime:<6}] {desc}")

        print(f"\n  Total: {len(public_mcps)} public MCPs")

    if not local_mcps and not public_mcps:
        print("  No MCPs found.")

    print()


def show_status(refresh_cache: bool = False) -> None:
    """Show status of downloaded and installed MCPs."""

    if refresh_cache:
        from .status_cache import get_cache
        cache = get_cache()
        cache.invalidate()
        print("Cache invalidated, fetching fresh status...\n")

    local_mcps = mcp_manager.load_installed_mcps()
    public_mcps = mcp_manager.load_public_mcps()

    all_mcps = {}
    all_mcps.update(public_mcps)
    all_mcps.update(local_mcps)

    downloaded = {}
    registered = {}
    both = {}

    for name, mcp in all_mcps.items():
        status = mcp.get_status()
        if status == MCPStatus.BOTH:
            both[name] = mcp
        elif status == MCPStatus.INSTALLED:
            downloaded[name] = mcp
        elif status == MCPStatus.REGISTERED:
            registered[name] = mcp

    print("MCP Status Overview")
    print("=" * 80)

    if both:
        print("\n[+] Downloaded & Registered with Claude:")
        for name, mcp in sorted(both.items()):
            desc = mcp.description[:50] + "..." if len(mcp.description) > 50 else mcp.description
            scope = "Local" if name in local_mcps else "Public"
            print(f"    * {name:<25} [{scope:<7}] [{mcp.runtime:<6}] {desc}")
        print(f"\n  Total: {len(both)} MCPs")

    if downloaded:
        print("\n[*] Downloaded but not registered with Claude:")
        for name, mcp in sorted(downloaded.items()):
            desc = mcp.description[:50] + "..." if len(mcp.description) > 50 else mcp.description
            scope = "Local" if name in local_mcps else "Public"
            print(f"    * {name:<25} [{scope:<7}] [{mcp.runtime:<6}] {desc}")
        print(f"\n  Total: {len(downloaded)} MCPs")
        print(f"  Tip: Register with 'cpmcp install <mcp_name>'")

    if registered:
        print("\n[~] Registered but not downloaded:")
        for name, mcp in sorted(registered.items()):
            desc = mcp.description[:50] + "..." if len(mcp.description) > 50 else mcp.description
            scope = "Local" if name in local_mcps else "Public"
            print(f"    * {name:<25} [{scope:<7}] [{mcp.runtime:<6}] {desc}")
        print(f"\n  Total: {len(registered)} MCPs")

    if not both and not downloaded and not registered:
        print("\n  No MCPs downloaded or installed.")
        print("  Use 'cpmcp avail' to see available MCPs")
        print("  Use 'cpmcp install <mcp_name>' to install")

    print()


def install_mcp_cmd(mcp_name: str, cli: str = "claude", no_register: bool = False,
                    skip_env: bool = False, skip_repo: bool = False) -> bool:
    """
    Install an MCP and optionally register it with the specified CLI.

    Args:
        mcp_name: Name of the MCP to install
        cli: CLI tool to register with ("claude" or "gemini")
        no_register: If True, only install without registering
        skip_env: If True, skip environment creation (passed to quick_setup.sh)
        skip_repo: If True, skip repository cloning (passed to quick_setup.sh)

    Returns:
        True if successful, False otherwise
    """
    mcp = mcp_manager.get_mcp(mcp_name)

    if not mcp:
        print(f"MCP '{mcp_name}' not found.")
        print(f"   Run 'cpmcp avail' to see available MCPs.")
        return False

    mcp.invalidate_status_cache(cli)

    status = mcp.get_status(cli, use_cache=False)
    print(f"\nCurrent status: {status.value}")

    if status in [MCPStatus.NOT_INSTALLED, MCPStatus.REGISTERED]:
        print(f"\nInstalling '{mcp_name}'...")
        if mcp.setup_script:
            print(f"  Using setup script: {mcp.setup_script}")
            if skip_env:
                print(f"  --skip-env: Will skip environment creation")
            if skip_repo:
                print(f"  --skip-repo: Will skip repository cloning")
        if not mcp_manager.install_mcp(mcp_name, skip_env=skip_env, skip_repo=skip_repo):
            return False
    else:
        print(f"MCP '{mcp_name}' already installed")

    if not no_register:
        if status in [MCPStatus.NOT_INSTALLED, MCPStatus.INSTALLED]:
            if not mcp_manager.register_mcp(mcp_name, cli=cli):
                return False
        else:
            print(f"MCP '{mcp_name}' already registered with {cli}")

    final_status = mcp.get_status(cli, use_cache=False)
    print(f"\nFinal status: {final_status.value}")

    if final_status == MCPStatus.BOTH:
        print(f"Successfully installed and registered '{mcp_name}'!")

    return True


def search_mcps(query: str) -> None:
    """Search MCPs by name or description."""
    results = mcp_manager.search_mcps(query)

    if results:
        print(f"\nSearch results for '{query}':")
        mcp_manager.print_mcps(results, f"Results for '{query}'")
    else:
        print(f"\n   No MCPs found matching '{query}'")
    print()


def show_info(mcp_name: str) -> None:
    """Show detailed info about an MCP."""
    mcp = mcp_manager.get_mcp(mcp_name)

    if not mcp:
        print(f"MCP '{mcp_name}' not found.")
        return

    status = mcp.get_status()

    print(f"\n{mcp.name}")
    print("=" * 60)
    print(f"  Description: {mcp.description}")
    print(f"  Source: {mcp.source}")
    print(f"  Runtime: {mcp.runtime}")
    print(f"  Python Version: {mcp.python_version}")

    if mcp.url:
        print(f"  URL: {mcp.url}")

    if mcp.path:
        print(f"  Path: {mcp.path}")

    if mcp.docker_image:
        print(f"  Docker Image: {mcp.docker_image}")
        resolved = mcp._resolve_docker_image()
        if resolved and resolved != mcp.docker_image:
            print(f"  Active Image: {resolved} (local)")
        elif resolved:
            print(f"  Active Image: {resolved}")
        else:
            print(f"  Active Image: (not found locally)")
    if mcp.docker_args:
        print(f"  Docker Args: {' '.join(mcp.docker_args)}")

    print(f"  Status: {status.value}")
    print(f"  Installed: {'Yes' if mcp.is_installed() else 'No'}")
    print(f"  Registered (Claude): {'Yes' if mcp.is_registered('claude') else 'No'}")

    if mcp.server_command:
        print(f"  Server Command: {mcp.server_command}")

    if mcp.server_args:
        print(f"  Server Args: {' '.join(mcp.server_args)}")

    if mcp.setup_script:
        print(f"  Setup Script: {mcp.setup_script}")

    if mcp.env_vars:
        print(f"  Environment Variables:")
        for key, value in mcp.env_vars.items():
            print(f"    {key}={value}")

    if mcp.dependencies:
        print(f"  Dependencies: {', '.join(mcp.dependencies)}")

    if mcp.setup_commands:
        print(f"  Setup Commands (legacy):")
        for cmd in mcp.setup_commands:
            print(f"    - {cmd}")

    print()


def uninstall_mcp_cmd(mcp_name: str, cli: str = "claude", remove_files: bool = False) -> bool:
    """
    Uninstall MCP from CLI and optionally remove files.

    Args:
        mcp_name: Name of MCP to uninstall
        cli: CLI tool to unregister from
        remove_files: If True, also remove installation files

    Returns:
        True if successful, False otherwise
    """
    mcp = mcp_manager.get_mcp(mcp_name)

    if not mcp:
        print(f"MCP '{mcp_name}' not found.")
        return False

    if mcp.is_registered(cli):
        print(f"Unregistering '{mcp_name}' from {cli}...")
        if not mcp_manager.unregister_mcp(mcp_name, cli=cli):
            print(f"Failed to unregister, continuing...")

    if remove_files:
        if mcp.is_installed():
            print(f"Removing installation files...")
            if not mcp_manager.uninstall_mcp(mcp_name, remove_files=True):
                return False

    print(f"Successfully uninstalled '{mcp_name}'")
    return True


def sync_mcps() -> None:
    """Synchronize MCP registry with filesystem."""
    print("Synchronizing MCP registry with filesystem...")
    mcp_manager.discover_and_add_tool_mcps()
