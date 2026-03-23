# ADR-002: Lite/Full Tier Split

> Status: **Accepted**
> Date: 2026-03-10
> Context: Serving both non-technical and technical users with the same product

## Decision

Maintain two distinct runtime tiers that share the same YAML config format and FABRIC directory structure:

- **Lite** — Obsidian vault + CLAUDE.md protocol. Runs via Claude Code/Desktop. No server, no Docker.
- **Full** — Python server with FastAPI, Docker Compose, multi-channel gateway, programmatic engine.

## Why

### For Tier Split
- Non-technical users (solo entrepreneurs) cannot set up Docker, APIs, or servers
- Lite gives them 80% of the value with 0% infrastructure
- Full gives technical users the full platform with extensibility
- Same YAML format means skills, methods, and templates work in both tiers
- Clear upgrade path: start Lite, graduate to Full when you outgrow it

### Against Single Tier
- A server-only product excludes the largest target segment
- A Lite-only product cannot compete with OpenClaw's advanced features
- Two tiers serve two markets without compromising either

## Consequences

- Every shared feature (YAML skills, methods, templates, onboarding) must work in both tiers
- Lite development scope is smaller: content, templates, CLAUDE.md improvements
- Full development scope covers all 13 phases
- Documentation must clearly indicate tier availability per feature
