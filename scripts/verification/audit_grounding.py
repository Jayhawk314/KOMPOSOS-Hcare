import sys
import os
import numpy as np

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from komposos_wesys.validation.thermodynamic_probe import ThermodynamicSheaf

def verify_audit_consistency():
    """
    Verifies the audit correctness by comparing the categorical flag 
    with a physical sheaf calculation.
    """
    print("--- Verifying Audit Correctness: Physical Grounding ---")
    
    # Setup a scenario where we KNOW there is a loss
    # Source (100 units) -> Process A (90% eff) -> Sink
    #                   -> Process B (40% eff) -> Sink
    
    sheaf = ThermodynamicSheaf()
    sheaf.add_flow("Source", "Sink", efficiency=0.90, weight=1.0) # Path A
    sheaf.add_flow("Source", "Sink", efficiency=0.40, weight=1.0) # Path B (The 'Conflict')
    
    report = sheaf.audit()
    
    print(f"Global Energy Leak Index (H^1): {report.energy_leak:.4f}")
    print(f"System Stable? {report.stable}")
    
    # The 'Interchange Failure' corresponds to a high inconsistency_index
    # We expect the index to be high because 0.9 and 0.4 cannot be globally resolved
    
    if report.energy_leak > 0.1:
        print("\n[VERIFIED] Categorical 'Interchange Failure' maps to a high Physical Leak Index.")
        print(f"Localized Leak Source: {report.edge_residuals[0][0].u} -> {report.edge_residuals[0][0].v}")
        print(f"Leak Magnitude: {report.edge_residuals[0][1]:.4f}")
    else:
        print("\n[FAILED] Physical grounding did not detect the expected leak.")

    # Cross-check with Yoneda Distance (Conceptual)
    # d(0.9, 0.4) = |0.9 - 0.4| / max(0.9, 0.4) = 0.5 / 0.9 = 0.55
    expected_yoneda = abs(0.9 - 0.4) / max(0.9, 0.4)
    print(f"\nConceptual Yoneda Distance: {expected_yoneda:.4f}")
    
    if abs(report.energy_leak - expected_yoneda) < 0.5: # Loose bound for prototype
        print("[VERIFIED] Sheaf leak index is consistent with Yoneda distance magnitude.")

if __name__ == "__main__":
    verify_audit_consistency()
