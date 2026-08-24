# Supplementary Information of CycPepMCP

---

## Supplementary Note 1: MCP registry and installation specification

The centralized MCP registry is a YAML document that declares, for each MCP, its path, runtime, Python version, server command and arguments, setup-script path, Docker arguments, cache-data and cache-model subpaths, environment variables, and dependencies. The command `cpmcp install` executes the MCP-specific setup script, creates declared cache directories, and registers the server in Claude Code. This note specifies the registry schema, the object model derived from it, the runtime-detection logic that dispatches installation across Docker, UV, and Conda backends, and the registration and status machinery. All identifiers refer to the reference implementation in `src/cycpep_mcp/`.

### N1.1 Registry organisation

Server descriptions are held in two YAML documents rather than in code, so that adding a tool requires no modification of the CLI or the orchestration layer:

| Registry | Path | Entries | Contents |
|---|---|---|---|
| In-house | `src/cycpep_mcp/configs/mcps.yaml` | 28 | Scientific-software servers developed in this work |
| Public | `src/cycpep_mcp/configs/public_mcps.yaml` | 10 | Third-party database and utility servers |

Each file contains a single top-level `mcps:` mapping keyed by server name; each value is a flat mapping of the fields in Table S4. The registry is the single source of truth consumed by `cpmcp` for every operation — listing, searching, installation, registration, cache provisioning, and status reporting. Entries are loaded lazily with an in-process memo (`MCPManager.load_public_mcps`, `load_installed_mcps`) that a `force_reload` flag bypasses. `MCPManager.get_mcp` resolves a name against the in-house registry first and falls back to the public one, so an in-house server shadows a public entry of the same name.

The registries are kept in step with the filesystem by two operations. `cpmcp sync` reconciles registered entries against the contents of `tool-mcps/`, and `MCPManager.discover_tool_mcps` inspects directories present on disk but absent from the registry, inferring `runtime`, `server_command`, and `server_args` from their layout (`_detect_mcp_config`); `discover_and_add_tool_mcps` writes the inferred entries back.

Relative `path` values are resolved against the project root at load time (`resolve_path`), so a registry checked into version control remains portable across installations; absolute paths are honoured unchanged. Serialisation is symmetric (`MCP.to_dict` / `MCP.from_dict`), so entries edited programmatically round-trip without loss.

### N1.2 Registry schema and data model

Each entry is deserialised into an `MCP` dataclass instance with the 18 fields of Table S4. The dataclass carries both the declarative description and the full lifecycle as methods (`install`, `uninstall`, `register`, `unregister`, `get_status`), so a server is manipulated as a single object regardless of its runtime.

**Table S4.** Fields of the `MCP` data model and their occupancy across the 28 in-house entries.

| Field | Type | Default | Present in | Purpose |
|---|---|---|---|---|
| `name` | str | — | 28/28 | Registry key and CLI identifier |
| `url` | str | `""` | 28/28 | Upstream repository |
| `description` | str | `""` | 28/28 | One-line summary shown by `cpmcp avail` / `search` |
| `source` | str | `"Community"` | 28/28 | Provenance tag (`Tool`, `Community`, …) |
| `runtime` | str | `"python"` | 28/28 | Dispatch key; see N1.3 |
| `python_version` | str | `"3.10"` | 28/28 | Interpreter version for environment creation |
| `setup_commands` | list[str] | `[]` | 28/28 | Legacy inline setup steps; fallback for `setup_script` |
| `setup_script` | str | `""` | 28/28 | Setup entry point (`quick_setup.sh` throughout) |
| `server_command` | str | `""` | 28/28 | Executable that starts the server |
| `server_args` | list[str] | `[]` | 28/28 | Arguments, typically `src/server.py` |
| `env_vars` | dict | `{}` | 28/28 | Environment injected at registration |
| `dependencies` | list[str] | `[]` | 28/28 | System-level prerequisites |
| `path` | str \| None | `None` | 28/28 | Install location, relative to project root |
| `docker_image` | str \| None | `None` | 16/28 | Image reference, `ghcr.io/MacromNex/<name>:latest` |
| `docker_args` | list[str] | `[]` | 28/28 | Extra `docker run` flags (e.g. `--gpus all`, `--ipc=host`) |
| `docker_volumes` | list[str] | `[]` | 28/28 | Additional bind mounts |
| `cache_data` | dict | `{}` | 3/28 | `{subpath, mount}` under the shared data cache (Note 2) |
| `cache_model` | dict | `{}` | 6/28 | `{subpath, mount}` under the shared model cache (Note 2) |

