python protein_mpnn_run.py \
  --pdb_path ./diffused_binder_cyclic_1.pdb \
  --pdb_path_chains A \
  --temperature 0.0001 \
  --backbone_noise 0 \
  --omit_AAs C \
  --num_seq_per_target 1 \
  --path_to_model_weights vanilla_model_weights/v_48_020.pt