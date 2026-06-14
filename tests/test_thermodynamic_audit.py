import sys
import os

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from komposos_wesys.adapter import WesysAdapter
from komposos_wesys.core.energy_coherence import (
    GridCategoryBuilder, GrayCategoryLayer, CoherenceGapType
)

def run_landfill_cng_audit():
    print("--- Running Thermodynamic Audit: Landfill-to-CNG Pathway ---")
    
    # 1. Initialize Adapter and Load Data
    adapter = WesysAdapter()
    data_path = 'data/external/WESyS-Model-master/wesys/data/WESyS_Default_Inputs.xlsx'
    adapter.load_wesys_scenario(data_path)
    
    # 2. Build the Grid Category representing the energy flow
    # We'll model a scenario where energy is lost during the compression phase
    builder = GridCategoryBuilder()
    
    # Nodes (Energy States/Nodes)
    nodes = [
        {"id": "LF_Raw_Gas", "kind": "source", "privilege": 0},
        {"id": "Biogas_Cleanup", "kind": "process", "privilege": 1},
        {"id": "CNG_Compression", "kind": "process", "privilege": 2},
        {"id": "Grid_Injection", "kind": "sink", "privilege": 0}
    ]
    
    # Edges (Energy Transitions)
    # We create a "tension" between two parallel paths to test coherence
    edges = [
        # Path A: Standard efficient path
        {"src": "LF_Raw_Gas", "dst": "Biogas_Cleanup", "label": "cleanup_a", "confidence": 0.95},
        {"src": "Biogas_Cleanup", "dst": "CNG_Compression", "label": "compress_a", "confidence": 0.90},
        
        # Path B: Alternative path with high loss (low confidence/efficiency)
        {"src": "LF_Raw_Gas", "dst": "Biogas_Cleanup", "label": "cleanup_b", "confidence": 0.60},
        {"src": "Biogas_Cleanup", "dst": "CNG_Compression", "label": "compress_b", "confidence": 0.40}
    ]
    
    builder.from_cfg(nodes, edges)
    
    # 3. Perform Gray-Category Coherence Scan
    layer = GrayCategoryLayer()
    gaps = layer.scan_builder(builder)
    
    print(f"\nAudit Results: Found {len(gaps)} coherence gaps (energy leaks).")
    
    for mod in gaps:
        print(f"\n[!] Energy Leak Detected: {mod.gap_type.value}")
        print(f"    Location: {mod.gap_location}")
        print(f"    Between Morphisms: {mod.source_2cell.source_morphism} <-> {mod.target_2cell.source_morphism}")
        print(f"    Confidence/Efficiency: {mod.source_2cell.confidence:.2f} vs {mod.target_2cell.confidence:.2f}")
        
        if mod.gap_type == CoherenceGapType.MODIFICATION_MISSING:
            print("    Analysis: This represents a 'Frequency Desync' or Race Condition in the power loop.")
        elif mod.gap_type == CoherenceGapType.COMPOSITION_BOUNDARY:
            print("    Analysis: This represents 'Transmission Waste' crossing a voltage/privilege boundary.")

    if not gaps:
        print("SUCCESS: Thermodynamic loop is coherent. No significant leaks detected.")

if __name__ == "__main__":
    run_landfill_cng_audit()
