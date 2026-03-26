# Architecture Checklist

> Architecture compliance review for evaluating AutoBuild output.

## Convention Compliance

- [ ] File naming follows project conventions
- [ ] Files are placed in the correct directory/module
- [ ] Import ordering follows project standards
- [ ] Naming (variables, functions, classes) follows conventions

## Pattern Consistency

- [ ] New code uses the same design patterns as existing similar code
- [ ] Same abstractions are used (repositories, services, controllers, etc.)
- [ ] Error handling follows the established pattern
- [ ] Dependency injection used where the project expects it

## Module Boundaries

- [ ] No circular dependencies introduced
- [ ] Layer boundaries respected (presentation → business → data)
- [ ] Cross-cutting concerns handled through proper middleware/decorators
- [ ] No direct database access from presentation layer

## Interface Contracts

- [ ] No breaking changes to existing APIs
- [ ] New interfaces are consistent with existing ones
- [ ] Data transfer objects follow established patterns
- [ ] Event/message contracts are documented

## Anti-Pattern Detection

- [ ] No code duplication — shared utilities used where available
- [ ] No god classes/functions (should be decomposed)
- [ ] No tight coupling between unrelated modules
- [ ] No magic numbers or strings

## Scalability

- [ ] No N+1 query patterns
- [ ] Large data sets paginated or streamed
- [ ] No expensive operations inside loops
- [ ] No blocking calls in async contexts
- [ ] Caching used where appropriate

## Overall Architecture Assessment

- **Compliance:** FULLY COMPLIANT / MINOR ISSUES / VIOLATIONS
- **Findings:** <!-- List specific issues -->
- **Verdict:** PASS / NEEDS CHANGES