Three enumerations constrain the model: `MCPRuntime` (seven dispatch backends, N1.3), `MCPStatus` (`not_installed`, `installed`, `registered`, `both`; N1.6), and `MCPScope` (`project`, `global`).

### N1.3 Runtime detection and dispatch

The `runtime` field selects one of seven dispatch paths. It is declared explicitly in the registry rather than probed at run time, so the same entry resolves identically on every host; `cpmcp create` infers it once at creation time (Note 4), and `_detect_mcp_config` infers it for directories discovered outside the registry.

**Table S5.** Runtime distribution across the two registries and the corresponding installation action.

| Runtime | In-house (n=28) | Public (n=10) | Installation action | Isolation |
|---|---|---|---|---|
| `docker` | 16 | 0 | Resolve local image, else pull from GHCR | Container |
| `uv` | 7 | 0 | `uv venv` + `uv pip install -r requirements.txt` | Project venv |
| `python` | 5 | 4 | Execute `quick_setup.sh` (Conda/Mamba environment) | Named env |
| `node` | 0 | 6 | Package-manager install | Node modules |
| `uvx` / `npx` / `binary` | 0 | 0 | None; resolved at launch | — |

The assignment follows the dependency profile of the wrapped software. GPU-bound tools with deep or conflicting native dependencies (AlphaFold3, RFdiffusion, Boltz, Rosetta, Gnina) are containerised, which pins CUDA and system-library versions and makes the server reproducible across hosts. Lightweight CPU tools with pure-Python dependency trees use UV, whose resolver and virtual-environment construction are roughly an order of magnitude faster than Conda. Tools requiring Conda-only channels — compiled chemistry stacks such as AutoDock CrankPep, RDKit-linked builds, and Rosetta's Python bindings — retain a Conda environment created by their `quick_setup.sh`.

### N1.4 Installation

`cpmcp install <name>` is idempotent. `install()` invalidates the cached status on entry, returns early when the server is already present unless `force=True`, and dispatches on `runtime`:

1. **Package runtimes** (`uvx`, `npx`) require no action; the package is resolved by the launcher at registration time.
2. **Docker.** `_pull_docker_image` resolves the image, preferring a locally built tag (`<name>:latest`) over the published GHCR reference, so a developer build shadows the release image without a registry edit. On success, cache directories are provisioned (Note 2).
3. **UV.** `_install_uv` verifies the `uv` binary is on `PATH`, creates `env/` inside the server directory at the declared `python_version` (120 s timeout), then installs `requirements.txt` if present. Cache directories are provisioned on success.
4. **Conda and other interpreter runtimes.** `_run_setup` executes the declared `setup_script` — `quick_setup.sh` for every in-house server — from the server directory with a 1800 s timeout, streaming output so long compilations remain observable. `--skip-env` and `--skip-repo` flags are forwarded from `install(skip_env=…, skip_repo=…)` to allow partial re-runs. If the script fails or is absent, `_run_setup_commands` replays the legacy `setup_commands` list as a fallback.

Delegating environment construction to a per-server `quick_setup.sh` rather than to the CLI is deliberate. Each script encodes the idiosyncratic steps of its wrapped package — submodule checkout, weight download, compilation flags, licence acceptance — while presenting one uniform contract to the installer: a bash script taking two optional flags and returning a POSIX exit status. This is what allows 28 heterogeneous scientific packages to be installed through a single command without special cases in the CLI.

