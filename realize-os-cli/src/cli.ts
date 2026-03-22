#!/usr/bin/env node
/**
 * RealizeOS CLI — Deploy and manage your AI operations system.
 *
 * Usage:
 *   npx realize-os init          Scaffold a new RealizeOS project
 *   npx realize-os start         Start the Docker containers
 *   npx realize-os stop          Stop the Docker containers
 *   npx realize-os status        Check system health and container status
 *   npx realize-os logs          Tail container logs
 *   npx realize-os upgrade       Pull latest image and restart
 *   npx realize-os venture       Manage ventures (list, create, export, import)
 */

import { Command } from "commander";
import chalk from "chalk";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const pkg = require("../package.json");

const program = new Command();

program
  .name("realize-os")
  .description(
    chalk.bold("RealizeOS") +
      " — Deploy and manage your AI operations system with Docker"
  )
  .version(pkg.version, "-v, --version", "Show the CLI version");

// ── Register commands ──────────────────────────────────────────────────────

async function loadCommand(name: string) {
  const mod = await import(`./commands/${name}.js`);
  mod.register(program);
}

async function main() {
  await loadCommand("init");
  await loadCommand("start");
  await loadCommand("stop");
  await loadCommand("status");
  await loadCommand("logs");
  await loadCommand("upgrade");
  await loadCommand("venture");

  // Show help by default if no command
  if (process.argv.length <= 2) {
    program.outputHelp();
    process.exit(0);
  }

  await program.parseAsync(process.argv);
}

main().catch((err) => {
  console.error(chalk.red("Error:"), err.message);
  process.exit(1);
});
