// commitlint.config.js — Conventional Commits enforcement for RealizeOS
// Types aligned with the v5.5.0 infrastructure spec
module.exports = {
  extends: ['@commitlint/config-conventional'],
  rules: {
    'type-enum': [
      2,
      'always',
      [
        'feat',     // new feature
        'fix',      // bug fix
        'docs',     // documentation only
        'style',    // formatting, no code change
        'refactor', // code change, no feature/fix
        'perf',     // performance improvement
        'test',     // adding or fixing tests
        'build',    // build system, dependencies
        'ci',       // CI/CD configuration
        'chore',    // tooling, repo maintenance
        'revert',   // revert a commit
        'dream',    // proposed by the Dreaming subsystem
      ],
    ],
    'scope-enum': [
      1,  // warning, not error — new scopes emerge naturally
      'always',
      [
        'core',       // realize_core/
        'api',        // realize_api/
        'dashboard',  // dashboard/
        'cli',        // realize-os-cli/
        'lite',       // realize_lite/
        'docs',       // docs/
        'v5.5.0',     // v5.5.0 design docs
        'fabric',     // FABRIC system
        'runtimes',   // Runtime adapters
        'synapse',    // Synapse event bus
        'heart',      // Heart kernel
        'dreaming',   // Dreaming subsystem
        'infra',      // infrastructure, CI/CD
        'deps',       // dependencies
        'release',    // release automation
      ],
    ],
    'subject-case': [2, 'never', ['start-case', 'pascal-case', 'upper-case']],
    'header-max-length': [2, 'always', 100],
    'body-max-line-length': [1, 'always', 200],  // warning only
  },
};