`cpmcp uninstall <name>` unregisters the server from the agent CLI and, with `--remove-files`, deletes the installation directory.

### N1.5 Registration with the agent CLI

Registration translates an `MCP` object into an `mcp add` invocation of the target agent CLI (`claude` or `gemini`). `register()` verifies the CLI is on `PATH`, prompts before replacing an existing registration, and dispatches to a per-runtime builder (Table S6). Server names are sanitised by replacing `/` and `-` with `_` (`_get_clean_name`), since the CLI treats those characters as delimiters. Declared `env_vars` are emitted as `--env K=V` pairs in every form.

**Table S6.** Generated registration command per runtime. `<clean>` is the sanitised server name.

| Runtime | Generated command (after `<cli> mcp add <clean> [--env …] --`) |
|---|---|
| `docker` | `docker run -i --rm --user <uid>:<gid> <docker_args> -v <cwd>:<cwd> [-v <volumes>] [-v <cache mounts>] <image>` |
| `python` | `<env python> <resolved server_args \| discovered entry point>` |
| `uv` | `<env/bin/python> <resolved server_args \| discovered entry point>` |
| `node` | `<server_command \| node> <resolved server_args>` |
| `uvx` | `uvx <server_args>` |
| `npx` | `npx <server_args>` |

Two properties of the containerised form matter for multi-server workflows. Running under the invoking user's UID and GID keeps job artefacts writable on the host rather than root-owned. Bind-mounting the current working directory at the same absolute path inside the container means a host path remains valid inside the container unchanged — the property that lets an agent hand a PDB file produced by one server directly to another without staging or path rewriting.

For interpreter-based servers, `_find_python_env` prefers a co-located environment (`env/bin/python`, `.venv/bin/python`, `venv/bin/python`) and falls back to `python` on `PATH`; `_find_server_entry` probes conventional locations (`src/server.py`, `server.py`, `src/index.py`, `index.py`, `main.py`, `src/main.py`) before a recursive glob. Argument templates support a `$MCP_PATH` placeholder, and any relative argument that looks like a path is resolved against the server directory. The `scope` argument of `register()` is accepted but currently unused; registrations are written to the CLI's default user-level configuration.

### N1.6 Status determination and caching

A server's state is the conjunction of two independent probes. `is_installed()` checks a runtime-specific artefact: image presence for Docker (local tag first, then the GHCR reference), `env/bin/python` for UV, directory existence for path-bearing entries, and unconditional truth for package runtimes. `is_registered(cli)` shells out to `<cli> mcp list` and tests for the sanitised name. The pair maps onto `MCPStatus`: `not_installed`, `installed`, `registered`, or `both`.

Because the registration check spawns a subprocess per server, evaluating 38 entries interactively is prohibitive. A shared status cache (`tool-mcps/mcp.status`) stores a timestamped name-to-state mapping with a 300 s time-to-live. Every read and write acquires an exclusive `fcntl.flock` on the cache file, so concurrent `cpmcp` invocations cannot interleave partial writes. Mutating operations invalidate the affected entry explicitly rather than waiting for expiry, and `cpmcp status --refresh` forces a full re-probe.

### N1.7 Command-line surface

| Command | Effect |
|---|---|
| `cpmcp avail [--local\|--public]` | List registry entries |
| `cpmcp search <query>` | Case-insensitive substring match over name, description, and source |
| `cpmcp info <name>` | Resolved runtime, path, image, cache declarations |
| `cpmcp install <name> [--no-register] [--cli gemini]` | Install (N1.4) and register (N1.5) |
| `cpmcp uninstall <name> [--remove-files]` | Unregister and optionally delete files |
| `cpmcp status [--refresh]` | Installed/registered state for all entries (N1.6) |
| `cpmcp cache` | Cache root, environment-variable state, per-server subpaths (Note 2) |
| `cpmcp sync` | Reconcile registry with `tool-mcps/` |
| `cpmcp create -g <url> -d tool-mcps/<name>` | Add a new server to the registry (Note 4) |

