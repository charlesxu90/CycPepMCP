# Supplementary Information — CycPepMCP

---

## Supplementary Note 1. MCP registry, data model, cache system, and execution architecture

This note details the implementation of the MCP-server layer summarised in *System architecture and agentic orchestration*: the declarative registry that describes every server, the object model derived from it, the runtime-detection and registration logic, the centralised cache, and the asynchronous job architecture used by compute-bound servers. All identifiers below refer to the reference implementation (`src/cycpep_mcp/`).

### N1.1 Registry organisation

Server descriptions are held in two YAML registries rather than in code, so that adding a tool requires no modification of the CLI or the orchestration layer:

| Registry | Path | Entries | Contents |
|---|---|---|---|
| In-house | `src/cycpep_mcp/configs/mcps.yaml` | 28 | Scientific-software servers developed in this work |
| Public | `src/cycpep_mcp/configs/public_mcps.yaml` | 10 | Third-party database and utility servers |

Each file contains a single top-level `mcps:` mapping keyed by server name; each value is a flat mapping of the fields in Table S4. The registry is the single source of truth consumed by `cpmcp` for every operation — listing, searching, installation, registration, cache provisioning, and status reporting — and is loaded lazily with an in-process memo (`MCPManager.load_installed_mcps`, `load_public_mcps`), refreshable via `force_reload`. `cpmcp sync` reconciles the registry against the contents of `tool-mcps/`, and `MCPManager.discover_tool_mcps` can infer entries for directories that are present on disk but absent from the registry.

Relative `path` values are resolved against the project root at load time (`resolve_path`), so a registry checked into version control remains portable across installations; absolute paths are honoured unchanged.

### N1.2 Data model

Each registry entry is deserialised into an `MCP` dataclass instance with 18 fields (Table S4). The dataclass carries both the declarative description and the full installation/registration lifecycle as methods (`install`, `uninstall`, `register`, `unregister`, `get_status`), so that a server is manipulated as a single object regardless of its runtime.

**Table S4.** Fields of the `MCP` data model and their occupancy across the 28 in-house entries.

| Field | Type | Default | Present in | Purpose |
|---|---|---|---|---|
| `name` | str | — | 28/28 | Registry key and CLI identifier |
| `url` | str | `""` | 28/28 | Upstream repository |
| `description` | str | `""` | 28/28 | One-line summary shown by `cpmcp avail`/`search` |
| `source` | str | `"Community"` | 28/28 | Provenance tag (`Tool`, `Community`, …) |
| `runtime` | str | `"python"` | 28/28 | Dispatch key; see N1.3 |
| `python_version` | str | `"3.10"` | 28/28 | Interpreter version for environment creation |
| `setup_commands` | list[str] | `[]` | 28/28 | Legacy inline setup steps |
| `setup_script` | str | `""` | 28/28 | Setup entry point (`quick_setup.sh` throughout) |
| `server_command` | str | `""` | 28/28 | Executable that starts the server |
| `server_args` | list[str] | `[]` | 28/28 | Arguments, typically `src/server.py` |
| `env_vars` | dict | `{}` | 28/28 | Environment injected at registration |
| `dependencies` | list[str] | `[]` | 28/28 | System-level prerequisites |
| `path` | str \| None | `None` | 28/28 | Install location, relative to project root |
| `docker_image` | str \| None | `None` | 16/28 | Image reference, `ghcr.io/MacromNex/<name>:latest` |
| `docker_args` | list[str] | `[]` | 28/28 | Extra `docker run` flags (e.g. `--gpus all`, `--ipc=host`) |
| `docker_volumes` | list[str] | `[]` | 28/28 | Additional bind mounts |
| `cache_data` | dict | `{}` | 3/28 | `{subpath, mount}` under the shared data cache |
| `cache_model` | dict | `{}` | 6/28 | `{subpath, mount}` under the shared model cache |

Serialisation is symmetric (`to_dict`/`from_dict`), so registry entries edited programmatically round-trip without loss.

### N1.3 Runtime detection and registration

The `runtime` field selects one of seven dispatch paths (`MCPRuntime`: `docker`, `python`, `uv`, `node`, `uvx`, `npx`, `binary`). Their distribution is given in Table S5.

**Table S5.** Runtime distribution across the two registries.

| Runtime | In-house (n=28) | Public (n=10) | Installation action | Isolation |
|---|---|---|---|---|
| `docker` | 16 | 0 | Resolve local image, else pull from GHCR | Container |
| `uv` | 7 | 0 | Create `uv` virtual environment, install dependencies | Project venv |
| `python` | 5 | 4 | Execute `quick_setup.sh` (Conda/Mamba environment) | Named env |
| `node` | 0 | 6 | Package-manager install | Node modules |
| `uvx` / `npx` / `binary` | 0 | 0 | No installation required (resolved at launch) | — |

