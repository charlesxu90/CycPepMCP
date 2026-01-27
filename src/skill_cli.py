#!/usr/bin/env python3
"""
CycPepMCP Skill CLI - Skill Management Command Line Interface

Provides unified access to skill management functionality through subcommands:
- cpskill avail: Show all available skills to install
- cpskill status: Show installed status of skills
- cpskill info: Show detailed information about a skill
- cpskill install: Install a skill and its required MCPs
- cpskill execute: Guide through skill execution
- cpskill uninstall: Uninstall a skill and cleanup MCPs
- cpskill create: Create a new skill interactively
"""

import sys
import textwrap
from pathlib import Path
from typing import List, Tuple

import click

from .skill.skill_manager import SkillManager
from .skill.create_skill import SkillCreator, interactive_add_step
from .cycpep_mcp.mcp_manager import MCPManager


def check_required_mcps(required_mcps: List[str], cli: str = "claude") -> Tuple[List[str], List[str]]:
    """
    Check if required MCPs are installed and registered.

    Args:
        required_mcps: List of MCP names to check
        cli: CLI tool to check registration against

    Returns:
        Tuple of (available_mcps, missing_mcps)
    """
    mcp_manager = MCPManager()
    available = []
    missing = []

    for mcp_name in required_mcps:
        mcp = mcp_manager.get_mcp(mcp_name)
        if mcp and mcp.is_registered(cli):
            available.append(mcp_name)
        else:
            missing.append(mcp_name)

    return available, missing


