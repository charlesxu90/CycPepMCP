from pyrosetta import *

# Initialize PyRosetta with beta_nov16 weights
init('-beta_nov16')

# Load Rosetta XML configuration
xml = 'cycpep_fast_relax.xml'
objs = protocols.rosetta_scripts.XmlObjects.create_from_file(xml)

# Get movers from XML
fr = objs.get_mover('full_relax_complex')
pcm = objs.get_mover('pcm')

# Load PDB structure
pose = pose_from_pdb('diffused_binder_cyclic_1_mpnn.pdb')

# Apply cyclization and relaxation
pcm.apply(pose)
fr.apply(pose)
pcm.apply(pose)

# Save output
pose.dump_pdb('diffused_binder_cyclic_1_mpnn1.pdb')