Installation is idempotent: `install()` short-circuits when the server is already present unless `force=True`, and invalidates the status cache (N1.5) on entry so that subsequent queries reflect the new state. For Docker entries, `_resolve_docker_image` prefers a locally built image (`<name>:latest`) over the published GHCR tag, which allows a developer build to shadow the release image without editing the registry.

Registration translates an `MCP` object into a `claude mcp add` (or `gemini mcp add`) invocation, with the command line built per runtime. Server names are sanitised for CLI use by replacing `/` and `-` with `_` (`_get_clean_name`). For containerised servers the generated command is

```
claude mcp add <clean_name> [--env K=V ...] -- \
  docker run -i --rm --user <uid>:<gid> <docker_args> \
    -v <cwd>:<cwd> [-v <docker_volumes> ...] [-v <cache mounts> ...] <image>
```

Running the container under the invoking user's UID/GID keeps job artefacts writable on the host, and bind-mounting the working directory allows the agent to pass host paths to tools unchanged — the property that lets a single natural-language workflow hand a PDB file from one server to another without staging. For interpreter-based servers, `_find_python_env` prefers a co-located environment (`env/bin/python`, `.venv/bin/python`, `venv/bin/python`) and `_find_server_entry` locates the entry point by probing conventional locations (`src/server.py`, `server.py`, `src/index.py`, …) before falling back to a recursive glob. The `scope` argument of `register()` (`project`/`global`) is accepted but currently unused; registrations are written to the CLI's default user-level configuration.

### N1.4 Centralised cache

Model weights and reference databases are shared across all servers through a single cache root, resolved at run time as `$MACROMNEX_CACHE` with a fallback of `~/.macromnex/cache`, and partitioned into two subtrees:

```
$MACROMNEX_CACHE/
├── data/     # reference databases, sequence/structure corpora
└── model/    # trained network weights
```

A server declares its requirements in the registry as two optional nested mappings, each with a `subpath` (relative to `data/` or `model/`) and a `mount` (the absolute path at which the directory is made visible inside the container):

```yaml
alphafold3_mcp:
  cache_data:
    subpath: af3_db
    mount: /app/repo/alphafold3/alphafold3_db
  cache_model:
    subpath: alphafold3/model
    mount: /app/repo/alphafold3/model
```

Three mechanisms apply these declarations automatically:

1. **Provisioning.** `_ensure_cache_dirs` creates the declared subdirectories during `cpmcp install`, before any setup script runs, so that a first-time download lands in the shared tree rather than inside the server directory.
2. **Container binding.** `_get_cache_volumes` expands each declaration to a `-v <host>:<mount>` argument appended to the generated `docker run` command. Read-only assets carry an explicit `:ro` suffix in the `mount` field (Table S6), preventing a server from mutating weights shared with other servers.
3. **Environment propagation.** For non-containerised runtimes, `_get_cache_env_vars` injects `MACROMNEX_CACHE` into the registration command, letting the server resolve the same paths natively.

**Table S6.** Registry cache declarations. Suffix `:ro` denotes a read-only mount.

| MCP server | `cache_model` subpath → mount | `cache_data` subpath → mount |
|---|---|---|
| `afcycdesign_mcp` | `alphafold2/params` → `/app/params:ro` | — |
| `alphafold3_mcp` | `alphafold3/model` → `/app/repo/alphafold3/model` | `af3_db` → `/app/repo/alphafold3/alphafold3_db` |
| `boltz_mcp` | `boltz` → `/opt/boltz_cache` | — |
| `helm_gpt_mcp` | `helmgpt` → `/app/models/helmgpt:ro` | `helmgpt_data` → `/app/examples/data` |
| `highfold3_mcp` | `alphafold3/model` → `/app/repo/alphafold3/model` | `af3_db` → `/app/repo/alphafold3/alphafold3_db` |
| `rfpeptides_mcp` | `rfpeptides/models` → `/app/repo/RFdiffusion/models:ro` | — |

The scheme yields three practical benefits. Large assets are downloaded once: `alphafold3_mcp` and `highfold3_mcp` declare identical `af3_db` and `alphafold3/model` subpaths and therefore share a single copy of the AlphaFold3 databases and weights. Version consistency is enforced by construction, since two servers pointing at the same subpath cannot diverge. And relocating the cache to a high-capacity or shared filesystem requires only setting `MACROMNEX_CACHE`, with no registry edit. `cpmcp cache` reports the resolved root, whether the environment variable is set, and the existence of every declared subdirectory.

### N1.5 Status caching

