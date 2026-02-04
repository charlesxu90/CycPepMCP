prefix=./outputs/diffused_binder_cyclic
pdb='./target.pdb'
num_designs=400
script="rf_diffusion/run_inference.py"

python $script \
  --config-name base \
  inference.output_prefix=$prefix \
  inference.num_designs=$num_designs \
  contigmap.contigs=['12-18,0 A1-113,0'] \
  inference.input_pdb=$pdb \
  inference.cyclic=True \
  diffuser.T=50 \
  +inference.cyc_chains='a' \
  +ppi.hotspot_res=['A68','A70']