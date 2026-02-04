# Setup
pdb = 'diffused_binder_cyclic_1_mpnn1'
model = mk_afdesign_model('binder')

# Prepare inputs
model.prep_inputs(
    f'{pdb}.pdb',
    binder_chain='B',
    target_chain='A',
    use_binder_template=False,
    use_multimer=True,
    use_initial_guess=True
)

# Configure cyclic design
add_cyclic_offset(model, offset_type=2)

# Set sequence and prediction options
model.set_seq(mode='wildtype')
model.set_opt(num_recycles=1)

# Run prediction
model.predict(models=[0, 1], verbose=False)

# Save results
model.save_pdb(f'diffused_binder_cyclic_1_mpnn1_prediction.pdb')

# Extract and log scores
rmsd = model.aux['losses']['rmsd']
ipae = model.aux['all']['losses']['i_pae'][0]

with open(f'score.sc', 'a') as outfile:
    outfile.write(f'{pdb},{ipae},{rmsd}\n')