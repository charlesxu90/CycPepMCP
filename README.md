# CycPepMCP

Cyclic Peptide Engineering Model Context Protocol Package

A comprehensive toolkit for cyclic peptide engineering, non-natural amino acid incorporation, peptide design, and analysis using the Model Context Protocol (MCP) for Claude Code.

## Features

- **Cyclic Peptide Design**: Design cyclic peptides with various cyclization strategies
  - Head-to-tail backbone cyclization
  - Disulfide bridge formation
  - Side-chain lactam bridges
  - Thioether linkages

- **Non-Natural Amino Acids**: Incorporate non-canonical amino acids
  - D-amino acids for proteolytic stability
  - N-methylated amino acids for permeability
  - Alpha-methylated amino acids for conformational constraint
  - Beta-amino acids for backbone modification

- **Property Prediction**: Predict key physicochemical properties
  - Molecular weight and charge
  - Solubility and membrane permeability
  - Proteolytic stability
  - Conformational flexibility

- **Workflow Skills**: Pre-built workflows for common tasks
  - Cyclic peptide design workflow
  - NNAA incorporation workflow
  - Permeability optimization workflow

## Installation

### Prerequisites

- Python 3.10+
- Claude Code CLI installed and configured

### Install CycPepMCP

```bash
# Clone the repository
git clone https://github.com/macronex/CycPepMCP.git
cd CycPepMCP

mamba env create -f environment.yml -y
mamba activate cycpepmcp
pip install -r requirements.txt
# Install in development mode
pip install -e .
```

## Quick Start

### List Available MCPs

```bash
cpmcp avail
```

### Install an MCP

```bash
cpmcp install cycpep_design_mcp
```

### Check MCP Status

```bash
cpmcp status
```

### List Available Skills

```bash
cpskill avail
```

### Install a Skill

```bash
cpskill install cycpep_design
```

## CLI Commands

### cpmcp - MCP Management

```bash
# Show all available MCPs
cpmcp avail

# Show MCP status
cpmcp status

# Install MCP(s)
cpmcp install <mcp_name>
cpmcp install mcp1 mcp2 mcp3

# Uninstall MCP
cpmcp uninstall <mcp_name>

# Search MCPs
cpmcp search <query>

# Show MCP info
cpmcp info <mcp_name>
```

### cpskill - Skill Management

```bash
# Show available skills
cpskill avail

# Show skill status
cpskill status

# Install skill and its MCPs
cpskill install <skill_name>

# Execute skill (guided workflow)
cpskill execute <skill_name>

# Uninstall skill
cpskill uninstall <skill_name>

# Create new skill
cpskill create init <skill_name>
cpskill create add-step <skill_name>
cpskill create generate <skill_name>
```

## Tool MCPs

### cycpep_design_mcp
Design cyclic peptides with various cyclization strategies.

**Tools:**
- `design_cyclic_peptide` - Design a cyclic peptide from linear sequence
- `analyze_cyclization_sites` - Analyze potential cyclization sites
- `generate_cyclic_variants` - Generate variant sequences
- `predict_cyclic_peptide_properties` - Predict physicochemical properties
- `list_example_sequences` - List example sequences

### nnaa_mcp
Incorporate non-natural amino acids into peptides.

**Tools:**
- `analyze_nnaa_sites` - Find optimal positions for NNAA
- `select_nnaa` - Choose appropriate modifications
- `generate_modified_sequence` - Create NNAA-containing sequences
- `predict_modification_effects` - Predict property changes

### peptide_permeability_mcp
Predict and optimize cell membrane permeability.

### peptide_stability_mcp
Predict proteolytic stability and half-life.

## Workflow Skills

### cycpep_design
Complete workflow for designing cyclic peptides.

```bash
cpskill install cycpep_design
cpskill execute cycpep_design
```

### nnaa_incorporation
Workflow for incorporating non-natural amino acids.

```bash
cpskill install nnaa_incorporation
cpskill execute nnaa_incorporation
```

## Creating New Skills

1. Initialize a new skill:
```bash
cpskill create init my_skill -d "Description" -m mcp1 -m mcp2
```

2. Add steps interactively:
```bash
cpskill create add-step my_skill
```

3. Generate the skill file:
```bash
cpskill create generate my_skill
```

4. Install the skill:
```bash
cpskill install my_skill
```

## Creating New MCPs

1. Create a new directory in `tool-mcps/`:
```bash
mkdir -p tool-mcps/my_mcp/src
```

2. Create `server.py` using FastMCP:
```python
from fastmcp import FastMCP

mcp = FastMCP("my-mcp")

@mcp.tool()
def my_tool(param: str) -> dict:
    """Tool description."""
    return {"result": param}

if __name__ == "__main__":
    mcp.run()
```

3. Add to `src/mcp/configs/mcps.yaml`

4. Install and register:
```bash
cpmcp install my_mcp
```

## Directory Structure

```
CycPepMCP/
├── src/
│   ├── __init__.py
│   ├── mcp_cli.py              # cpmcp command
│   ├── skill_cli.py            # cpskill command
│   ├── mcp/
│   │   ├── mcp.py              # MCP class
│   │   ├── mcp_manager.py      # MCP management
│   │   ├── install_mcp.py      # Installation functions
│   │   ├── status_cache.py     # Status caching
│   │   └── configs/
│   │       ├── mcps.yaml       # Local MCP configs
│   │       └── public_mcps.yaml
│   └── skill/
│       ├── skill.py            # Skill class
│       ├── skill_manager.py    # Skill management
│       ├── create_skill.py     # Skill creation
│       └── configs.yaml        # Skill configs
├── tool-mcps/                   # MCP server implementations
│   ├── cycpep_design_mcp/
│   ├── nnaa_mcp/
│   └── public/
├── workflow-skills/             # Workflow skill definitions
│   ├── cycpep_design.md
│   └── nnaa_incorporation.md
├── examples/                    # Example data and usage
├── setup.py
├── requirements.txt
└── README.md
```

## Contributing

Contributions are welcome! Please feel free to submit pull requests.

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

MIT License - see LICENSE file for details.

## References

- Craik, D.J. et al. (2013). The Future of Peptide-based Drugs. Chem. Biol. Drug Des.
- White, C.J. & Yudin, A.K. (2011). Contemporary strategies for peptide macrocyclization. Nat. Chem.
- Driggers, E.M. et al. (2008). The exploration of macrocycles for drug discovery. Nat. Rev. Drug Discov.
- Blaskovich, M.A. (2016). Unusual amino acids in medicinal chemistry. J. Med. Chem.

## Acknowledgments

Built following the architecture of [ProteinMCP](https://github.com/macronex/ProteinMCP) for protein engineering.
