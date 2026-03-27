# Architecture Checklist

> Architecture compliance review for evaluating AutoBuild output.

## Convention Compliance

- [ ] **File Naming**: 100% of new files match regex `^[a-z0-9-]+(\.[a-z0-9-]+)*$` (kebab-case) or project-specific strictly defined pattern.
- [ ] **Placement**: 100% of new files are located in exact directories dictated by existing module structures (e.g., routes in `/routes`, models in `/models`). No orphaned files outside the `src/` hierarchy.
- [ ] **Imports Sorted**: Import block is strictly ordered (Built-ins, External dependencies, Internal modules).
- [ ] **Symbol Naming**: Variables/functions are explicitly `camelCase`; classes/interfaces are `PascalCase`; constants are `UPPER_SNAKE_CASE`.

## Pattern Consistency

- [ ] **Symmetry**: 100% of new repository/service layers implement the same interface signature patterns as adjacent existing files.
- [ ] **Abstractions**: No ad-hoc wrappers. Exact project abstractions (base controllers, standard Response objects) are inherited or extended.
- [ ] **Error Propagation**: Errors are thrown using typed custom Error classes, not generic `Error` instances or string throws.
- [ ] **Dependency Injection**: 100% of new external services/SDKs are injected via constructor/params, not instantiated inline.

## Module Boundaries

- [ ] **Acyclic Dependencies**: 0 circular dependencies exist in the import graph (pass cycle detection).
- [ ] **Layer Isolation**: Presentation layer files (controllers/routers) contain 0 SQL queries or direct DB schema references.
- [ ] **Direct Access**: Service files contain 0 direct HTTP request parsing (`req.body`, `res.send`); they return data structures to controllers.
- [ ] **Encapsulation**: 100% of cross-cutting concerns (logging, auth, metrics) are applied via middleware or decorators, not inlined in business logic.

## Interface Contracts

- [ ] **Backward Compatibility**: 0 existing API routes have modified paths or removed JSON request/response schema properties.
- [ ] **Schema Conformance**: 100% of new input schemas implement strict validation (e.g., Zod, Joi) denying undeclared properties.
- [ ] **Data Transfer Objects**: 100% of inter-service payloads conform to typed DTO structures rather than generic `any` or `Record<string, unknown>`.
- [ ] **Documentation**: OpenAPI/Swagger definitions exist and pass validation for 100% of new API endpoints.

## Anti-Pattern Detection

- [ ] **DRY Enforcement**: 0 copied/pasted blocks of logic > 5 lines. Standard utilities are reused.
- [ ] **God Classes/Functions**: 0 functions exceed 50 lines of execution logic. 0 classes exceed 300 lines. Max nesting depth <= 3.
- [ ] **Coupling**: 0 direct imports between sibling sub-domains (e.g., `PaymentService` does not directly import `UserDatabaseModel`).
- [ ] **Magic Values**: 0 hardcoded semantic string literals or numbers (excluding 0, 1) used more than once; extracted to constants.

## Scalability

- [ ] **Query Efficiency**: 0 database queries are executed inside loop bodies (no N+1). Bulk `IN` clauses or joins are used.
- [ ] **Pagination Boundary**: 100% of list-returning endpoints enforce a hard `limit` parameter <= 100.
- [ ] **Algorithmic Safety**: 0 nested iterations over unbounded datasets (O(N^2) or worse on user collections).
- [ ] **Async Non-Blocking**: 0 synchronous I/O methods (e.g., `fs.readFileSync`) in async execution paths.
- [ ] **Caching Presence**: Responses for frequently queried, rarely updated data explicitly implement cache headers or Redis wrappers.

## Overall Architecture Assessment

- **Compliance Score Deduction**: Start at 100. Deduct 5 points per failed binary condition.
- **Verdict Threshold**: If Score < 80, VERDICT = `REJECTED`. All artifacts scoring < 80 are strictly flagged and fail validation.
- **Findings**: <!-- List specific failed binary constraints -->
- **Verdict**: PASS / REJECTED
