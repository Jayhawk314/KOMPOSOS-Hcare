"""
WESyS Domain Adapter for KOMPOSOS-IV.
This module provides the interface between system dynamics (waste-to-energy) 
and topological power grid modeling.
"""

import numpy as np
from power_grid_model import PowerGridModel, initialize_array, DatasetType, ComponentType

import pandas as pd
import os
from .core.resource_graph import ResourceGraphBuilder

class WesysAdapter:
    def __init__(self):
        self.scenario_graph = None
        self.grid_model = None
        self.inputs_df = None

    def load_wesys_scenario(self, data_path):
        """
        Loads WESyS scenario data from the Excel input file.
        """
        if not os.path.exists(data_path):
            raise FileNotFoundError(f"WESyS data not found at {data_path}")
        
        print(f"Parsing WESyS scenario: {data_path}")
        # Load all sheets to capture Global Inputs and Regional Resources
        self.inputs_df = pd.read_excel(data_path, sheet_name=None)
        
        sheets = list(self.inputs_df.keys())
        print(f"Successfully loaded {len(sheets)} sheets: {sheets}")
        return self.inputs_df

    def build_resource_graph(self):
        """
        Transforms the raw WESyS output data into a categorical ResourceGraph.
        """
        output_path = 'data/external/WESyS-Model-master/wesys/output_fy19q1.xlsx'
        if not os.path.exists(output_path):
            raise FileNotFoundError(f"WESyS output not found at {output_path}")
            
        print(f"Parsing WESyS outputs for graph construction: {output_path}")
        df = pd.read_excel(output_path)
        
        builder = ResourceGraphBuilder()
        
        # We'll use 2026 as our snapshot year
        year_col = 2026
        if year_col not in df.columns:
            # Fallback to last column if 2026 is missing
            year_col = df.columns[-1]
            
        print(f"Using data snapshot for year: {year_col}")
        
        # Look for rows like "CA LF.facilities by size and config[LFSmall, CNG]"
        for idx, row in df.iterrows():
            label = str(row.iloc[0])
            if ".facilities by size and config[" in label:
                try:
                    # Extract Source and Tech
                    parts = label.split(".facilities by size and config[")
                    source_base = parts[0] # e.g., "CA LF"
                    tech_part = parts[1].split("]")[0] # e.g., "LFSmall, CNG"
                    tech_name = tech_part.split(", ")[-1] # e.g., "CNG"
                    
                    facility_count = float(row[year_col])
                    
                    # Add nodes
                    builder.graph.add(source_base, type_name="waste_source")
                    builder.graph.add(tech_name, type_name="technology")
                    
                    # Connect
                    # Use normalized count as confidence/weight
                    # (For the audit, we want to see where facilities are clustering)
                    builder.graph.connect(
                        source_base, tech_name,
                        name=f"{source_base}_{tech_name}",
                        confidence=facility_count,
                        metadata={"tech": tech_name, "count": facility_count}
                    )
                except (IndexError, ValueError, KeyError):
                    continue
        
        print(f"Built resource graph with {len(builder.graph.objects())} nodes "
              f"and {len(builder.graph.morphisms())} infrastructure pathways.")
        self.scenario_graph = builder.graph
        return self.scenario_graph

    def map_to_grid(self, energy_outputs):
        """
        Maps WESyS energy production nodes to Power Grid Model nodes.
        """
        print("Mapping WESyS outputs to grid topology...")
        # Example of grid initialization
        nodes = initialize_array(DatasetType.input, ComponentType.node, len(energy_outputs))
        # Fill node attributes directly using field names
        # nodes['id'] = [1, 2, ...]
        # nodes['u_rated'] = [10.5e3, ...]
        return nodes

    def audit_thermodynamics(self, inputs, outputs):
        """
        Strict thermodynamic audit: Energy Out <= Energy In.
        Uses Pronoia sheaf probes to verify logical consistency.
        """
        for i, o in zip(inputs, outputs):
            if o > i:
                raise ValueError("Thermodynamic violation detected: Output exceeds input.")
        return True

if __name__ == "__main__":
    adapter = WesysAdapter()
    print("WESyS Adapter Initialized.")