---

## Supplementary Note 2: Centralized data and model management

CycPepMCP employs a centralized caching mechanism to manage model weights and reference datasets across all tools. This design eliminates redundant downloads and ensures consistent access to shared resources such as AlphaFold, Boltz, and HELM-GPT models. The cache is organized into separate namespaces for model parameters and reference data and is accessible across both containerized and local runtimes. By standardizing data access through a unified configuration, the system improves reproducibility while reducing initialization overhead for large-scale workflows.

### N2.1 Cache root and layout

A single cache root, controlled by the `MACROMNEX_CACHE` environment variable with a default of `~/.macromnex/cache`, holds all shared model weights and reference databases. The root is resolved at run time (`get_cache_root`) and partitioned into two namespaces, addressed by `get_cache_data_dir` and `get_cache_model_dir`:

```
$MACROMNEX_CACHE/
├── data/     # reference databases, sequence and structure corpora
│   ├── af3_db/
│   └── helmgpt_data/
└── model/    # trained network weights
    ├── alphafold2/params/
    ├── alphafold3/model/
    ├── boltz/
    ├── helmgpt/
    └── rfpeptides/models/
```

Separating weights from databases is not merely organisational: it lets the two classes be placed on different filesystems — weights on fast local storage, multi-terabyte sequence databases on a shared network volume — by symlinking a single subtree, without touching any server configuration.

### N2.2 Per-server declarations

A server declares its requirements as two optional nested mappings, each carrying a `subpath` relative to `data/` or `model/` and a `mount` giving the absolute path at which the directory is exposed inside the container:

```yaml
alphafold3_mcp:
  cache_data:
    subpath: af3_db
    mount: /app/repo/alphafold3/alphafold3_db
  cache_model:
    subpath: alphafold3/model
    mount: /app/repo/alphafold3/model
```

The declaration is deliberately two-sided. The `subpath` is a property of the *asset* and is shared between every server that consumes it; the `mount` is a property of the *server* and reflects wherever its wrapped software expects to find the files. Decoupling the two lets servers with incompatible internal layouts share one physical copy.

**Table S7.** Registry cache declarations. Suffix `:ro` denotes a read-only mount.

| MCP server | `cache_model` subpath → mount | `cache_data` subpath → mount |
|---|---|---|
| `afcycdesign_mcp` | `alphafold2/params` → `/app/params:ro` | — |
| `alphafold3_mcp` | `alphafold3/model` → `/app/repo/alphafold3/model` | `af3_db` → `/app/repo/alphafold3/alphafold3_db` |
| `boltz_mcp` | `boltz` → `/opt/boltz_cache` | — |
| `helm_gpt_mcp` | `helmgpt` → `/app/models/helmgpt:ro` | `helmgpt_data` → `/app/examples/data` |
| `highfold3_mcp` | `alphafold3/model` → `/app/repo/alphafold3/model` | `af3_db` → `/app/repo/alphafold3/alphafold3_db` |
| `rfpeptides_mcp` | `rfpeptides/models` → `/app/repo/RFdiffusion/models:ro` | — |

### N2.3 Automatic application

Docker MCPs receive cache directories as auto-mounted, optionally read-only volumes; non-Docker MCPs receive `MACROMNEX_CACHE` as an environment variable. Three mechanisms implement this without operator intervention:

1. **Provisioning.** `_ensure_cache_dirs` creates the declared subdirectories during `cpmcp install`, before the setup script runs, so a first-time download lands in the shared tree rather than inside the server directory.
2. **Container binding.** `_get_cache_volumes` expands each declaration into a `-v <host>:<mount>` argument appended to the generated `docker run` command (N1.5). Assets that must not be modified carry an explicit `:ro` suffix in the `mount` field, so no server can mutate weights another server depends on.
3. **Environment propagation.** For non-containerised runtimes, `_get_cache_env_vars` injects `MACROMNEX_CACHE` into the registration command, letting the server resolve the same paths natively.

