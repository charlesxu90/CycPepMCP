#!/usr/bin/env python3
"""
MCPManager Class - Manages collections of MCPs and maintains YAML registries
"""

import re
from pathlib import Path
from typing import Optional, Dict, Any
import yaml

from .mcp import (
    MCP,
    MCPScope,
    MCPStatus,
    PUBLIC_MCPS_CONFIG,
    MCPS_CONFIG,
    PUBLIC_MCPS_DIR,
    PROJECT_ROOT,
    resolve_path,
    make_relative_path,
)


# =============================================================================
# MCPManager Class - Manages collections of MCPs
# =============================================================================

class MCPManager:
    """
    Manages available (public) and installed MCPs using YAML config files.

    - Public MCPs: src/configs/public_mcps.yaml
    - Installed MCPs: src/configs/mcps.yaml
    """

    def __init__(
        self,
        public_config: Path = PUBLIC_MCPS_CONFIG,
        installed_config: Path = MCPS_CONFIG
    ):
        """
        Initialize MCPManager.

        Args:
            public_config: Path to public MCPs YAML config
            installed_config: Path to installed MCPs YAML config
        """
        self.public_config = Path(public_config)
        self.installed_config = Path(installed_config)
        self._public_mcps_cache: Optional[Dict[str, MCP]] = None
        self._installed_mcps_cache: Optional[Dict[str, MCP]] = None
        self._ensure_configs_exist()

    # -------------------------------------------------------------------------
    # Configuration Management
    # -------------------------------------------------------------------------

    def _ensure_configs_exist(self):
        """Ensure configuration files exist"""
        if not self.public_config.exists():
            self.public_config.parent.mkdir(parents=True, exist_ok=True)
            with open(self.public_config, "w") as f:
                f.write("mcps: {}\n")

        if not self.installed_config.exists():
            self.installed_config.parent.mkdir(parents=True, exist_ok=True)
            with open(self.installed_config, "w") as f:
                f.write("mcps: {}\n")

    # -------------------------------------------------------------------------
    # Loading Methods
    # -------------------------------------------------------------------------

    def load_public_mcps(self, force_reload: bool = False) -> Dict[str, MCP]:
        """
        Load public MCPs from YAML config.

        Args:
            force_reload: If True, bypass cache and reload from file

        Returns:
            Dictionary of MCP objects keyed by name
        """
        if self._public_mcps_cache is not None and not force_reload:
            return self._public_mcps_cache

        try:
            with open(self.public_config, "r") as f:
                config = yaml.safe_load(f)

            if config is None:
                config = {}

            raw_mcps = config.get("mcps", {})
            mcps = {}

            for name, info in raw_mcps.items():
                try:
                    if info is None:
                        info = {}
                    if 'name' not in info:
                        info['name'] = name
                    mcps[name] = MCP(**info)
                except Exception as e:
                    print(f"Failed to load MCP '{name}': {e}")

            self._public_mcps_cache = mcps
            return mcps

        except Exception as e:
            print(f"Failed to load public MCPs config: {e}")
            return {}

    def load_installed_mcps(self, force_reload: bool = False) -> Dict[str, MCP]:
        """
        Load installed MCPs from YAML config.

        Args:
            force_reload: If True, bypass cache and reload from file

        Returns:
            Dictionary of MCP objects keyed by name
        """
        if self._installed_mcps_cache is not None and not force_reload:
            return self._installed_mcps_cache

        try:
            with open(self.installed_config, "r") as f:
                config = yaml.safe_load(f)

            if config is None:
                config = {}

            raw_mcps = config.get("mcps", {})
            mcps = {}

            for name, info in raw_mcps.items():
                try:
                    if info is None:
                        info = {}
                    if 'name' not in info:
                        info['name'] = name
                    mcps[name] = MCP(**info)
                except Exception as e:
                    print(f"Failed to load MCP '{name}': {e}")

            self._installed_mcps_cache = mcps
            return mcps

        except Exception as e:
            print(f"Failed to load installed MCPs config: {e}")
            return {}

    # -------------------------------------------------------------------------
    # Saving Methods
    # -------------------------------------------------------------------------

    def save_public_mcps(self, mcps: Dict[str, MCP]):
        """Save public MCPs to YAML config."""
        mcps_dict = {}
        for name, mcp in mcps.items():
            mcp_data = mcp.to_dict()
            mcp_data.pop('name', None)
            if 'path' in mcp_data and mcp_data['path']:
                mcp_data['path'] = make_relative_path(mcp_data['path'])
            mcps_dict[name] = mcp_data

        with open(self.public_config, "w") as f:
            yaml.safe_dump({"mcps": mcps_dict}, f, default_flow_style=False)

        self._public_mcps_cache = mcps

    def save_installed_mcps(self, mcps: Dict[str, MCP]):
        """Save installed MCPs to YAML config."""
        mcps_dict = {}
        for name, mcp in mcps.items():
            mcp_data = mcp.to_dict()
            mcp_data.pop('name', None)
            if 'path' in mcp_data and mcp_data['path']:
                mcp_data['path'] = make_relative_path(mcp_data['path'])
            mcps_dict[name] = mcp_data

        with open(self.installed_config, "w") as f:
            yaml.safe_dump({"mcps": mcps_dict}, f, default_flow_style=False)

        self._installed_mcps_cache = mcps

    # -------------------------------------------------------------------------
    # CRUD Operations
    # -------------------------------------------------------------------------

    def add_public_mcp(self, mcp: MCP):
        """Add a new public MCP to registry."""
        mcps = self.load_public_mcps()
        mcps[mcp.name] = mcp
        self.save_public_mcps(mcps)
        print(f"Added '{mcp.name}' to public MCPs registry")

    def remove_public_mcp(self, name: str) -> bool:
        """Remove a public MCP from registry."""
        mcps = self.load_public_mcps()
        if name in mcps:
            del mcps[name]
            self.save_public_mcps(mcps)
            print(f"Removed '{name}' from public MCPs registry")
            return True
        else:
            print(f"MCP '{name}' not found in public registry")
            return False

    def add_installed_mcp(self, mcp: MCP):
        """Add an MCP to installed registry."""
        mcps = self.load_installed_mcps()
        mcps[mcp.name] = mcp
        self.save_installed_mcps(mcps)
        print(f"Added '{mcp.name}' to installed MCPs registry")

    def remove_installed_mcp(self, name: str) -> bool:
        """Remove an MCP from installed registry."""
        mcps = self.load_installed_mcps()
        if name in mcps:
            del mcps[name]
            self.save_installed_mcps(mcps)
            print(f"Removed '{name}' from installed MCPs registry")
            return True
        else:
            print(f"MCP '{name}' not found in installed registry")
            return False

    # -------------------------------------------------------------------------
    # Query Methods
    # -------------------------------------------------------------------------

    def get_mcp(self, name: str) -> Optional[MCP]:
        """Get an MCP by name (searches both public and installed)."""
        installed = self.load_installed_mcps()
        if name in installed:
            return installed[name]

        public = self.load_public_mcps()
        if name in public:
            return public[name]

        return None

    def get_public_mcp(self, name: str) -> Optional[MCP]:
        """Get a public MCP by name"""
        return self.load_public_mcps().get(name)

    def get_installed_mcp(self, name: str) -> Optional[MCP]:
        """Get an installed MCP by name"""
        return self.load_installed_mcps().get(name)

    def list_mcps(
        self,
        source: Optional[str] = None,
        runtime: Optional[str] = None,
        installed_only: bool = False,
        public_only: bool = False
    ) -> Dict[str, MCP]:
        """List MCPs with optional filters."""
        results = {}

        if not public_only:
            results.update(self.load_installed_mcps())

        if not installed_only:
            results.update(self.load_public_mcps())

        if source:
            results = {k: v for k, v in results.items() if v.source == source}

        if runtime:
            results = {k: v for k, v in results.items() if v.runtime == runtime}

        return results

    def search_mcps(self, query: str) -> Dict[str, MCP]:
        """Search MCPs by name or description."""
        query = query.lower()
        results = {}

        all_mcps = self.list_mcps()

        for name, mcp in all_mcps.items():
            if (query in name.lower() or
                query in mcp.description.lower() or
                query in mcp.source.lower()):
                results[name] = mcp

        return results

    # -------------------------------------------------------------------------
    # High-level Operations
    # -------------------------------------------------------------------------

    def install_mcp(self, name: str, force: bool = False,
                    skip_env: bool = False, skip_repo: bool = False) -> bool:
        """
        Install an MCP by name.

        Args:
            name: Name of the MCP to install
            force: If True, re-install even if already installed
            skip_env: If True, skip environment creation (passed to quick_setup.sh)
            skip_repo: If True, skip repository cloning (passed to quick_setup.sh)

        Returns:
            True if successful, False otherwise
        """
        mcp = self.get_mcp(name)
        if not mcp:
            print(f"MCP '{name}' not found")
            return False

        success = mcp.install(force=force, skip_env=skip_env, skip_repo=skip_repo)

        if success:
            self.add_installed_mcp(mcp)

        return success

    def uninstall_mcp(self, name: str, remove_files: bool = True) -> bool:
        """Uninstall an MCP by name."""
        mcp = self.get_installed_mcp(name)
        if not mcp:
            print(f"MCP '{name}' not found in installed registry")
            return False

        success = mcp.uninstall(remove_files=remove_files)

        if success:
            self.remove_installed_mcp(name)

        return success

    def register_mcp(
        self,
        name: str,
        cli: str = "claude",
        scope: MCPScope = MCPScope.GLOBAL
    ) -> bool:
        """Register an MCP with CLI."""
        mcp = self.get_mcp(name)
        if not mcp:
            print(f"MCP '{name}' not found")
            return False

        return mcp.register(cli=cli, scope=scope)

    def unregister_mcp(self, name: str, cli: str = "claude") -> bool:
        """Unregister an MCP from CLI."""
        mcp = self.get_mcp(name)
        if not mcp:
            print(f"MCP '{name}' not found")
            return False

        return mcp.unregister(cli=cli)

    def install_and_register(
        self,
        name: str,
        cli: str = "claude",
        scope: MCPScope = MCPScope.GLOBAL,
        force: bool = False,
        skip_env: bool = False,
        skip_repo: bool = False
    ) -> bool:
        """
        Install and register an MCP in one operation.

        Args:
            name: Name of the MCP to install
            cli: CLI tool to register with ("claude" or "gemini")
            scope: Registration scope (project or global)
            force: If True, re-install even if already installed
            skip_env: If True, skip environment creation (passed to quick_setup.sh)
            skip_repo: If True, skip repository cloning (passed to quick_setup.sh)

        Returns:
            True if successful, False otherwise
        """
        if not self.install_mcp(name, force=force, skip_env=skip_env, skip_repo=skip_repo):
            return False

        return self.register_mcp(name, cli=cli, scope=scope)

    # -------------------------------------------------------------------------
    # Discovery Methods
    # -------------------------------------------------------------------------

    def discover_tool_mcps(self, skip_public_dir: bool = True) -> Dict[str, MCP]:
        """
        Discover and configure MCPs from tool-mcps directory.
        """
        from .mcp import TOOL_MCPS_DIR

        mcps = {}

        if not TOOL_MCPS_DIR.exists():
            return mcps

        for item in TOOL_MCPS_DIR.iterdir():
            if not item.is_dir():
                continue

            if skip_public_dir and item.name == "public":
                continue
            if item.name in [".git", "__pycache__", "mcp.status"]:
                continue

            mcp_config = self._detect_mcp_config(item)
            if mcp_config:
                mcps[mcp_config['name']] = MCP(**mcp_config)

        return mcps

    def _detect_mcp_config(self, mcp_dir: Path) -> Optional[Dict[str, Any]]:
        """Detect MCP configuration from directory structure."""
        name = mcp_dir.name
        description = "Tool MCP from local repository"
        runtime = "python"
        python_version = "3.10"
        server_command = "python"
        server_args = []
        setup_script = ""
        setup_commands = []
        env_vars = {}
        dependencies = []

        # Check for quick_setup.sh first (preferred setup method)
        quick_setup = mcp_dir / "quick_setup.sh"
        if quick_setup.exists():
            setup_script = "quick_setup.sh"

        # Extract description from README
        readme = mcp_dir / "README.md"
        if readme.exists():
            try:
                content = readme.read_text()
                lines = content.split("\n")

                for line in lines:
                    line = line.strip()
                    if not line or line.startswith("#") or line.startswith("```"):
                        continue
                    line = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', line)
                    if len(line) > 10:
                        description = line[:100] + "..." if len(line) > 100 else line
                        break
            except:
                pass

        # Detect Python version from environment
        env_python = mcp_dir / "env" / "bin" / "python"
        if env_python.exists():
            try:
                import subprocess
                result = subprocess.run(
                    [str(env_python), "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result.returncode == 0:
                    python_version = result.stdout.strip()
            except:
                pass

        # Detect entry point
        entry_points = [
            mcp_dir / "src" / f"{name.replace('_mcp', '_mcp')}.py",
            mcp_dir / "src" / "mcp.py",
            mcp_dir / "src" / "server.py",
            mcp_dir / f"{name}.py",
            mcp_dir / "server.py",
        ]

        if "_server_" in name or "_" in name:
            short_name = name.replace("_server", "").replace("_mcp", "_mcp")
            entry_points.insert(0, mcp_dir / "src" / f"{short_name}.py")

        entry_point = None
        for ep in entry_points:
            if ep.exists():
                entry_point = ep
                break

        if not entry_point:
            return None

        try:
            relative_entry = entry_point.relative_to(mcp_dir)
            server_args = [str(relative_entry)]
        except ValueError:
            server_args = [str(entry_point)]

        # Only detect setup commands if no setup_script (legacy fallback)
        if not setup_script:
            if (mcp_dir / "setup.py").exists() or (mcp_dir / "pyproject.toml").exists():
                setup_commands.append("pip install -e .")
            elif (mcp_dir / "requirements.txt").exists():
                setup_commands.append("pip install -r requirements.txt")
            else:
                setup_commands.append("pip install fastmcp requests")

        # Check for Node.js MCPs
        if (mcp_dir / "package.json").exists():
            runtime = "node"
            server_command = "node"
            if (mcp_dir / "build" / "index.js").exists():
                server_args = ["build/index.js"]
            elif (mcp_dir / "dist" / "index.js").exists():
                server_args = ["dist/index.js"]
            elif (mcp_dir / "index.js").exists():
                server_args = ["index.js"]
            else:
                return None

            if not setup_script:
                setup_commands = ["npm install"]
                if (mcp_dir / "tsconfig.json").exists():
                    setup_commands.append("npm run build")

        return {
            "name": name,
            "description": description,
            "source": "Tool",
            "runtime": runtime,
            "python_version": python_version,
            "server_command": server_command,
            "server_args": server_args,
            "setup_script": setup_script,
            "setup_commands": setup_commands,
            "env_vars": env_vars,
            "dependencies": dependencies,
            "path": str(mcp_dir),
        }

    def discover_and_add_tool_mcps(self, overwrite: bool = False) -> Dict[str, MCP]:
        """Discover tool MCPs and add them to installed registry."""
        print("Discovering tool MCPs from tool-mcps directory...")

        tool_mcps = self.discover_tool_mcps()

        if not tool_mcps:
            print("   No tool MCPs found.")
            return {}

        print(f"   Found {len(tool_mcps)} tool MCPs\n")

        installed = self.load_installed_mcps()
        added = {}
        skipped = {}
        updated = {}

        for name, mcp in tool_mcps.items():
            if name in installed and not overwrite:
                skipped[name] = mcp
                print(f"   Skipped '{name}' (already in registry)")
            elif name in installed and overwrite:
                installed[name] = mcp
                updated[name] = mcp
                print(f"   Updated '{name}'")
            else:
                installed[name] = mcp
                added[name] = mcp
                print(f"   Added '{name}'")

        self.save_installed_mcps(installed)

        print(f"\nDiscovery complete:")
        print(f"   Added: {len(added)}")
        print(f"   Updated: {len(updated)}")
        print(f"   Skipped: {len(skipped)}")
        print(f"   Total in registry: {len(installed)}")

        return {**added, **updated}

    # -------------------------------------------------------------------------
    # Display Methods
    # -------------------------------------------------------------------------

    def print_mcps(self, mcps: Dict[str, MCP], title: str = "MCPs"):
        """Pretty print MCPs."""
        if not mcps:
            print(f"\n{title}: None")
            return

        print(f"\n{title}")
        print("=" * 80)

        sources = {}
        for name, mcp in mcps.items():
            source = mcp.source
            if source not in sources:
                sources[source] = []
            sources[source].append((name, mcp))

        for source, mcp_list in sorted(sources.items()):
            print(f"\n  [{source}]")
            for name, mcp in sorted(mcp_list):
                status = mcp.get_status()
                status_icon = {
                    MCPStatus.NOT_INSTALLED: "o",
                    MCPStatus.INSTALLED: "*",
                    MCPStatus.REGISTERED: "~",
                    MCPStatus.BOTH: "+"
                }.get(status, "o")

                desc = mcp.description[:50] + "..." if len(mcp.description) > 50 else mcp.description
                print(f"    {status_icon} {name:<20} [{mcp.runtime:<6}] {desc}")

        print(f"\n  Total: {len(mcps)} MCPs")
        print()


# =============================================================================
# Global Instance
# =============================================================================

mcp_manager = MCPManager()


if __name__ == "__main__":
    print("MCPManager Class")
    print("=" * 80)

    manager = MCPManager()

    print("\n1. Listing all public MCPs:")
    public = manager.load_public_mcps()
    manager.print_mcps(public, "Public MCPs")
