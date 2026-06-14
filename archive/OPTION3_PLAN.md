# Option 3: LLM + COG Pipeline — Verified QA Architecture

## Overview

The LLM handles **language** (parsing questions, generating responses). COG handles **truth** (verifying claims against the knowledge graph). The LLM only runs twice — once to parse, once to respond. All reasoning in between is done by COG for free.

```
User Query → LLM parses → KOMPOSOS stores → COG verifies → LLM responds
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      User Query                          │
│  "Is Python good for machine learning?"                  │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  Step 1: LLM Parse (one LLM call)                       │
│                                                         │
│  Prompt: "Extract a claim from this question."          │
│  Output: {source: "Python", target: "ML",               │
│           relation: "supports"}                         │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  Step 2: KOMPOSOS-IV Knowledge Check                    │
│                                                         │
│  - Check if concepts exist in Category                  │
│  - Find compositional paths: Python→typing→ML_libs→ML   │
│  - If missing, LLM can suggest facts to add             │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  Step 3: COG Verification (no LLM, no tokens)           │
│                                                         │
│  Tier 0: Direct edge? Yes → AGREE (confidence=0.9)      │
│  Tier 1: Compositional path? Found 3 paths              │
│  Tier 2: Sheaf coherence? Neighborhood consistent       │
│  Tier 3: ZFC+CAT dual? Both agree                       │
│  Tier 4: Topology? Same curvature region                │
│                                                         │
│  Result: AGREE, confidence=0.85, tier=1                 │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  Step 4: LLM Respond (one LLM call)                     │
│                                                         │
│  Prompt: "Answer this question using the verified       │
│  result: {status: AGREE, confidence: 0.85,              │
│  paths: [Python→typing→ML]}"                            │
│                                                         │
│  Output: "Yes, Python is well-suited for ML because     │
│  it has strong typing support and extensive libraries." │
└─────────────────────────────────────────────────────────┘
```

---

## Components to Build

### 1. `ClaimExtractor` (LLM Plugin)

Extracts structured claims from natural language questions.

```python
class ClaimExtractor:
    """Use LLM to parse questions into verifiable claims."""

    PROMPT = """
    Extract a verifiable claim from this question.
    Return JSON: {"source": str, "target": str, "relation": str}

    Question: {question}
    """

    async def extract(self, question: str) -> CogClaim:
        response = await self.llm.generate(self.PROMPT.format(question=question))
        data = json.loads(response)
        return CogClaim(data["source"], data["target"], data["relation"])
```

### 2. `VerifiedResponder` (LLM Plugin)

Generates natural language answers using COG verification results.

```python
class VerifiedResponder:
    """Use LLM to generate responses grounded in verified results."""

    PROMPT = """
    Answer the user's question based on this verified result.
    If the result is REJECT or low confidence, say so honestly.
    If AGREE, explain the reasoning path.

    Question: {question}
    Verification: {result}

    Answer:
    """

    async def respond(self, question: str, result: CheckResult) -> str:
        return await self.llm.generate(
            self.PROMPT.format(question=question, result=result.dict())
        )
```

### 3. `VerifiedQA` Pipeline (Orchestrator)

Wires everything together into a single call.

```python
class VerifiedQA:
    """End-to-end verified question answering."""

    def __init__(self, agent: Agent):
        self.agent = agent
        self.extractor = ClaimExtractor()
        self.responder = VerifiedResponder()

    async def answer(self, question: str) -> Dict[str, Any]:
        # Step 1: Parse
        claim = await self.extractor.extract(question)

        # Step 2: Check knowledge
        paths = await self.agent.find_paths(claim.source, claim.target)

        # Step 3: Verify
        result = await self.agent.verify_claim(
            claim.source, claim.target, claim.relation
        )

        # Step 4: Respond
        answer = await self.responder.respond(question, result)

        return {
            "question": question,
            "claim": claim,
            "verification": result,
            "answer": answer,
            "paths_found": len(paths),
        }
```

---

## Example Flow

```python
from orion_komposos_cog import Agent
from pipelines.verified_qa import VerifiedQA

# Start agent
agent = Agent()
await agent.start()

# Pre-load knowledge
await agent.add_knowledge("Python", "typing", "supports", 0.9)
await agent.add_knowledge("typing", "type_safety", "enables", 0.8)
await agent.add_knowledge("type_safety", "ML", "helps_with", 0.7)

# Create pipeline
qa = VerifiedQA(agent)

# Ask question
result = await qa.answer("Is Python good for machine learning?")

print(result["answer"])
# "Yes, Python is well-suited for ML. The knowledge graph shows
#  Python supports typing, which enables type safety, which helps
#  with ML tasks. Confidence: 0.72 (verified through 3-hop path)."

print(result["verification"].status)
# AGREE

print(result["verification"].tier_reached)
# 1 (compositional path finding)
```

---

## Why This Works

| Problem | Traditional LLM | Option 3 |
|---------|----------------|----------|
| Hallucination | Makes up facts | Claims verified against knowledge graph |
| Cost | Every reasoning step costs tokens | COG reasoning is free |
| Explainability | "I think..." | "I know because: Python→typing→ML" |
| Memory | Context window only | Persistent SQLite, survives restarts |
| Confidence | Model's internal probability | Mathematical verification (quantales, paths) |

---

## Implementation Steps

1. **Create `pipelines/` directory** with `verified_qa.py`
2. **Build `ClaimExtractor`** — simple LLM prompt to parse questions into claims
3. **Build `VerifiedResponder`** — LLM prompt that grounds responses in COG results
4. **Build `VerifiedQA` orchestrator** — wires extraction → knowledge → verification → response
5. **Add to `Agent` class** — convenience method `agent.answer(question)`
6. **Test with sample questions** — verify the pipeline works end-to-end

---

## Extensions

- **Multi-claim questions**: "Is Python good for ML and is Rust better?" → extract multiple claims, verify each
- **Knowledge gaps**: If COG can't verify, ask LLM to suggest facts to add
- **Confidence thresholds**: Only respond if verification confidence > threshold
- **Source attribution**: Track where each fact came from (LLM suggested vs. user provided)
