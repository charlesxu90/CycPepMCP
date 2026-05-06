#!/usr/bin/env python3
"""Stage case3 prior model into the helm_gpt_mcp Docker cache and verify predictor parity.

Copies `perm_prior/gpt_model_final_0.105.{pt,json}` into
`$MACROMNEX_CACHE/model/helmgpt/` (host) which is mounted into the container at
`/app/models/helmgpt`. Verifies that `rl_predictors/` and `monomer_library.csv`
match the predictor bundle baked into the MCP.
"""
import hashlib
import os
import shutil
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = CASE_DIR.parent.parent
MCP_REPO_DATA = REPO_ROOT / "tool-mcps" / "helm_gpt_mcp" / "repo" / "helm-gpt" / "data"

PRIOR_FILES = ["gpt_model_final_0.105.pt", "gpt_model_final_0.105.json"]

PARITY_CHECKS = [
    (CASE_DIR / "rl_predictors/kras_kd/kras_xgboost_reg.pkl",
     MCP_REPO_DATA / "kras_kd/kras_xgboost_reg.pkl"),
    (CASE_DIR / "rl_predictors/perm/regression_rf.pkl",
     MCP_REPO_DATA / "cpp/regression_rf.pkl"),
    (CASE_DIR / "rl_predictors/perm/pred_cpp_perm.pkl",
     MCP_REPO_DATA / "cpp/pred_cpp_perm.pkl"),
    (CASE_DIR / "rl_predictors/perm/scaffold_k_fold_idxes.pkl",
     MCP_REPO_DATA / "cpp/scaffold_k_fold_idxes.pkl"),
    (CASE_DIR / "monomer_library.csv",
     MCP_REPO_DATA / "prior/monomer_library.csv"),
]


def md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cache_root() -> Path:
    return Path(os.environ.get("MACROMNEX_CACHE", Path.home() / ".macromnex" / "cache"))


def stage_prior(dest_dir: Path) -> list[Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    staged = []
    for name in PRIOR_FILES:
        src = CASE_DIR / "perm_prior" / name
        if not src.exists():
            raise FileNotFoundError(f"Missing case3 prior file: {src}")
        dst = dest_dir / name
        if dst.exists() and md5(src) == md5(dst):
            print(f"  [skip] {dst}  (md5 match)")
        else:
            shutil.copy2(src, dst)
            print(f"  [copy] {src.name}  ->  {dst}")
        staged.append(dst)
    return staged


def verify_parity() -> bool:
    all_ok = True
    for case_path, mcp_path in PARITY_CHECKS:
        if not case_path.exists():
            print(f"  [WARN] case3 file missing: {case_path}")
            all_ok = False
            continue
        if not mcp_path.exists():
            print(f"  [WARN] MCP file missing: {mcp_path} (run `cpmcp install helm_gpt_mcp` first)")
            all_ok = False
            continue
        if md5(case_path) == md5(mcp_path):
            print(f"  [ok]   {case_path.relative_to(CASE_DIR)}")
        else:
            print(f"  [DIFF] {case_path.relative_to(CASE_DIR)}  !=  baked-in MCP copy")
            print(f"         pass model_path=... to predict_* tools to use the case3 file instead")
            all_ok = False
    return all_ok


def main() -> int:
    print(f"case3 dir : {CASE_DIR}")
    print(f"cache root: {cache_root()}")
    cache_model_dir = cache_root() / "model" / "helmgpt"

    print("\nStaging prior into MCP cache_model mount:")
    stage_prior(cache_model_dir)

    print("\nVerifying predictor / monomer_library parity with baked-in MCP defaults:")
    parity_ok = verify_parity()

    container_prior = "/app/models/helmgpt/gpt_model_final_0.105.pt"
    print()
    print(f"Container prior path: {container_prior}")
    print()
    print("Use this in submit_optimize_peptides:")
    print(f'  prior_model="{container_prior}"')
    print('  task="kras_perm"')
    print('  output_dir="/app/results/case3"')
    print('  n_steps=500, batch_size=32, loss_type="reinvent_cpl", device="cuda"')

    if not parity_ok:
        print("\nNote: at least one parity check failed; predict_permeability and predict_kras_binding")
        print("      now accept a `model_path` argument if you need to point at the case3 pickles.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
