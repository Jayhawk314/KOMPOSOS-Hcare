# Orion Core Attribution

## About Orion

**Orion Core** is an independent open-source project created and maintained by **Borkwork**.

- **Repository**: https://github.com/borkwork/orion-framework
- **License**: MIT License
- **Copyright**: © Borkwork

## Orion in This Repository

The `orion-main/` directory contains a copy of Orion Core for integration purposes. This copy remains under its original MIT license and is the property of its creators.

**We do not claim any ownership over Orion Core.**

## KOMPOSOS-IV Integration

The files in the `bridges/` directory are **KOMPOSOS-IV code** that integrates with Orion Core:

- **Bridge Plugins** (bridges/*.py)
  - License: Apache-2.0 OR KOMPOSOS-IV-Commercial (dual-licensed)
  - Copyright: © 2024-2026 James Ray Hawkins
  - Purpose: Integration layer between Orion, KOMPOSOS-IV, and COG

These bridge plugins are separate works that utilize Orion's plugin API (which is MIT licensed).

## License Compatibility

- **Orion Core**: MIT License (permissive, allows commercial use)
- **KOMPOSOS-IV**: Apache-2.0 OR Commercial (dual-licensed)
- **Bridge Plugins**: Apache-2.0 OR Commercial (integrates the two)

The MIT license (Orion) is compatible with Apache-2.0 (KOMPOSOS-IV bridges), so these can work together legally.

## Mutual Inspiration

KOMPOSOS-IV and Orion inspired each other through collaborative discussions between their creators:

- **Orion → KOMPOSOS-IV**: "Runtime is first-class" architecture principle
- **KOMPOSOS-IV → Orion**: Category theory provides mathematical foundations

Both projects remain independently owned and maintained.

## Attribution in Code

All bridge plugins include proper attribution:

```python
# This bridge plugin is dual-licensed (Apache-2.0 OR KOMPOSOS-IV-Commercial).
# It integrates with Orion Core, which is separately licensed under MIT.
# Orion Core © Borkwork (https://github.com/borkwork/orion-framework)
```

## Contact

- **Orion Core**: See https://github.com/borkwork/orion-framework
- **KOMPOSOS-IV**: James Ray Hawkins (this repository)

---

**Thank you to the Orion Core team for creating an excellent plugin framework!**
