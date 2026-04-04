# Examples

Production examples demonstrating the three-layer architecture.

## Production Agent

`production_agent.py` - Complete example showing all three layers:

### What it demonstrates:

1. **Agent Creation** - Initialize the three-layer stack
2. **Plugin Addition** (Orion) - Add web search capability
3. **Fact Gathering** - Use plugins to collect information
4. **Knowledge Storage** (KOMPOSOS-IV) - Store facts in categorical graph
5. **Graph Querying** - Find paths and neighbors
6. **Claim Verification** (COG) - Tiered reasoning
7. **Session Management** - Per-user persistent memory
8. **Statistics** - Get agent metrics

### Run it:

```bash
python examples/production_agent.py
```

### Expected output:

```
======================================================================
Three-Layer AI Agent Example
======================================================================

Step 1: Creating agent...
Starting agent...
✓ Agent started!

Step 2: Adding web search plugin (Orion layer)...
✓ Plugin added!

Step 3: Using web search to gather facts...
Found 2 results:
  - Python has extensive ML libraries (confidence: 0.95)
  - TensorFlow and PyTorch use Python (confidence: 0.9)

Step 4: Storing facts in categorical knowledge graph...
✓ Facts stored in knowledge graph!

Step 5: Querying knowledge graph...
Found 1 path(s) from Python to TensorFlow:
  Path 1: length=2, weight=0.855
    has → includes

Python neighbors: 3 outgoing
  → ML_libraries (has)
  → typing (supports)

Step 6: Verifying claims with tiered reasoning (COG layer)...

Claim 1: 'Python has ML_libraries'
  Status: AGREE
  Confidence: 0.95
  Tier reached: 0
  Explanation: Direct edge exists: has (confidence=0.95)

Claim 2: 'Python includes TensorFlow' (compositional)
  Status: AGREE
  Confidence: 0.4
  Tier reached: 1
  Explanation: Found 1 path(s), shortest length 2
  Proof path: ['has', 'includes']

Claim 3: 'Python supports Rust' (unknown)
  Status: PARTIAL
  Confidence: 0.0
  Tier reached: 1
  Explanation: No compositional path found within 5 hops

Step 7: Session management (per-user memory)...
✓ Loaded session for user 'alice'
✓ Added user-specific knowledge
✓ Session saved

Step 8: Agent statistics...

Orion (Application Layer):
  Plugins: 4

KOMPOSOS-IV (Mathematical Layer):
  Objects: 5
  Morphisms: 4

COG (Reasoning Layer):
  Concepts added: 0
  Relations added: 0
  Checks performed: 3

Sessions:
  Active: 1

Stopping agent...
✓ Agent stopped cleanly!

======================================================================
Example complete!
======================================================================
```

## Key Takeaways

The example shows how:
- **Orion** provides extensible tools (web search plugin)
- **KOMPOSOS-IV** provides persistent knowledge (categorical graph)
- **COG** provides intelligent reasoning (tiered verification)

Together they create a complete AI agent with:
- Hot-loadable capabilities
- Formal verification
- Persistent memory
- Mathematical guarantees