Determining whether a server is installed and registered requires filesystem probes and a CLI query per server, which is prohibitive when listing 38 entries. A shared status cache (`tool-mcps/mcp.status`) stores a timestamped mapping from server name to one of four states (`MCPStatus`: `not_installed`, `installed`, `registered`, `both`) with a 300-second time-to-live. All reads and writes acquire an exclusive `fcntl.flock` on the cache file, so that concurrent `cpmcp` invocations cannot interleave partial writes. Mutating operations invalidate the affected entry explicitly rather than waiting for expiry, and `cpmcp status --refresh` forces a full re-probe.

### N1.6 Asynchronous job architecture

Structure prediction, diffusion-based backbone generation, docking, and molecular dynamics run for minutes to hours — far longer than an interactive tool call should block. Twenty-six of the 27 in-house server source trees present in `tool-mcps/` therefore expose long-running operations through a uniform asynchronous contract implemented in `src/jobs/manager.py`: a `submit_*` tool returns an eight-character job identifier immediately, and the agent polls `get_job_status(job_id)` until completion before calling `get_job_result(job_id)`. `get_job_log`, `list_jobs`, `cancel_job`, and `get_queue_info` complete the interface. Because the contract is identical across servers, a workflow skill can interleave submissions to several tools and collect results as they finish without tool-specific handling.

Each job is materialised as a directory under the server's `jobs/` root, containing `metadata.json` (identifier, human-readable name, script path, full argument mapping, status, and `submitted_at` / `started_at` / `completed_at` timestamps), the captured `stdout`/`stderr` stream, a `result.json` written on success, and the tool's own output files. Persisting state to the filesystem rather than to process memory means results survive a server restart and remain inspectable outside the agent session. Metadata updates are written to a temporary file and renamed, which is atomic on POSIX filesystems, so a concurrent reader never observes a partially written record.

Jobs progress through five states (`JobStatus`: `pending`, `running`, `completed`, `failed`, `cancelled`). On start-up, `_recover_pending_jobs` scans the jobs root, returns any entry left in `pending` or `running` to `pending`, clears its timestamps, annotates it with `recovered_from`, and re-enqueues it, so an interrupted campaign resumes without operator intervention.

Two admission-control strategies coexist (Table S7). Servers whose tools saturate a GPU for the whole of a run — `afcycdesign_mcp`, `rfpeptides_mcp`, and `boltzgen_mcp` — place submissions on a `queue.Queue` drained by a single daemon worker thread, giving strict FIFO execution with exactly one job resident on the accelerator at a time; `boltzgen_mcp` generalises this with a configurable `max_workers` and a GPU pool that auto-detects available devices via `nvidia-smi` and leases one per job. The remaining servers, whose operations are shorter or CPU-bound, launch each job on its own daemon thread without admission control. This design keeps the accelerator serialised where contention would cause out-of-memory failures, while avoiding needless queuing elsewhere. The consequence for campaign planning is that per-job latency on a queued server is dominated by queue depth rather than by compute: in the MDM2 case study (Supplementary Note 3), 50 designs each requiring ~3.4 min of GPU time completed in 2 h 48 min of wall-clock time at ~100% accelerator occupancy, but individual jobs waited up to 45 min before starting.

**Table S7.** Execution model of the in-house servers. Counts cover the 27 server source trees in `tool-mcps/`; `rosetta_mcp` is distributed as a container image without a source tree in the repository and is therefore not classified here.

| Model | n | Servers | Concurrency |
|---|---|---|---|
| FIFO queue, single worker | 3 | `afcycdesign_mcp`, `rfpeptides_mcp`, `boltzgen_mcp` | 1 job (configurable in `boltzgen_mcp`) |
| Detached thread per job | 22 | `adcp_mcp`, `alphafold3_mcp`, `boltz_mcp`, `gnina_mcp`, `helm_gpt_mcp`, and 17 others | Unbounded |
| Synchronous | 1 | `multicycgt_mcp` | 1 job |
| No job layer | 1 | `amber_mcp` | — |

### N1.7 Implementation limitations

Three limitations of the current implementation are worth recording.

First, completion write-back is best-effort. If a server process is terminated between a job's final output write and the corresponding `metadata.json` update, the record retains `"status": "running"` with a null `completed_at` even though the outputs are complete and valid. This affected 2 of 50 jobs in the MDM2 campaign; both had written full logs and structures, and their runtimes had to be recovered from file modification times. Consumers of job metadata should treat the presence of `result.json` and the tool's output files, rather than the status field alone, as the authoritative completion signal.

Second, the temporary-file-plus-rename update is atomic per writer but is not serialised across writers. Multiple concurrent resubmissions to the same server can collide on the shared `metadata.json.tmp` name and raise a transient `FileNotFoundError`. Resubmissions should therefore be issued sequentially.

Third, servers using the detached-thread model apply no admission control, so an agent that submits many jobs at once can oversubscribe a GPU. Workflow skills that fan out over such servers bound their own concurrency explicitly.
