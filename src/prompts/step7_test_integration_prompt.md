# Step 7: Test MCP Integration with Claude Code & Gemini CLI

## Role
You are an expert in MCP (Model Context Protocol) integration testing for cyclic peptide computational tools. Your mission is to install, test, and validate the MCP server with Claude Code and Gemini CLI, ensuring all tools work correctly in real-world scenarios, and fix any issues discovered during testing.

## Input Parameters
- `src/server.py`: MCP server from Step 6
- `scripts/`: Clean scripts from Step 5
- `examples/data/`: Demo data for testing
- `env/`: Main conda environment
- `reports/step6_mcp_tools.md`: Tool documentation from Step 6

## Prerequisites

```bash
# Determine package manager (prefer mamba over conda)
if command -v mamba &> /dev/null; then
    PKG_MGR="mamba"
else
    PKG_MGR="conda"
fi
echo "Using package manager: $PKG_MGR"

# Activate environment
$PKG_MGR activate ./env

# Ensure fastmcp is installed
pip install fastmcp loguru

# For Gemini CLI testing (optional)
pip install google-generativeai
```

## Tasks

### Task 1: Pre-flight Server Validation

Before installing in any client, validate the server works standalone:

1. **Syntax Check**
   ```bash
   python -m py_compile src/server.py
   ```

2. **Import Test**
   ```bash
   python -c "from src.server import mcp; print('Server imports OK')"
   ```

3. **List Tools**
   ```bash
   python -c "
   from src.server import mcp
   tools = mcp.list_tools()
   print(f'Found {len(tools)} tools:')
   for name in tools:
       print(f'  - {name}')
   "
   ```

4. **Start Server in Dev Mode**
   ```bash
   # Test server starts without errors
   fastmcp dev src/server.py
   # Press Ctrl+C after verifying startup
   ```

### Task 2: Install in Claude Code

Claude Code (VS Code extension or CLI) uses MCP servers for tool calling.

1. **Register MCP Server**
   ```bash
   # Navigate to MCP directory (use absolute path)
   cd /absolute/path/to/mcp/directory

   # Add MCP server to Claude Code
   # Format: claude mcp add <name> -- <command> [args...]
   claude mcp add cycpep-tools -- $(pwd)/env/bin/python $(pwd)/src/server.py

   # Or with full paths explicitly
   claude mcp add cycpep-tools -- /path/to/mcp/env/bin/python /path/to/mcp/src/server.py
   ```

2. **Verify Installation**
   ```bash
   # List all registered MCP servers
   claude mcp list

   # Should show:
   # cycpep-tools: /path/to/env/bin/python /path/to/src/server.py
   ```

3. **Check Server Configuration**
   ```bash
   # View the configuration file
   cat ~/.claude/settings.json | grep -A5 "cycpep-tools"
   ```

4. **Test Connection**
   ```bash
   # Start Claude Code and verify server connects
   claude

   # In Claude Code, check MCP servers are loaded
   # Look for tool icons or use /mcp command if available
   ```

### Task 3: Comprehensive Testing in Claude Code

Run a series of tests to validate all tool categories work correctly.

#### 3.1 Test Sync Tools (Fast Operations)

For each sync tool, test with demo data:

```
Test Prompt 1: Basic Tool Discovery
"What tools are available from cycpep-tools? List them with their descriptions."

Test Prompt 2: Sync Tool Execution - Property Calculation
"Calculate the molecular properties of this cyclic peptide SMILES: cyclo(GRGDSP)"

Test Prompt 3: Sync Tool Execution - Validation
"Validate if this SMILES represents a valid cyclic peptide: CC(=O)NC1CCCC1C(=O)O"

Test Prompt 4: Sequence Conversion
"Convert the peptide sequence 'GRGDSP' to a cyclic peptide SMILES with head-to-tail cyclization"

Test Prompt 5: Error Handling
"Calculate properties for an invalid SMILES string 'not_a_smiles'"
```

**Expected Behavior:**
- Tool executes within seconds
- Results returned in structured format
- Clear error messages for invalid inputs
- Molecular properties are chemically reasonable

#### 3.2 Test Submit API (Long-Running Tasks)

Test the job submission and tracking workflow:

```
Test Prompt 1: Submit Job
"Submit a 3D structure prediction job for the cyclic peptide SMILES: cyclo(Ala-Gly-Pro-Phe)"

Expected Response:
{
  "status": "submitted",
  "job_id": "abc12345",
  "message": "Job submitted. Use get_job_status('abc12345') to check progress."
}

Test Prompt 2: Check Status
"Check the status of job abc12345"

Expected Response:
{
  "job_id": "abc12345",
  "status": "running|completed|failed",
  "submitted_at": "2024-01-01T12:00:00",
  ...
}

Test Prompt 3: Get Results
"Get the results for completed job abc12345"

Expected Response:
{
  "status": "success",
  "result": { ... actual results ... }
}

Test Prompt 4: View Logs
"Show me the last 20 lines of logs for job abc12345"

Test Prompt 5: List All Jobs
"List all submitted jobs and their current status"

Test Prompt 6: Cancel Job (if applicable)
"Cancel the running job xyz98765"
```