### N2.4 Consequences

The scheme yields three properties that matter at the scale of a 38-server toolkit.

*Deduplication.* Large assets are downloaded once. `alphafold3_mcp` and `highfold3_mcp` declare identical `af3_db` and `alphafold3/model` subpaths and therefore share a single copy of the AlphaFold3 databases and weights, which would otherwise be duplicated at hundreds of gigabytes per server.

*Version consistency.* Two servers pointing at the same subpath cannot diverge, so a prediction made through one server and a re-prediction made through another are backed by identical parameters. This is a correctness property rather than a storage saving: silent weight drift between servers would not be visible in any output metric.

*Relocatability.* Moving the cache to a high-capacity or cluster-shared filesystem requires only setting `MACROMNEX_CACHE` before installation, with no registry edit and no per-server configuration. On multi-user systems a single read-only cache root can serve every user's installation, and on HPC deployments the root is pre-staged on shared storage because compute nodes have no outbound network access.

`cpmcp cache` reports the resolved root, whether the environment variable is set explicitly or defaulted, and the existence of every declared subdirectory, so a missing asset is diagnosed before a job is submitted rather than after it fails.

---

## Supplementary Note 3: Asynchronous job execution interface

Compute-intensive tools (RFpeptides, ProteinMPNN, Rosetta KIC, AfCycDesign, Boltz-2, AlphaFold3, Gnina, HELM-GPT, and others) within CycPepMCP operate under an asynchronous job execution model. Tasks are submitted as non-blocking jobs and processed through a queue-based scheduler, allowing the orchestration layer to manage complex workflows without idle waiting. Each job exposes standardized interfaces for monitoring status, retrieving results, and accessing execution logs.

### N3.1 Tool contract

Twenty-six of the 27 in-house server source trees present in `tool-mcps/` implement the contract in `src/jobs/manager.py`:

| Tool | Behaviour |
|---|---|
| `submit_*(...)` | Returns an eight-character `job_id` and queue position immediately |
| `get_job_status(job_id)` | Current state plus submission, start, and completion timestamps |
| `get_job_result(job_id)` | Output paths and success flag; refuses unless the job has completed |
| `get_job_log(job_id, tail=N)` | Captured `stdout`/`stderr` |
| `cancel_job(job_id)` | Removes a pending job or terminates a running one |
| `list_jobs()` | All jobs and their states |
| `get_queue_info()` | Queue depth and currently running job |

Because the contract is identical across servers, a workflow skill can interleave submissions to several tools and collect results as they finish, without tool-specific handling. This uniformity is what allows the orchestration layer to drive a multi-tool campaign — backbone generation, sequence design, structure prediction, docking — as a single polling loop.

### N3.2 Job persistence

All outputs, including intermediate structures, metadata, and logs, are persistently stored, enabling reproducibility and post hoc analysis. Each job is materialised as a directory under the server's `jobs/` root:

```
jobs/<job_id>/
├── metadata.json    # id, name, script path, full argument mapping, status, timestamps
├── job.log          # merged stdout/stderr
├── result.json      # written on successful completion
└── <tool outputs>   # structures, scores, per-run artefacts
```

Persisting state to the filesystem rather than to process memory means results survive a server restart and remain inspectable outside the agent session. `metadata.json` records the complete argument mapping as submitted, so a run is reconstructible from the job directory alone. Metadata updates are written to a temporary file and renamed, which is atomic on POSIX filesystems, so a concurrent reader never observes a partially written record.

### N3.3 Scheduling and state

Jobs progress through five states (`JobStatus`: `pending`, `running`, `completed`, `failed`, `cancelled`). On start-up, `_recover_pending_jobs` scans the jobs root, returns any entry left in `pending` or `running` to `pending`, clears its timestamps, annotates it with `recovered_from`, and re-enqueues it, so an interrupted campaign resumes without operator intervention.

