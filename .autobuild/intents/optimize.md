# Optimization Intent

> Use this template when you want to improve a specific measurable metric.

## Goal

<!-- What are you optimizing? e.g., "Reduce API response latency for /users endpoint" -->

## Context

<!-- Current state: what is the metric now? Why is it a problem? -->

## Scope

### IN

- <!-- Files/modules that can be modified -->

### OUT

- <!-- Files/modules that must NOT be touched -->
- <!-- Features that must not be affected -->

## Metric

- **What:** <!-- e.g., response latency, bundle size, memory usage -->
- **How to measure:** <!-- e.g., `npm run bench`, `python -m pytest --benchmark`, `k6 run` -->
- **Current value:** <!-- e.g., 230ms -->
- **Target value:** <!-- e.g., < 100ms -->
- **Direction:** <!-- minimize | maximize -->

## Acceptance Criteria

- [ ] <!-- Metric reaches target value -->
- [ ] <!-- No regression in other metrics -->
- [ ] <!-- All tests still pass -->
- [ ] <!-- No security issues introduced -->

## Constraints

- <!-- Must not change public API contracts -->
- <!-- Must not add heavy dependencies for marginal gains -->

## Build Mode

**Mode:** `optimize`

## Budget

- **Max iterations:** 20