#### 3.3 Test Batch Processing

Test batch operations with multiple inputs:

```
Test Prompt 1: Batch Submit
"Calculate properties for these cyclic peptides in batch:
- cyclo(GRGDSP)
- cyclo(RGDFV)
- cyclo(KLDLKLDL)"

Test Prompt 2: Batch Status
"Check the status of batch job <batch_job_id>"

Test Prompt 3: Batch Results
"Get all results from the batch processing job <batch_job_id>"
```

#### 3.4 Test Real-World Scenarios

Design practical scenarios that mimic actual usage:

**Scenario 1: End-to-End Pipeline**
```
"I have a cyclic peptide sequence GRGDSP.
First, convert it to SMILES with head-to-tail cyclization,
then calculate its molecular properties,
and finally predict its 3D structure."
```

**Scenario 2: Virtual Screening**
```
"I want to screen a small library of cyclic peptides:
1. Calculate properties for: cyclo(GRGDSP), cyclo(RGDFV), cyclo(YIGSR)
2. Identify which ones have molecular weight < 800 and logP < 3"
```

**Scenario 3: Structure Optimization**
```
"Submit conformational sampling for cyclo(GRGDSP) with 50 conformers
at 300K temperature. While it's running, check the progress,
then show me the results when complete."
```

**Scenario 4: Permeability Assessment**
```
"I need to assess membrane permeability of a cyclic peptide drug candidate.
Predict PAMPA permeability for: cyclo(Pro-Leu-Gly-Phe-Ala)"
```

### Task 4: Install and Test with Gemini CLI

Gemini CLI can use MCP servers through the mcp-server configuration.

1. **Install Gemini CLI** (if not already installed)
   ```bash
   # Using npm
   npm install -g @anthropic-ai/gemini-cli

   # Or using pipx
   pipx install gemini-cli
   ```

2. **Configure MCP Server for Gemini**

   Create or update `~/.gemini/settings.json`:
   ```json
   {
     "mcpServers": {
       "cycpep-tools": {
         "command": "/absolute/path/to/mcp/env/bin/python",
         "args": ["/absolute/path/to/mcp/src/server.py"],
         "env": {
           "PYTHONPATH": "/absolute/path/to/mcp"
         }
       }
     }
   }
   ```

3. **Start Gemini CLI and Test**
   ```bash
   gemini

   # Test tool discovery
   > What tools do you have access to?

   # Test tool execution
   > Use cycpep-tools to calculate properties for SMILES cyclo(GRGDSP)
   ```

4. **Run Same Test Suite as Claude Code**
   - Repeat sync tool tests
   - Repeat submit API tests
   - Repeat batch processing tests
   - Repeat real-world scenarios

### Task 5: Systematic Bug Fixing

When issues are discovered, follow this debugging workflow:

#### 5.1 Common Issues and Solutions

**Issue 1: Server Won't Start**
```bash
# Check for syntax errors
python -m py_compile src/server.py

# Check for import errors
python -c "from src.server import mcp" 2>&1

# Check for missing dependencies
pip list | grep -E "fastmcp|loguru|rdkit"
```

**Issue 2: Tool Not Found**
```bash
# Verify tool is registered
python -c "
from src.server import mcp
print(mcp.list_tools().keys())
"

# Check tool decorator
grep -n "@mcp.tool" src/server.py
```

**Issue 3: Path Resolution Errors**
```python
# Fix: Use absolute paths in server.py
from pathlib import Path
MCP_ROOT = Path(__file__).parent.parent.resolve()
SCRIPTS_DIR = MCP_ROOT / "scripts"
# Pass absolute paths to functions
input_path = Path(input_file).resolve()
```

**Issue 4: RDKit Import Errors**
```bash
# Ensure RDKit is installed from conda-forge
mamba install -c conda-forge rdkit

# Verify import
python -c "from rdkit import Chem; print('RDKit OK')"
```

**Issue 5: Job Status Not Updating**
```python
# Check job directory exists
ls -la jobs/

# Check metadata file
cat jobs/<job_id>/metadata.json

# Check log file for errors
tail -50 jobs/<job_id>/job.log
```