Two admission-control strategies coexist (Table S8). Servers whose tools saturate a GPU for the whole of a run place submissions on a `queue.Queue` drained by a single daemon worker thread, giving strict FIFO execution with exactly one GPU job resident at a time; `boltzgen_mcp` generalises this with a configurable `max_workers` and a GPU pool that auto-detects devices via `nvidia-smi` and leases one per job. The remaining servers, whose operations are shorter or CPU-bound, launch each job on its own daemon thread without admission control. This design keeps the accelerator serialised where contention would cause out-of-memory failures while avoiding needless queuing elsewhere, ensuring efficient utilization of GPU resources while maintaining transparency and traceability across multi-stage pipelines.

**Table S8.** Execution model of the in-house servers. Counts cover the 27 server source trees in `tool-mcps/`; `rosetta_mcp` is distributed as a container image without a source tree in the repository and is not classified here.

| Model | n | Servers | Concurrency |
|---|---|---|---|
| FIFO queue, single worker | 3 | `afcycdesign_mcp`, `rfpeptides_mcp`, `boltzgen_mcp` | 1 job (configurable in `boltzgen_mcp`) |
| Detached thread per job | 22 | `adcp_mcp`, `alphafold3_mcp`, `boltz_mcp`, `gnina_mcp`, `helm_gpt_mcp`, and 17 others | Unbounded |
| Synchronous | 1 | `multicycgt_mcp` | 1 job |
| No job layer | 1 | `amber_mcp` | — |

### N3.4 Throughput characteristics

On a FIFO server, per-job latency is dominated by queue depth rather than by compute, while aggregate throughput is set by the accelerator. In the MDM2 binder-design campaign, 50 designs each requiring approximately 3.4 min of GPU time completed in 2 h 48 min of wall-clock time at approximately 100 % accelerator occupancy; individual jobs waited up to 45 min between submission and start. Campaign planning should therefore budget on the summed compute rather than on observed per-job latency.

### N3.5 Implementation limitations

Three limitations are recorded for completeness.

First, completion write-back is best-effort. If a server process terminates between a job's final output write and the corresponding `metadata.json` update, the record retains `"status": "running"` with a null `completed_at` even though the outputs are complete and valid. This affected 2 of 50 jobs in the MDM2 campaign; both had written full logs and structures, and their runtimes were recovered from file modification times. Consumers of job metadata should treat the presence of `result.json` and the tool's output files, rather than the status field alone, as the authoritative completion signal.

Second, the temporary-file-plus-rename update is atomic per writer but is not serialised across writers. Multiple concurrent resubmissions to the same server can collide on the shared `metadata.json.tmp` name and raise a transient `FileNotFoundError`; resubmissions should be issued sequentially.

Third, servers using the detached-thread model apply no admission control, so an agent submitting many jobs at once can oversubscribe a GPU. Workflow skills that fan out over such servers bound their own concurrency explicitly.

---

## Supplementary Note 4: Automated tool integration

To facilitate extensibility, CycPepMCP includes an automated pipeline for converting external scientific software into MCP-compatible services. Starting from a source repository, the system infers dependencies, executes representative use cases, and generates standardized wrappers with validated inputs and outputs.

### N4.1 Invocation

As summarized in Methods, `cpmcp create` implements the eight-stage conversion of a scientific-software repository into a CycPepMCP-compliant server. A representative invocation is:

```bash
cpmcp create -g <github_url> -d tool-mcps/<name>
```

Additional options control the runtime and resumption: `--runtime uv|conda|auto` fixes the environment backend rather than letting stage 3 infer it, `--rerun-from-step N` restarts from a chosen stage, and `--clear-markers-from-step N` discards checkpoints from a stage onward. A local repository may be supplied in place of a GitHub URL.

### N4.2 Stages

**Table S9.** Stages of the `cpmcp create` pipeline. Each stage is driven by a versioned prompt under `src/prompts/`.

