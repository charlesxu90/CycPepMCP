#!/usr/bin/env python3
"""
CycPepMCP - Cyclic Peptide Engineering Model Context Protocol Package

Setup script for installing CycPepMCP tools.
"""

from setuptools import setup
from pathlib import Path

# Read the README for long description
readme_path = Path(__file__).parent / "README.md"
if readme_path.exists():
    long_description = readme_path.read_text(encoding="utf-8")
else:
    long_description = "Cyclic Peptide Engineering Model Context Protocol Package"

setup(
    name="cycpepmcp",
    version="0.1.0",
    author="Charles XU",
    author_email="",
    description="Cyclic Peptide Engineering Model Context Protocol Package",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/macronex/CycPepMCP",
    packages=["cycpepmcp", "cycpepmcp.cycpep_mcp", "cycpepmcp.skill"],
    package_dir={"cycpepmcp": "src"},
    include_package_data=True,
    package_data={
        'cycpepmcp': [
            'prompts/*.md',
            'cycpep_mcp/configs/*.yaml',
            'skill/configs.yaml',
        ],
    },
    python_requires=">=3.9",
    install_requires=[
        "click>=8.0.0",
        "pyyaml>=6.0",
        "requests>=2.28.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "black>=23.0.0",
            "ruff>=0.1.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "cpmcp=cycpepmcp.mcp_cli:main",
            "cpskill=cycpepmcp.skill_cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Scientific/Engineering :: Bio-Informatics",
        "Topic :: Scientific/Engineering :: Chemistry",
    ],
    keywords=[
        "cyclic peptides",
        "peptide design",
        "non-natural amino acids",
        "MCP",
        "model context protocol",
        "Claude Code",
        "bioinformatics",
    ],
    zip_safe=False,
)