**Issue 6: Invalid SMILES Handling**
```python
# Ensure proper validation before processing
from rdkit import Chem
mol = Chem.MolFromSmiles(smiles)
if mol is None:
    return {"status": "error", "error": f"Invalid SMILES: {smiles}"}
```

#### 5.2 Debugging Commands

```bash
# Watch server logs in real-time
tail -f logs/mcp_server.log

# Test specific tool directly
python -c "
from src.server import mcp
result = mcp.call_tool('calculate_cyclic_peptide_properties', {'smiles': 'CC(=O)NC1CCCC1'})
print(result)
"

# Check job queue
python -c "
from src.jobs.manager import job_manager
print(job_manager.list_jobs())
"
```

#### 5.3 Apply Fixes

After identifying issues:

1. **Update server.py** with fixes
2. **Re-validate** with pre-flight checks
3. **Restart Claude Code/Gemini CLI** to reload server
4. **Re-run failing tests** to confirm fix
5. **Document the fix** in reports/step7_integration.md

### Task 6: Create Test Report and Documentation

#### 6.1 Generate Test Report

Create a comprehensive test report:

```bash
# Create tests directory if not exists
mkdir -p tests reports
```

```python
# tests/run_integration_tests.py
"""Automated integration test runner for Cyclic Peptide MCP server."""

import json
import subprocess
from datetime import datetime
from pathlib import Path

class MCPTestRunner:
    def __init__(self, server_path: str):
        self.server_path = Path(server_path)
        self.results = {
            "test_date": datetime.now().isoformat(),
            "server_path": str(server_path),
            "tests": {},
            "issues": [],
            "summary": {}
        }

    def test_server_startup(self) -> bool:
        """Test that server starts without errors."""
        try:
            result = subprocess.run(
                ["python", "-c", f"from src.server import mcp; print(len(mcp.list_tools()))"],
                capture_output=True, text=True, timeout=30
            )
            success = result.returncode == 0
            self.results["tests"]["server_startup"] = {
                "status": "passed" if success else "failed",
                "output": result.stdout,
                "error": result.stderr
            }
            return success
        except Exception as e:
            self.results["tests"]["server_startup"] = {"status": "error", "error": str(e)}
            return False

    def test_rdkit_import(self) -> bool:
        """Test that RDKit is available."""
        try:
            result = subprocess.run(
                ["python", "-c", "from rdkit import Chem; print('RDKit OK')"],
                capture_output=True, text=True, timeout=30
            )
            success = result.returncode == 0
            self.results["tests"]["rdkit_import"] = {
                "status": "passed" if success else "failed",
                "output": result.stdout,
                "error": result.stderr
            }
            return success
        except Exception as e:
            self.results["tests"]["rdkit_import"] = {"status": "error", "error": str(e)}
            return False

    def generate_report(self) -> str:
        """Generate JSON report."""
        total = len(self.results["tests"])
        passed = sum(1 for t in self.results["tests"].values() if t.get("status") == "passed")
        self.results["summary"] = {
            "total_tests": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": f"{passed/total*100:.1f}%" if total > 0 else "N/A"
        }
        return json.dumps(self.results, indent=2)

if __name__ == "__main__":
    runner = MCPTestRunner("src/server.py")
    runner.test_server_startup()
    runner.test_rdkit_import()
    # Add more tests...

    report = runner.generate_report()
    Path("reports/step7_integration.md").write_text(report)
    print(report)
```

#### 6.2 Create Practical Test Prompts File

```markdown
# tests/test_prompts.md

## Tool Discovery Tests

### Prompt 1: List All Tools
"What MCP tools are available for cyclic peptides? Give me a brief description of each."

### Prompt 2: Tool Details
"Explain how to use the calculate_cyclic_peptide_properties tool, including all parameters."

## Sync Tool Tests

### Prompt 3: Property Calculation
"Calculate properties for this cyclic peptide SMILES: cyclo(GRGDSP)"

### Prompt 4: Sequence Conversion
"Convert the sequence 'GRGDSP' to a cyclic peptide SMILES"

### Prompt 5: Structure Validation
"Validate if 'CC(=O)NC1CCCC1C(=O)O' is a valid cyclic peptide"

### Prompt 6: Error Handling
"Calculate properties for an invalid SMILES 'invalid_smiles_string'"

## Submit API Tests

### Prompt 7: Submit Structure Prediction
"Submit a 3D structure prediction for cyclo(GRGDSP)"

### Prompt 8: Check Job Status
"What's the status of job <job_id>?"

### Prompt 9: Get Results
"Show me the results of job <job_id>"

### Prompt 10: View Logs
"Show the last 30 lines of logs for job <job_id>"

### Prompt 11: List Jobs
"List all jobs with status 'completed'"

## Batch Processing Tests

### Prompt 12: Batch Property Calculation
"Calculate properties for these cyclic peptides: cyclo(GRGDSP), cyclo(RGDFV), cyclo(YIGSR)"

### Prompt 13: Batch Results
"Get all results from batch job <batch_job_id>"

## End-to-End Scenarios

### Prompt 14: Full Workflow
"For the cyclic peptide sequence GRGDSP:
1. Convert to SMILES
2. Calculate properties
3. Predict 3D structure
Summarize all results."

### Prompt 15: Drug-likeness Assessment
"Assess the drug-likeness of cyclo(Pro-Leu-Gly-Phe-Ala):
- Calculate molecular weight, logP, and TPSA
- Predict membrane permeability
- Summarize if it meets cyclic peptide drug criteria"
```