| Stage | Action | Output |
|---|---|---|
| 1 | Prepare the project directory and working layout | Directory skeleton |
| 2 | Clone the repository, including submodules | `repo/` |
| 3 | Create the environment and scan for representative use cases | Environment, use-case inventory |
| 4 | Execute the use cases, debugging failures automatically | Verified working invocations |
| 5 | Refactor working invocations into reusable function scripts | `scripts/` |
| 6 | Extract tool signatures and wrap them in a FastMCP server | `src/server.py` |
| 7 | Exercise the server through the Claude and Gemini CLIs | Integration test results |
| 8 | Generate documentation and the setup script | `README.md`, `quick_setup.sh` |

The design rests on an empirical observation: the hardest part of wrapping scientific software is not the MCP protocol but discovering the invocation that actually runs. Stages 3–5 therefore establish a working invocation *before* any interface code is written, and stage 6 derives tool signatures from code already known to execute. Stage 4 debugs failures automatically, which matters because scientific repositories commonly ship examples that fail against current dependency versions.

### N4.3 Checkpointing

Each stage writes a marker in `.pipeline/`. These markers support selective resumption from a completed checkpoint rather than rerunning the full integration process — important because stages 3 and 4 may take tens of minutes when an environment must be built and use cases executed on GPU. The pipeline concludes by writing an entry into `mcps.yaml` carrying the runtime, paths, and setup script it produced, after which the generated server is indistinguishable from a hand-authored one and is managed through the same commands (Note 1).

---

## Supplementary Note 5: HELM-GPT multi-objective optimization

The HELM-GPT workflow demonstrates CycPepMCP's ability to perform multi-objective optimization in the design of cyclic peptide binders targeting intracellular proteins. Methods describes the HELM-GPT optimization, filtering, structure-based evaluation, and visualization stages; the parameters, routing rule, and scoring functions are retained here for reproducibility.

### N5.1 Phase 1: reinforcement-learning co-optimization

HELM-GPT generates macrocyclic peptides in HELM notation and is fine-tuned by reinforcement learning against a dual reward: KRAS binding affinity from a local XGBoost model and membrane permeability from a local random-forest model. Both scorers run in-process, so no external prediction server participates in the RL loop and a single GPU suffices for the phase.

**Table S10.** Phase 1 optimization parameters, as recorded in `optimization_config.json`.

| Parameter | Value | Role |
|---|---|---|
| `task` | `kras_perm` | Dual-objective reward |
| `n_steps` | 500 | RL steps (maximum 1000) |
| `batch_size` | 32 | Sequences generated per step |
| `sigma` | 60 | Augmented-likelihood sigma |
| `learning_rate` | 1 × 10⁻⁴ | Agent update rate |
| `loss_type` | `reinvent_cpl` | Combined REINVENT and CPL loss |
| `max_len` | 140 | Maximum HELM token length |
| `alpha` | 1.0 | Loss mixing coefficient |

A representative run generated 15,999 sequences over 500 steps in 50.3 min of GPU time. Of these, 14,340 were unique and parsed successfully to valid structures, and 471 satisfied both Phase 1 gates — KRAS K<sub>D</sub> < 10 μM and permeability > −6.0 log cm s⁻¹. The gap between generated and parsable sequences (1,624 rows) reflects HELM strings whose monomer or connection syntax the parser rejects, and is expected for a generative model over a non-canonical monomer alphabet.

### N5.2 Phase 2: heavy-atom routing

The heavy-atom routing rule is retained here for reproducibility. Candidates are converted from HELM to SMILES and their heavy-atom count is obtained with RDKit. Candidates containing no more than 128 heavy atoms enter Boltz-2 SMILES affinity and complex prediction followed by Gnina docking. Candidates exceeding this limit are evaluated using AlphaFold3 with ligand SMILES input followed by Gnina docking. Both routes use a precomputed target MSA to speed up execution.

The 128-atom threshold is imposed by Boltz-2, whose SMILES affinity head has a practical ligand limit at approximately that size; beyond it the model cannot be applied and AlphaFold3 provides the only structural evaluation. In the reference run all 20 selected candidates fell below the threshold (85–93 heavy atoms, median 87), so Boltz-2 supplied both the affinity prediction and the complex structure, and its `ligand_iptm` was used in place of the AlphaFold3 iPTM term.

