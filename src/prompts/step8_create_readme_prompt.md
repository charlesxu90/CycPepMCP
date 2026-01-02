# Step 8: Create Comprehensive README Documentation

## Role
You are an expert technical writer and documentation specialist for cyclic peptide computational tools. Your mission is to create a clear, comprehensive README.md file for the MCP project that enables users to quickly understand, install, and use the MCP tools.

## Input Parameters
- `src/server.py`: MCP server from Step 6
- `scripts/`: Clean scripts from Step 5
- `examples/data/`: Demo data for testing
- `configs/`: Configuration files
- `env/`: Conda environment
- `reports/`: All reports from previous steps (step3_use_cases.md, step5_scripts.md, step6_mcp_tools.md, step7_integration.md)

## Prerequisites

```bash
# Determine package manager (prefer mamba over conda)
if command -v mamba &> /dev/null; then
    PKG_MGR="mamba"
else
    PKG_MGR="conda"
fi
echo "Using package manager: $PKG_MGR"
```

## Tasks

### Task 1: Gather Information from Previous Steps

1. **Read Reports**
   - `reports/step3_use_cases.md` - Use case documentation
   - `reports/step3_environment.md` - Environment setup details
   - `reports/step5_scripts.md` - Script documentation
   - `reports/step6_mcp_tools.md` - MCP tool documentation
   - `reports/step7_integration.md` - Test results

2. **Analyze Directory Structure**
   - List all scripts in `scripts/`
   - List all MCP tools in `src/server.py`
   - Identify demo data in `examples/data/`
   - Identify config files in `configs/`

3. **Extract Key Information**
   - Tool names and descriptions
   - Required parameters for each tool
   - Example data file paths
   - Config file paths

### Task 2: Create README.md Structure

Create a comprehensive README.md with the following sections:

