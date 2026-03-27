# Review Checklist

> Used during Phase 5 (EVALUATE) for structured, deterministic objective review by AI and human evaluators.

## The 7 Dimensions of Quality

### 1. Correctness
- [ ] **Intent Mapping**: 100% of explicit `should do` statements from the system intent map to successful test assertions.
- [ ] **No regressions**: 0 tests in the existing suite fail after integrating the artifact.

### 2. Completeness
- [ ] **Acceptance Criteria**: 100% of acceptance criteria defined in the issue/intent have a corresponding TRUE testable outcome.
- [ ] **No ToDos**: 0 `TODO`, `FIXME`, or stub functions (`pass`, `NotImplementedError`) remain in the deployed code artifact.

### 3. Edge Cases
- [ ] **Null/Empty Handling**: Inputs containing `null`, `undefined`, `[]`, or empty strings `""` are explicitly guarded against or handled via test cases.
- [ ] **Boundary Limits**: Extreme integer boundaries (0, -1, MaxInt) and over-length strings are explicitly covered by tests.

### 4. Error Handling
- [ ] **Typed Errors**: 100% of I/O boundaries and cross-network calls are wrapped in `try/catch` (or error-tuples).
- [ ] **Meaningful Messages**: Errors returned to users omit stack traces but contain precise, documented error codes.
- [ ] **No Silent Failures**: 0 instances of empty `catch` blocks or intentionally swallowed exceptions without explicit audit logging.

### 5. Readability
- [ ] **Lint Compliance**: 0 unresolved warnings or errors from the codebase's configured linter.
- [ ] **Formatting**: Code strictly passes automated format validators (e.g., Prettier/Black) with 0 deviations.
- [ ] **Descriptive Naming**: 0 single-letter variables exist (except standard loop indices `i`, `j`, or math coordinates `x`, `y`, `z`).

### 6. Maintainability
- [ ] **Complexity Limits**: 0 functions have a cyclomatic complexity > 10.
- [ ] **Nesting Limits**: 0 code blocks exceed 3 levels of nested indentation (`if` inside `for` inside `if`).
- [ ] **Docstrings**: 100% of exported public functions/classes have standard JSDoc/Docstring header documentation.

### 7. No Dead Code
- [ ] **Unused Imports**: 0 unused library or file imports detected by AST static analysis.
- [ ] **Unreachable Logic**: 0 lines of unreachable code (e.g., code after a `return` or unconditional `throw`).
- [ ] **Unused Variables**: 0 declared variables remain unread/unassigned in their scope.

## Overall Assessment & Strict Threshold Guard

- **Quality Score:** ___ / 100
  *(Algorithm: Start at 100. Deduct 5 points for every unchecked box across all checklists.)*
- **Verdict Guarantees:** 
  - If Score >= 80 and 0 Critical Security Box fail: **APPROVE**
  - If Score < 80: **REJECTED** (Any iterative code artifact scoring < 80 is strictly flagged and fails evaluation. NO EXCEPTIONS.)
- **Summary:** <!-- List exactly which objective dimensions caused deductions -->
