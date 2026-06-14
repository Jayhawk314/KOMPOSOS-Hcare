import sys
import os
import numpy as np

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from komposos_wesys.adapter import WesysAdapter
from komposos_wesys.core.energy_coherence import GrayCategoryLayer, GridCategoryBuilder
from komposos_wesys.geometry.grid_spectral import SpectralGraphAnalyzer

def run_california_full_audit():
    print("--- 🗺️ California Regional Energy Audit: Full Scale ---")
    
    # 1. Ingest Data and Build Graph
    adapter = WesysAdapter()
    data_path = 'data/external/WESyS-Model-master/wesys/data/WESyS_Default_Inputs.xlsx'
    adapter.load_wesys_scenario(data_path)
    graph = adapter.build_resource_graph()
    
    # 2. Spectral Health Analysis
    print("\n--- ⚡ Spectral Grid Health ---")
    analyzer = SpectralGraphAnalyzer(graph)
    try:
        analyzer.build_laplacian()
        vals = np.sort(np.linalg.eigvals(analyzer.laplacian))
        fiedler_value = vals[1] if len(vals) > 1 else 0
        
        # Calculate components via Laplacian (nullity of L = # of components)
        n_components = np.sum(vals < 1e-10)
        
        print(f"Algebraic Connectivity (Fiedler Value): {fiedler_value:.4f}")
        print(f"Number of Independent Grid Components: {n_components}")
        
        if n_components > 1:
            print(f"Status: Grid is FRAGMENTED into {n_components} isolated islands.")
        elif fiedler_value > 0.1:
            print("Status: Regional grid is tightly coupled and stable.")
        else:
            print("Status: Grid has weak coupling; vulnerable to isolation.")
            
    except Exception as e:
        print(f"Spectral analysis skipped: {str(e)}")

    # 3. Thermodynamic Coherence Scan
    print("\n--- 🔍 Stability Scan: Identifying Inefficiencies ---")
    builder = GridCategoryBuilder()
    
    nodes = [{"id": obj.name, "kind": obj.type_name, "privilege": 0} 
             for obj in graph.objects()]
    edges = [{"src": m.source, "dst": m.target, "label": m.name, "confidence": m.confidence} 
             for m in graph.morphisms()]
    
    builder.from_cfg(nodes, edges)
    
    layer = GrayCategoryLayer()
    gaps = layer.scan_builder(builder)
    
    print(f"\nRegional Audit Results: Found {len(gaps)} Efficiency Gaps across the model.")
    
    if gaps:
        # Sort by severity (facility count involved in the gap)
        gaps.sort(key=lambda x: x.source_2cell.confidence, reverse=True)
        
        total_impacted_facilities = sum(mod.source_2cell.confidence for mod in gaps)
        
        print("\nTop 5 Energy Hotspots (Most Critical Leaks):")
        for i, mod in enumerate(gaps[:5]):
            resource_name = mod.source_2cell.source_morphism.split('_')[0]
            tech_name = mod.source_2cell.source_morphism.split('_')[1]
            print(f"{i+1}. Resource: {resource_name} -> {tech_name}")
            print(f"   Gap Type: {mod.gap_type.value}")
            print(f"   Impacted Facilities: {mod.source_2cell.confidence:.0f}")

        # 4. Societal Value Calculation
        print("\n--- 💰 Realized Societal Value & Cost Savings ---")
        # Assumptions for the prototype:
        # Optimizing a 'leaky' facility saves ~$50,000/year in reduced waste/maintenance.
        annual_savings = total_impacted_facilities * 50000
        
        print(f"Total Facilities with Efficiency Gaps: {total_impacted_facilities:.0f}")
        print(f"Potential Annual Savings: ${annual_savings/1e6:.2f} Million")
        print("Note: Savings derived from resolving interchange failures and frequency desyncs.")
    else:
        print("SUCCESS: No major structural inefficiencies detected in the regional model.")

if __name__ == "__main__":
    run_california_full_audit()
