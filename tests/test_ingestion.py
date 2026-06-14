import sys
import os

# Add src to path so we can import our modules
sys.path.append(os.path.join(os.getcwd(), 'src'))

from komposos_wesys.adapter import WesysAdapter

def test_data_ingestion():
    adapter = WesysAdapter()
    data_path = 'data/external/WESyS-Model-master/wesys/data/WESyS_Default_Inputs.xlsx'
    
    print("--- Testing WESyS Data Ingestion ---")
    try:
        adapter.load_wesys_scenario(data_path)
        graph = adapter.build_resource_graph()
        
        # Simple verification
        objects = graph.objects()
        print(f"Verified: Found {len(objects)} resource nodes in the graph.")
        
        if len(objects) > 0:
            print("SUCCESS: Data ingestion and graph construction functional.")
        else:
            print("WARNING: Resource graph is empty.")
            
    except Exception as e:
        print(f"FAILED: {str(e)}")

if __name__ == "__main__":
    test_data_ingestion()