@click.group(invoke_without_command=True)
@click.version_option(version="0.1.0", prog_name="cpskill")
@click.pass_context
def cli(ctx):
    """
    CycPepMCP Skill Manager - Workflow Skills for Claude Code

    A toolkit for installing and managing workflow skills that combine
    multiple MCP servers into cohesive cyclic peptide engineering workflows.
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command(name="avail")
def avail_command():
    """
    Show all available skills that can be installed.

    Scans the workflow-skills directory and displays all skills
    with their descriptions.

    Examples:

      # Show all available skills:
      cpskill avail
    """
    manager = SkillManager()
    click.echo("Finding available skills in 'workflow-skills/'...")
    skills = manager.load_available_skills()

    if not skills:
        click.echo("  No skills found.")
        return

    click.echo("\nAvailable Skills:")
    click.echo("=" * 60)
    for name, skill in sorted(skills.items()):
        desc = skill.description[:70] + "..." if len(skill.description) > 70 else skill.description
        click.echo(f"  {name:<30} {desc}")
    click.echo(f"\nTotal: {len(skills)} skills found.")


@cli.command(name="status")
def status_command():
    """
    Show the installation status of all skills.

    Displays which skills are currently installed and registered
    with Claude Code.

    Examples:

      # Show skill installation status:
      cpskill status
    """
    manager = SkillManager()
    click.echo("Checking skill installation status...")
    skills = manager.load_available_skills()

    if not skills:
        click.echo("  No skills found to check.")
        return

    click.echo("\nSkill Status:")
    click.echo("=" * 60)
    for name, skill in sorted(skills.items()):
        status = skill.get_status()
        click.echo(f"  {name:<30} {status}")
    click.echo()


@cli.command(name="info")
@click.argument('skill_name')
def info_command(skill_name: str):
    """
    Show detailed information about a skill.

    Displays the skill description, required MCPs, cleanup MCPs,
    and installation status.

    Examples:

      # Show info about cycpep_design skill:
      cpskill info cycpep_design
    """
    manager = SkillManager()
    skill = manager.get_skill(skill_name)

    if not skill:
        click.echo(f"Skill '{skill_name}' not found.", err=True)
        sys.exit(1)

    click.echo(f"\nDetails for Skill: {skill.name}")
    click.echo("=" * 60)
    click.echo(f"  Description: {skill.description}")
    click.echo(f"  File Path: {skill.file_path}")
    click.echo(f"  Status: {skill.get_status()}")
    click.echo(f"  Command Name: '{skill.command_name}'")

    required_mcps = skill.get_required_mcps()
    if required_mcps:
        available, missing = check_required_mcps(required_mcps)

        click.echo(f"\n  Required MCPs ({len(required_mcps)}):")
        for mcp in required_mcps:
            status = "[+]" if mcp in available else "[-]"
            click.echo(f"    {status} {mcp}")

        if missing:
            click.echo(f"\n  {len(missing)} MCP(s) not registered. Install with:")
            click.echo(f"      cpskill install {skill_name}")
    click.echo()


@cli.command(name="install")
@click.argument('skill_name')
def install_command(skill_name: str):
    """
    Install a skill and its required MCP servers.

    Downloads and registers the skill with Claude Code, then installs
    all MCP servers required by the skill.

    Examples:

      # Install the cycpep_design skill:
      cpskill install cycpep_design
    """
    manager = SkillManager()
    success = manager.install_skill_and_mcps(skill_name)
    if not success:
        sys.exit(1)


@cli.command(name="execute")
@click.argument('skill_name')
def execute_command(skill_name: str):
    """
    Guide through the execution of an installed skill.

    Displays step-by-step prompts that you can copy and paste
    into your conversation with the assistant.

    Examples:

      # Execute the cycpep_design skill:
      cpskill execute cycpep_design
    """
    manager = SkillManager()
    skill = manager.get_skill(skill_name)

    if not skill:
        click.echo(f"Skill '{skill_name}' not found.", err=True)
        sys.exit(1)

    required_mcps = skill.get_required_mcps()
    if required_mcps:
        click.echo(f"\nChecking required MCPs for '{skill_name}'...")
        available, missing = check_required_mcps(required_mcps)

        if missing:
            click.echo(f"\nMissing required MCPs ({len(missing)}):")
            for mcp in missing:
                click.echo(f"    - {mcp}")
            click.echo(f"\nPlease install the skill first:")
            click.echo(f"    cpskill install {skill_name}")
            click.echo(f"\n   Or install MCPs manually:")
            click.echo(f"    cpmcp install {' '.join(missing)}")
            sys.exit(1)

        click.echo(f"All {len(available)} required MCPs are available")

    click.echo(f"\nExecuting Skill: {skill.name}")
    click.echo("=" * 70)
    click.echo("This will guide you through the steps defined in the skill file.")
    click.echo("Copy and paste the prompts into your conversation with the assistant.")
    click.echo("=" * 70)

    steps = skill.get_execution_steps()
    if not steps:
        click.echo("\nNo executable steps (prompts) found in this skill.")
        return

    for i, step in enumerate(steps, 1):
        click.echo(f"\n--- Step {i}: {step['title']} ---")
        click.echo("\nPrompt to copy:")
        prompt_block = textwrap.indent(step['prompt'], "    ")
        click.echo(prompt_block)

        if i < len(steps):
            click.prompt("\nPress Enter to continue to the next step", default="", show_default=False)


@cli.command(name="uninstall")
@click.argument('skill_name')
def uninstall_command(skill_name: str):
    """
    Uninstall a skill and clean up its MCP servers.

    Removes the skill from Claude Code and optionally uninstalls
    associated MCP servers.

    Examples:

      # Uninstall the cycpep_design skill:
      cpskill uninstall cycpep_design
    """
    manager = SkillManager()
    success = manager.uninstall_skill_and_mcps(skill_name)
    if not success:
        sys.exit(1)


# =============================================================================
# Skill Creation Commands
# =============================================================================

@cli.group(name="create")
def create_group():
    """
    Create new skills interactively.

    Use these subcommands to create new workflow skills by recording
    steps as you test MCP tools.

    Workflow:
      1. cpskill create init <skill_name>
      2. Test MCP tools interactively in Claude Code
      3. cpskill create add-step <skill_name> (repeat for each step)
      4. cpskill create generate <skill_name>
      5. cpskill install <skill_name>
    """
    pass


@create_group.command(name="init")
@click.argument('skill_name')
@click.option('--description', '-d', default="", help='Skill description')
@click.option('--mcps', '-m', multiple=True, help='Required MCP servers (can be repeated)')
def create_init_command(skill_name: str, description: str, mcps: tuple):
    """
    Initialize a new skill with a steps file template.

    Creates a template steps file that you can edit to add steps,
    or use the add-step command interactively.

    Examples:

      # Initialize a new cyclic peptide design skill:
      cpskill create init cycpep_design -d "Design cyclic peptides" -m cycpep_mcp

      # Initialize with multiple MCPs:
      cpskill create init my_skill -m mcp1 -m mcp2
    """
    creator = SkillCreator(skill_name)
    mcps_list = list(mcps) if mcps else None
    creator.init_skill(description=description, required_mcps=mcps_list)


@create_group.command(name="add-step")
@click.argument('skill_name')
@click.option('--title', '-t', default=None, help='Step title (interactive if not provided)')
@click.option('--prompt', '-p', default=None, help='Step prompt (interactive if not provided)')
def create_add_step_command(skill_name: str, title: str, prompt: str):
    """
    Add a step to the skill interactively or with options.

    Adds a new step to the skill's steps file. If title and prompt
    are not provided, enters interactive mode.

    Examples:

      # Add step interactively:
      cpskill create add-step cycpep_design

      # Add step with options:
      cpskill create add-step cycpep_design -t "Generate config" -p "Generate a config..."
    """
    creator = SkillCreator(skill_name)
    if title and prompt:
        creator.add_step(title=title, prompt=prompt)
    else:
        interactive_add_step(creator)


@create_group.command(name="list-steps")
@click.argument('skill_name')
def create_list_steps_command(skill_name: str):
    """
    List all steps in the skill's steps file.

    Displays the steps that have been recorded for the skill.

    Examples:

      # List steps for cycpep_design:
      cpskill create list-steps cycpep_design
    """
    creator = SkillCreator(skill_name)
    steps = creator.list_steps()
    if steps:
        click.echo(f"\nSteps in '{skill_name}':")
        click.echo("-" * 40)
        for step in steps:
            click.echo(f"  Step {step['number']}: {step['title']}")
        click.echo()
    else:
        click.echo("No steps found.")


@create_group.command(name="generate")
@click.argument('skill_name')
@click.option('--description', '-d', default=None, help='Override description')
@click.option('--mcps', '-m', multiple=True, help='Override required MCPs')
def create_generate_command(skill_name: str, description: str, mcps: tuple):
    """
    Generate the skill file from the steps file.

    Transforms the steps file into a full skill markdown file and
    updates the configs.yaml to register the skill.

    Examples:

      # Generate skill from steps:
      cpskill create generate cycpep_design

      # Generate with overrides:
      cpskill create generate cycpep_design -d "New description" -m mcp1 -m mcp2
    """
    creator = SkillCreator(skill_name)
    mcps_list = list(mcps) if mcps else None
    creator.generate_skill(description=description, required_mcps=mcps_list)


@create_group.command(name="from-steps")
@click.argument('steps_file', type=click.Path(exists=True))
@click.option('--description', '-d', default=None, help='Override description')
@click.option('--mcps', '-m', multiple=True, help='Override required MCPs')
def create_from_steps_command(steps_file: str, description: str, mcps: tuple):
    """
    Generate a skill from an existing steps file.

    Useful when you've manually edited a steps file or have one
    from a previous session.

    Examples:

      # Generate from existing steps file:
      cpskill create from-steps workflow-skills/my_steps.md

      # With overrides:
      cpskill create from-steps my_steps.md -d "Description" -m mcp1
    """
    steps_path = Path(steps_file)
    creator = SkillCreator.from_steps_file(steps_path)
    if creator:
        mcps_list = list(mcps) if mcps else None
        creator.generate_skill(description=description, required_mcps=mcps_list)
    else:
        sys.exit(1)


def main():
    """Main entry point for the CLI."""
    cli()


if __name__ == '__main__':
    main()