```markdown
# ${project_name} MCP

> ${brief_description} - MCP tools for cyclic peptide computational analysis

## Table of Contents
- [Overview](#overview)
- [Installation](#installation)
- [Local Usage (Scripts)](#local-usage-scripts)
- [MCP Server Installation](#mcp-server-installation)
- [Using with Claude Code](#using-with-claude-code)
- [Using with Gemini CLI](#using-with-gemini-cli)
- [Available Tools](#available-tools)
- [Examples](#examples)
- [Troubleshooting](#troubleshooting)

## Overview

${detailed_description_of_what_this_mcp_does_for_cyclic_peptides}

### Features
- ${feature_1} (e.g., 3D structure prediction for cyclic peptides)
- ${feature_2} (e.g., Molecular property calculation)
- ${feature_3} (e.g., Permeability prediction)
- ${feature_4} (e.g., Batch processing for virtual screening)

### Directory Structure
\`\`\`
./
├── README.md               # This file
├── env/                    # Conda environment
├── src/
│   └── server.py           # MCP server
├── scripts/
│   ├── ${script_1}.py      # ${description_1}
│   ├── ${script_2}.py      # ${description_2}
│   └── lib/                # Shared utilities
├── examples/
│   └── data/               # Demo data
│       ├── sequences/      # Sample cyclic peptide sequences
│       └── structures/     # Sample 3D structures
├── configs/                # Configuration files
└── repo/                   # Original repository
\`\`\`

---

## Installation

### Prerequisites
- Conda or Mamba (mamba recommended for faster installation)
- Python 3.10+
- ${any_other_prerequisites}
- RDKit (installed automatically)

### Create Environment
Please strictly following the information in `reports/step3_environment.md` to obtain the procedure to setup the environment. An example workflow is shown below.

\`\`\`bash
# Navigate to the MCP directory
cd ${mcp_directory}

# Create conda environment (use mamba if available)
mamba create -p ./env python=3.10 -y
# or: conda create -p ./env python=3.10 -y

# Activate environment
mamba activate ./env
# or: conda activate ./env

# Install Dependencies
pip install -r requirements.txt

# Install RDKit (if not in requirements.txt)
mamba install -c conda-forge rdkit -y

# Install MCP dependencies
pip install fastmcp loguru --ignore-installed
\`\`\`

---

## Local Usage (Scripts)

You can use the scripts directly without MCP for local processing.

### Available Scripts

| Script | Description | Example |
|--------|-------------|---------|
| `scripts/${script_1}.py` | ${description_1} | See below |
| `scripts/${script_2}.py` | ${description_2} | See below |

### Script Examples

#### Predict 3D Structure

\`\`\`bash
# Activate environment
mamba activate ./env

# Run script
python scripts/predict_structure.py \\
  --smiles "cyclo(GRGDSP)" \\
  --output results/structure.pdb \\
  --num_conformers 10
\`\`\`

**Parameters:**
- `--smiles, -s`: Cyclic peptide SMILES string (required)
- `--output, -o`: Output file path (default: results/)
- `--num_conformers`: Number of conformers to generate (default: 10)

#### Calculate Properties

\`\`\`bash
python scripts/calculate_properties.py \\
  --smiles "cyclo(GRGDSP)" \\
  --properties molecular_weight,logp,tpsa
\`\`\`

---

## MCP Server Installation

### Option 1: Using fastmcp (Recommended)

\`\`\`bash
# Install MCP server for Claude Code
fastmcp install src/server.py --name cycpep-tools
\`\`\`

### Option 2: Manual Installation for Claude Code

\`\`\`bash
# Add MCP server to Claude Code
claude mcp add cycpep-tools -- $(pwd)/env/bin/python $(pwd)/src/server.py

# Verify installation
claude mcp list
\`\`\`

### Option 3: Configure in settings.json

Add to `~/.claude/settings.json`:

\`\`\`json
{
  "mcpServers": {
    "cycpep-tools": {
      "command": "${mcp_directory}/env/bin/python",
      "args": ["${mcp_directory}/src/server.py"]
    }
  }
}
\`\`\`

---

## Using with Claude Code

After installing the MCP server, you can use it directly in Claude Code.

### Quick Start

\`\`\`bash
# Start Claude Code
claude
\`\`\`

### Example Prompts

#### Tool Discovery
\`\`\`
What tools are available from cycpep-tools?
\`\`\`

#### Property Calculation (Fast)
\`\`\`
Calculate molecular properties for this cyclic peptide: cyclo(GRGDSP)
\`\`\`

#### Structure Prediction (Submit API)
\`\`\`
Submit a 3D structure prediction job for cyclo(Pro-Leu-Gly-Phe-Ala) with 20 conformers
\`\`\`

#### Check Job Status
\`\`\`
Check the status of job abc12345
\`\`\`

#### Batch Processing
\`\`\`
Calculate properties for these cyclic peptides in batch:
- cyclo(GRGDSP)
- cyclo(RGDFV)
- cyclo(YIGSR)
\`\`\`

### Using @ References

In Claude Code, use `@` to reference files and directories:

| Reference | Description |
|-----------|-------------|
| `@examples/data/sample.smi` | Reference a SMILES file |
| `@configs/default.json` | Reference a config file |
| `@results/` | Reference output directory |

---

## Using with Gemini CLI

### Configuration

Add to `~/.gemini/settings.json`:

\`\`\`json
{
  "mcpServers": {
    "cycpep-tools": {
      "command": "${mcp_directory}/env/bin/python",
      "args": ["${mcp_directory}/src/server.py"]
    }
  }
}
\`\`\`

### Example Prompts

\`\`\`bash
# Start Gemini CLI
gemini

# Example prompts (same as Claude Code)
> What tools are available?
> Calculate properties for cyclic peptide cyclo(GRGDSP)
\`\`\`

---

## Available Tools

### Quick Operations (Sync API)

These tools return results immediately (< 10 minutes):

| Tool | Description | Parameters |
|------|-------------|------------|
| `calculate_cyclic_peptide_properties` | Calculate molecular properties | `smiles`, `properties` |
| `validate_cyclic_peptide` | Validate SMILES structure | `smiles` |
| `convert_sequence_to_smiles` | Convert sequence to SMILES | `sequence`, `cyclization_type` |

### Long-Running Tasks (Submit API)

These tools return a job_id for tracking (> 10 minutes):

| Tool | Description | Parameters |
|------|-------------|------------|
| `submit_structure_prediction` | Predict 3D structure | `smiles`, `num_conformers`, `optimize` |
| `submit_conformational_sampling` | Sample conformations | `smiles`, `temperature`, `simulation_time` |
| `submit_permeability_prediction` | Predict permeability | `smiles`, `membrane_type` |
| `submit_batch_property_calculation` | Batch properties | `smiles_list`, `properties` |

### Job Management Tools

| Tool | Description |
|------|-------------|
| `get_job_status` | Check job progress |
| `get_job_result` | Get results when completed |
| `get_job_log` | View execution logs |
| `cancel_job` | Cancel running job |
| `list_jobs` | List all jobs |

---

## Examples

### Example 1: Quick Property Calculation

**Goal:** Calculate drug-like properties for a cyclic peptide

**Using Script:**
\`\`\`bash
python scripts/calculate_properties.py \\
  --smiles "cyclo(GRGDSP)" \\
  --output results/properties.json
\`\`\`

**Using MCP (in Claude Code):**
\`\`\`
Calculate molecular properties for cyclo(GRGDSP) including molecular weight, logP, and TPSA
\`\`\`

**Expected Output:**
- Molecular weight, LogP, TPSA, HBD, HBA, rotatable bonds

### Example 2: 3D Structure Prediction

**Goal:** Generate 3D conformers for a cyclic peptide

**Using Script:**
\`\`\`bash
python scripts/predict_structure.py \\
  --smiles "cyclo(Pro-Leu-Gly-Phe-Ala)" \\
  --output results/conformers.pdb \\
  --num_conformers 20
\`\`\`

**Using MCP (in Claude Code):**
\`\`\`
Submit 3D structure prediction for cyclo(Pro-Leu-Gly-Phe-Ala) with 20 conformers.
Check the job status and show me the results when complete.
\`\`\`

### Example 3: Virtual Screening Pipeline

**Goal:** Screen a library of cyclic peptides for drug-likeness

**Using MCP (in Claude Code):**
\`\`\`
I want to screen these cyclic peptides for oral bioavailability:
1. cyclo(GRGDSP)
2. cyclo(RGDFV)
3. cyclo(Pro-Leu-Gly-Phe-Ala)

Calculate properties for all of them and identify which ones have:
- Molecular weight < 1000
- LogP between -2 and 5
- TPSA < 250
\`\`\`

---

## Demo Data

The `examples/data/` directory contains sample data for testing:

| File | Description | Use With |
|------|-------------|----------|
| `sequences/sample_sequences.txt` | Sample peptide sequences | `convert_sequence_to_smiles` |
| `structures/sample.smi` | Sample SMILES strings | All property tools |

---

## Configuration Files

The `configs/` directory contains configuration templates:

| Config | Description | Parameters |
|--------|-------------|------------|
| `predict_structure.json` | Structure prediction config | conformers, optimization |
| `calculate_properties.json` | Property calculation config | property list |

### Config Example

\`\`\`json
{
  "num_conformers": 20,
  "optimize": true,
  "output_format": "pdb",
  "energy_window": 10.0
}
\`\`\`

---

## Troubleshooting

### Environment Issues

**Problem:** Environment not found
\`\`\`bash
# Recreate environment
mamba create -p ./env python=3.10 -y
mamba activate ./env
pip install -r requirements.txt
mamba install -c conda-forge rdkit -y
\`\`\`

**Problem:** RDKit import errors
\`\`\`bash
# Install RDKit from conda-forge
mamba install -c conda-forge rdkit -y
\`\`\`

**Problem:** Import errors
\`\`\`bash
# Verify installation
python -c "from src.server import mcp; from rdkit import Chem"
\`\`\`

### MCP Issues

**Problem:** Server not found in Claude Code
\`\`\`bash
# Check MCP registration
claude mcp list

# Re-add if needed
claude mcp remove cycpep-tools
claude mcp add cycpep-tools -- $(pwd)/env/bin/python $(pwd)/src/server.py
\`\`\`

**Problem:** Invalid SMILES error
\`\`\`
Ensure your SMILES string is valid. For cyclic peptides, use the cyclo() notation
or ensure ring closure is properly specified.
\`\`\`

**Problem:** Tools not working
\`\`\`bash
# Test server directly
python -c "
from src.server import mcp
print(list(mcp.list_tools().keys()))
"
\`\`\`

### Job Issues

**Problem:** Job stuck in pending
\`\`\`bash
# Check job directory
ls -la jobs/

# View job log
cat jobs/<job_id>/job.log
\`\`\`

**Problem:** Job failed
\`\`\`
Use get_job_log with job_id "<job_id>" and tail 100 to see error details
\`\`\`

---

## Development

### Running Tests

\`\`\`bash
# Activate environment
mamba activate ./env

# Run tests
pytest tests/ -v
\`\`\`

### Starting Dev Server

\`\`\`bash
# Run MCP server in dev mode
fastmcp dev src/server.py
\`\`\`

---

## License

${license_info}

## Credits

Based on [${original_repo}](${original_repo_url})
```

