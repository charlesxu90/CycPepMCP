Design a cyclic peptide binder for the target protein in                                                               
    @examples/case1_cycpep_design/4HFZ_MDM2.pdb using rfpeptides_mcp                                                     
                                                                                                                         
    Steps:                                                                                                               
    1. First validate the PDB file using validate_pdb_file                                                               
    2. Submit a binder design job with submit_cyclic_binder (12-16 residues, 10                                          
    designs)                                                                                                             
    3. Monitor the job with get_job_status until completed                                                               
    4. Retrieve results with get_job_result    

 Next Steps:                                                                                                            
  1. Use LigandMPNN to design sequences for the backbones                                                                
  2. Validate with AfCycDesign for structure prediction                                                                  
  3. Filter designs based on metrics (iPAE, pLDDT)  