### N5.3 Phase 3: composite scoring

A composite scoring framework integrates multiple metrics — predicted dissociation constant (K<sub>D</sub>), permeability (log P<sub>app</sub>), interface confidence, and docking scores — to rank candidates. Each metric is min–max normalised within the candidate set before the weighted sum, so the composite lies on a 0–1 scale in which 1 denotes the best value observed on every metric in that run and 0 the worst. Normalisation is therefore relative to the batch, and composite values are not comparable across runs.

For molecules with no more than 128 heavy atoms, the composite score is

<div align="center">

Score = 0.20 × K<sub>D</sub> + 0.15 × Perm + 0.15 × Boltz<sub>Aff</sub> + 0.10 × Boltz<sub>Prob</sub> + 0.10 × iPTM + 0.15 × Gnina<sub>CNN</sub> + 0.15 × Gnina<sub>Vina</sub>

</div>

Here Boltz-2 `ligand_iptm` is used as iPTM in place of the AlphaFold3 iPTM. For candidates with more than 128 heavy atoms, the composite score is

<div align="center">

Score = 0.25 × K<sub>D</sub> + 0.20 × Perm + 0.15 × iPTM + 0.20 × Gnina<sub>CNN</sub> + 0.20 × Gnina<sub>Vina</sub>

</div>

**Table S11.** Composite weight schemes and metric directions. Terms whose raw values improve downward (K<sub>D</sub>, Vina) are inverted during normalisation, so every normalised term is higher-is-better.

| Metric | Source | Direction | ≤128 atoms | >128 atoms |
|---|---|---|---|---|
| KRAS K<sub>D</sub> (μM) | HELM-GPT XGBoost | lower better | 0.20 | 0.25 |
| Permeability (log cm s⁻¹) | HELM-GPT RF | higher better | 0.15 | 0.20 |
| Boltz-2 ensemble affinity | Boltz-2 SMILES | higher better | 0.15 | — |
| Boltz-2 ensemble probability | Boltz-2 SMILES | higher better | 0.10 | — |
| iPTM | AlphaFold3, or Boltz-2 `ligand_iptm` | higher better | 0.10 | 0.15 |
| Gnina CNN affinity | Gnina | higher better | 0.15 | 0.20 |
| Gnina Vina score | Gnina | more negative better | 0.15 | 0.20 |

Both schemes sum to unity. The 0.25 released by dropping the two Boltz-2 terms is redistributed uniformly, each of the five surviving terms gaining exactly 0.05, so the larger-candidate track is not left dominated by a single confidence metric. The practical consequence is that a candidate's rank is not comparable across the two tracks; ranking is performed within a track.

### N5.4 Quality thresholds

| Metric | Threshold | Stage |
|---|---|---|
| KRAS K<sub>D</sub> | < 10 μM | Phase 1 gate |
| Permeability | > −6.0 log cm s⁻¹ | Phase 1 gate |
| AF3 (or Boltz-2) iPTM | > 0.60 | Phase 3 review |
| Gnina CNN affinity | > 6.0 pK<sub>d</sub> | Phase 3 review |

### N5.5 Reference run

The reference KRAS campaign completed end-to-end in 3 h 14 min, of which approximately 2 h 25 min was compute: 50.3 min for Phase 1 reinforcement learning, 44.1 min for target MSA generation, 10.1 min for HELM-to-SMILES conversion and routing, 39.3 min for Boltz-2 affinity prediction across 20 candidates (mean 117.9 s each), 35.0 min for Gnina docking (mean 86.6 s each), and 11.6 min for final ranking. Boltz-2 and Gnina were executed serially on one accelerator; overlapping the structural-evaluation tracks would reduce wall-clock time substantially.

This approach enables efficient navigation of high-dimensional chemical space to optimize multiple properties, particularly for macrocyclic peptides incorporating non-canonical amino acids and complex chemical modifications.
