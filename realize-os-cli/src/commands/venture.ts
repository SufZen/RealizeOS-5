/**
 * realize-os venture - Manage ventures (list, create, export, import).
 *
 * Ventures are sub-systems within RealizeOS, each with their own
 * FABRIC directory structure, agents, and knowledge base.
 */

import { Command } from "commander";
import chalk from "chalk";
import ora from "ora";
import { access, mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { FABRIC_DIRS, validateVentureKey, writeVentureTemplate } from "../venture-template.js";
import { parse as parseYaml, stringify as stringifyYaml } from "../utils/yaml.js";

type SystemConfig = {
  key?: string;
  name?: string;
  directory?: string;
  description?: string;
  agents?: Record<string, unknown>;
  routing?: Record<string, unknown>;
  agent_routing?: Record<string, unknown>;
};

async function fileExists(path: string): Promise<boolean> {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

function normalizeSystems(systems: unknown): SystemConfig[] {
  if (Array.isArray(systems)) {
    return systems as SystemConfig[];
  }

  if (systems && typeof systems === "object") {
    return Object.entries(systems as Record<string, SystemConfig>).map(([key, value]) => ({
      key,
      ...value,
    }));
  }

  return [];
}

function newSystemConfig(key: string, name: string, description?: string): SystemConfig {
  return {
    key,
    name,
    directory: `systems/${key}`,
    ...(description ? { description } : {}),
    routing: {
      content: ["writer", "reviewer"],
      strategy: ["analyst", "orchestrator"],
      research: ["analyst"],
      general: ["orchestrator"],
    },
    agent_routing: {
      writer: ["write", "draft", "post", "blog", "content"],
      analyst: ["analyze", "research", "data", "market"],
      reviewer: ["review", "check", "quality", "approve"],
      orchestrator: ["plan", "help", "think", "prioritize"],
    },
  };
}

export function register(program: Command) {
  const venture = program
    .command("venture")
    .description("Manage ventures (list, create, export, import)");

  venture
    .command("list")
    .description("List all configured ventures")
    .argument("[directory]", "Project directory", ".")
    .action(async (directory: string) => {
      const projectDir = resolve(directory);
      const configPath = join(projectDir, "realize-os.yaml");

      if (!(await fileExists(configPath))) {
        console.log(
          chalk.yellow("No realize-os.yaml found."),
          "Run",
          chalk.cyan("npx realize-os init"),
          "first."
        );
        return;
      }

      const configText = await readFile(configPath, "utf-8");
      const config = parseYaml(configText);
      const systems = normalizeSystems(config?.systems);

      if (systems.length === 0) {
        console.log(chalk.dim("No ventures configured."));
        console.log(
          "Run",
          chalk.cyan("npx realize-os venture create --key my-venture"),
          "to create one."
        );
        return;
      }

      console.log();
      console.log(chalk.bold(`Ventures (${systems.length}):`));
      console.log();

      for (const sys of systems) {
        const key = sys.key || "";
        const name = sys.name || key;
        const dir = sys.directory || `systems/${key}`;
        const exists = await fileExists(join(projectDir, dir));
        const status = exists ? chalk.green("OK") : chalk.red("MISSING");
        const agents = Object.keys(sys.agents || {});

        console.log(`  ${chalk.bold(key)} - ${name} ${chalk.dim(`(${dir})`)} [${status}]`);
        if (agents.length > 0) {
          console.log(chalk.dim(`    Agents: ${agents.join(", ")}`));
        }
      }
      console.log();
    });

  venture
    .command("create")
    .description("Create a new venture")
    .requiredOption("--key <key>", "Venture key (directory name)")
    .option("--name <name>", "Display name")
    .option("--description <desc>", "Venture description")
    .argument("[directory]", "Project directory", ".")
    .action(async (directory: string, options) => {
      const projectDir = resolve(directory);
      const spinner = ora();
      const key = options.key;
      const name = options.name || key;
      const ventureDir = join(projectDir, "systems", key);
      const configPath = join(projectDir, "realize-os.yaml");

      try {
        validateVentureKey(key);
      } catch (error) {
        console.error(chalk.red("Error:"), (error as Error).message);
        process.exit(1);
      }

      if (!(await fileExists(configPath))) {
        console.error(
          chalk.red("Error:"),
          "No realize-os.yaml found. Run",
          chalk.cyan("npx realize-os init"),
          "first."
        );
        process.exit(1);
      }

      const configText = await readFile(configPath, "utf-8");
      const config = parseYaml(configText) || {};
      const systems = normalizeSystems(config.systems);

      if (systems.some((system) => system.key === key)) {
        console.error(chalk.red("Error:"), `Venture '${key}' already exists in realize-os.yaml`);
        process.exit(1);
      }

      if (await fileExists(ventureDir)) {
        console.error(chalk.red("Error:"), `Venture '${key}' already exists at systems/${key}/`);
        process.exit(1);
      }

      spinner.start(`Creating venture '${key}'...`);
      await writeVentureTemplate(projectDir, key, name);
      spinner.succeed(`Created venture '${key}' with FABRIC structure`);

      spinner.start("Updating realize-os.yaml...");
      config.systems = [...systems, newSystemConfig(key, name, options.description)];
      await writeFile(configPath, stringifyYaml(config), "utf-8");
      spinner.succeed("Updated realize-os.yaml");

      console.log();
      console.log(chalk.green.bold("Venture created!"));
      console.log(chalk.dim(`  Path: systems/${key}/`));
      console.log(
        chalk.dim("  Next: customize ") + chalk.cyan(`systems/${key}/F-foundations/venture-identity.md`)
      );
      console.log();
    });

  venture
    .command("export")
    .description("Export a venture to a portable archive")
    .requiredOption("--key <key>", "Venture key to export")
    .option("--output <path>", "Output file path")
    .argument("[directory]", "Project directory", ".")
    .action(async (directory: string, options) => {
      const projectDir = resolve(directory);
      const ventureDir = join(projectDir, "systems", options.key);

      if (!(await fileExists(ventureDir))) {
        console.error(chalk.red("Error:"), `Venture '${options.key}' not found at systems/${options.key}/`);
        process.exit(1);
      }

      const spinner = ora();
      spinner.start(`Exporting venture '${options.key}'...`);

      const files: string[] = [];
      async function walkDir(dir: string, prefix = "") {
        const entries = await readdir(dir, { withFileTypes: true });
        for (const entry of entries) {
          const path = join(prefix, entry.name);
          if (entry.isDirectory()) {
            await walkDir(join(dir, entry.name), path);
          } else {
            files.push(path);
          }
        }
      }
      await walkDir(ventureDir);

      const outputPath = options.output || join(projectDir, `${options.key}-export.json`);
      const exportData = {
        version: "1.0",
        venture_key: options.key,
        exported_at: new Date().toISOString(),
        files,
        file_count: files.length,
      };
      await writeFile(outputPath, JSON.stringify(exportData, null, 2), "utf-8");

      spinner.succeed(`Exported ${files.length} files to ${outputPath}`);
    });

  venture
    .command("import")
    .description("Import a venture from an export file")
    .requiredOption("--file <path>", "Path to export file")
    .option("--key <key>", "Override venture key")
    .argument("[directory]", "Project directory", ".")
    .action(async (directory: string, options) => {
      const projectDir = resolve(directory);
      const spinner = ora();

      if (!(await fileExists(options.file))) {
        console.error(chalk.red("Error:"), `Export file not found: ${options.file}`);
        process.exit(1);
      }

      spinner.start("Importing venture...");
      const exportData = JSON.parse(await readFile(options.file, "utf-8"));
      const key = options.key || exportData.venture_key;

      try {
        validateVentureKey(key);
      } catch (error) {
        spinner.fail((error as Error).message);
        process.exit(1);
      }

      const ventureDir = join(projectDir, "systems", key);

      if (await fileExists(ventureDir)) {
        spinner.fail(`Venture '${key}' already exists. Use a different --key.`);
        process.exit(1);
      }

      for (const dir of FABRIC_DIRS) {
        await mkdir(join(ventureDir, dir), { recursive: true });
      }

      spinner.succeed(`Imported venture '${key}' (${exportData.file_count || 0} files in manifest)`);
      console.log(
        chalk.dim("  Note: File content import requires the source directory. This creates the structure only.")
      );
    });
}