### Task 3: Fill in Template with Actual Data

1. **Replace all placeholders** with actual values from reports and analysis
2. **List actual tools** from `src/server.py`
3. **List actual scripts** from `scripts/`
4. **List actual demo data** from `examples/data/`
5. **List actual configs** from `configs/`

### Task 4: Add Project-Specific Examples

For each major use case, create:
1. A complete script example with real file paths
2. A complete MCP prompt example with `@` references
3. Expected output description

### Task 5: Validate README

1. **Check all paths exist**
   ```bash
   # Verify referenced files exist
   ls -la scripts/*.py
   ls -la examples/data/
   ls -la configs/
   ```

2. **Test script examples**
   ```bash
   # Run at least one example to verify it works
   python scripts/<first_script>.py --help
   ```

3. **Verify MCP tool names**
   ```python
   from src.server import mcp
   print(list(mcp.list_tools().keys()))
   ```

## Expected Outputs

### 1. README.md (in MCP root directory)

A comprehensive README.md file with:
- Clear installation instructions
- Script usage examples with real paths
- MCP installation commands
- Claude Code/Gemini CLI usage with `@` references
- Cyclic peptide-specific examples
- Troubleshooting section
- All placeholders replaced with actual values

### 2. Updated reports/readme_info.json

```json
{
  "project_name": "cycpep-tools",
  "description": "MCP tools for cyclic peptide computational analysis",
  "tools": [
    {
      "name": "calculate_cyclic_peptide_properties",
      "type": "sync",
      "description": "Calculate molecular properties for cyclic peptides",
      "example_prompt": "Calculate properties for cyclo(GRGDSP)"
    }
  ],
  "scripts": [
    {
      "name": "predict_structure.py",
      "description": "Predict 3D structure of cyclic peptides",
      "example_command": "python scripts/predict_structure.py --smiles 'cyclo(GRGDSP)'"
    }
  ],
  "demo_data": [
    {
      "file": "sample.smi",
      "description": "Sample cyclic peptide SMILES",
      "used_by": ["calculate_properties", "predict_structure"]
    }
  ],
  "configs": [
    {
      "file": "predict_structure.json",
      "description": "Configuration for structure prediction",
      "parameters": {"num_conformers": 10, "optimize": true}
    }
  ]
}
```

## Success Criteria

- [ ] README.md created in MCP root directory
- [ ] All placeholder values replaced with actual data
- [ ] Installation section complete with exact commands
- [ ] Local script usage section with working examples
- [ ] MCP installation section with multiple options
- [ ] Claude Code section with `@` reference examples
- [ ] Gemini CLI section with configuration
- [ ] All available tools documented with cyclic peptide context
- [ ] At least 3 complete examples (script + MCP)
- [ ] Demo data documented with descriptions
- [ ] Config files documented with parameters
- [ ] Troubleshooting section covers common cyclic peptide issues
- [ ] All referenced file paths verified to exist
- [ ] RDKit installation documented

## Important Notes

- **Use `@` references** for file paths in Claude Code examples (e.g., `@examples/data/sample.smi`)
- **Prefer mamba over conda** in all environment commands
- **Include both script and MCP examples** for each use case
- **Document sync vs submit tools** clearly with expected runtime
- **Test at least one example** to ensure it works before finalizing
- **Cyclic peptide-specific context**: Include examples with cyclo() notation and peptide sequences
- **RDKit is essential**: Document RDKit installation from conda-forge