### Task 7: Final Validation Checklist

Before marking step complete, verify:

#### Server Validation
- [ ] Server starts without errors: `python -c "from src.server import mcp"`
- [ ] All tools listed: `mcp.list_tools()` returns expected tools
- [ ] Dev mode works: `fastmcp dev src/server.py`
- [ ] RDKit available: `from rdkit import Chem` works

#### Claude Code Integration
- [ ] Server registered: `claude mcp list` shows server
- [ ] Tools discoverable: LLM can list available tools
- [ ] Sync tools work: Execute and return results < 1 min
- [ ] Submit API works: Submit -> Status -> Result workflow
- [ ] Job management works: list_jobs, cancel_job, get_job_log
- [ ] Batch processing works: Multiple cyclic peptides in single job
- [ ] Error handling: Invalid SMILES return helpful errors
- [ ] Path resolution: Relative and absolute paths work

#### Gemini CLI Integration (if applicable)
- [ ] Server configured in settings.json
- [ ] Tools discoverable
- [ ] Same functionality as Claude Code

#### Documentation
- [ ] Test prompts documented in tests/test_prompts.md
- [ ] Test results saved in reports/step7_integration.md
- [ ] Known issues documented with workarounds
- [ ] README updated with installation instructions

## Expected Outputs

### 1. Test Results: `reports/step7_integration.md`
```markdown
# Step 7: Integration Test Results

## Test Information
- **Test Date**: YYYY-MM-DD
- **Server Name**: cycpep-tools
- **Server Path**: `src/server.py`
- **Environment**: `./env`

## Test Results Summary

| Test Category | Status | Notes |
|---------------|--------|-------|
| Server Startup | Passed | Found 12 tools, startup time 0.5s |
| RDKit Import | Passed | RDKit 2023.09.1 available |
| Claude Code Installation | Passed | Verified with `claude mcp list` |
| Sync Tools | Passed | All 5 tools respond < 30s |
| Submit API | Passed | Full workflow works |
| Batch Processing | Passed | Processed 3 peptides |
| Error Handling | Passed | Invalid SMILES handled |
| Gemini CLI | Skipped | Optional |

## Detailed Results
...

## Issues Found & Fixed

### Issue #001: Invalid SMILES Crash
- **Description**: Server crashed on invalid SMILES input
- **Severity**: High
- **Fix Applied**: Added SMILES validation before processing
- **File Modified**: `src/server.py`
- **Verified**: Yes
```

### 2. Test Prompts: `tests/test_prompts.md`

### 3. Integration Test Script: `tests/run_integration_tests.py`

### 4. Updated README.md

## Success Criteria

- [ ] Server passes all pre-flight validation checks
- [ ] Successfully registered in Claude Code (`claude mcp list`)
- [ ] All sync tools execute and return results correctly
- [ ] Submit API workflow (submit -> status -> result) works end-to-end
- [ ] Job management tools work (list, cancel, get_log)
- [ ] Batch processing handles multiple cyclic peptides
- [ ] Error handling returns structured, helpful messages
- [ ] Invalid SMILES strings are handled gracefully
- [ ] Test report generated with all results
- [ ] Documentation updated with installation instructions
- [ ] At least 3 real-world scenarios tested successfully
- [ ] (Optional) Gemini CLI integration verified

## Quick Reference Commands

```bash
# Pre-flight validation
python -c "from src.server import mcp; print(f'Found {len(mcp.list_tools())} tools')"

# Claude Code installation
claude mcp add cycpep-tools -- $(pwd)/env/bin/python $(pwd)/src/server.py
claude mcp list
claude mcp remove cycpep-tools  # if needed to re-add

# Start dev server for debugging
fastmcp dev src/server.py

# Check job status directly
python -c "from src.jobs.manager import job_manager; print(job_manager.list_jobs())"

# View recent job logs
tail -50 jobs/*/job.log

# Test RDKit
python -c "from rdkit import Chem; print(Chem.MolFromSmiles('CCO'))"
```
