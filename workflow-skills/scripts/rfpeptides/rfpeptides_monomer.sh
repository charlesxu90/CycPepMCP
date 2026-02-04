python rf_diffusion/run_inference.py \
  inference.output_prefix=/path/to/folder/file_prefix \
  inference.num_designs=200 \
  contigmap.contigs=['8-8'] \
  inference.cyclic=True \
  inference.cyc_chains='a' \
  diffuser.T=50