# KOMPOSOS-IV-WESYS Project Instructions

## Architecture
This project follows a specialized WESyS (Waste-to-Energy System Simulation) integration architecture.

### Directory Structure
- `src/komposos_wesys/`: WESyS domain adapter and scenario graph.
- `src/operadum/`: Resource-operation design and ranking engine.
- `src/pronoia/`: Audit, MDL, and sheaf/contradiction probes.
- `src/komposos_core/`: Core categorical and cognitive machinery (seeded from KOMPOSOS-IV).
- `data/external/`: Gitignored external WESyS model data.
- `scripts/`: Utility scripts (e.g., `fetch_wesys.py`).
- `tests/`: Project-specific verification tests.

## Development Standards
- **Thermodynamic Constraints**: All energy loops modeled must respect $E_{out} \le E_{in}$.
- **Logical Integrity**: Use Pronoia sheaf probes to flag structural contradictions in power grid topologies.
- **Performance**: Use `power-grid-model` for high-performance steady-state calculations.

## External Models
- **WESyS (NREL)**: System dynamics model for WTE infrastructure.
- **Power Grid Model (LF Energy)**: For electrical grid transmission and congestion analysis.
