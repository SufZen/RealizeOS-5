# RealizeOS v5.5.0 — Design Documents

> **Status**: Pre-spec-kit staging location. These documents will migrate to `.specify/` in Phase B of the infrastructure rollout.

This directory contains the five canonical design documents for the v5.5.0 architecture evolution. They were produced in a prior planning session (May 2026) and landed here as the first infrastructure step (Phase 0).

## Documents

| Document | Description |
|---|---|
| [realizeos-v5.5.0-master-design.md](realizeos-v5.5.0-master-design.md) | 17-section canonical architecture — the Heart, FABRIC, Senses/Limbs, Mission Engine, Runtime Adapters, and the full biological metaphor. Draft v3. |
| [runtime-adapter-contract.md](runtime-adapter-contract.md) | Python Protocol definition for Runtime Adapters — data types, lifecycle hooks, capability negotiation, and 7 adapter sketches (Claude, Codex, Gemini, GPT, Ollama, Cursor, RealizeInternal). |
| [fabric-semantic-tags.md](fabric-semantic-tags.md) | Vocabulary of 13 canonical XML-in-markdown semantic tags — the structured annotation layer that makes FABRIC documents machine-readable while staying human-authored. |
| [fabric-entity-schemas.md](fabric-entity-schemas.md) | JSON Schemas (Draft 2020-12) for the five core FABRIC entity types: decision, mission, contact, commitment, insight. |
| [development-infrastructure-setup.md](development-infrastructure-setup.md) | Target-state CI/CD and development infrastructure — 11 GitHub Actions workflows, 5-tier testing strategy, Phase A–F migration plan. |

## Migration Plan

After Phase B (spec-kit adoption):

- **Master design** → `.specify/memory/constitution.md`
- **Runtime adapter contract** → `.specify/specs/000-runtime-adapter/`
- **Fabric semantic tags** → `.specify/specs/001-fabric-semantic-tags/`
- **Fabric entity schemas** → `.specify/specs/002-fabric-entity-schemas/`
- **Infrastructure setup** → `docs/development/infrastructure.md` (stays in `docs/`, not a spec)

## Related

- [handoff-setup-plan.md](handoff-setup-plan.md) — Gap analysis and Phase 0–F execution plan that led to this directory existing.
