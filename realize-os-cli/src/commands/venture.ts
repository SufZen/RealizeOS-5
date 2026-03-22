/**
 * realize-os venture — Manage ventures (list, create, export, import).
 *
 * Ventures are sub-systems within RealizeOS, each with their own
 * FABRIC directory structure, agents, and knowledge base.
 */

import { Command } from "commander";
import chalk from "chalk";
import ora from "ora";
import { mkdir, writeFile, readFile, readdir, access, cp } from "node:fs/promises";
import { join, resolve } from "node:path";
import { parse as parseYaml, stringify as stringifyYaml } from "../utils/yaml.js";

async function fileExists(path: string): Promise<boolean> {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

/** FABRIC directory structure for a new venture. */
const FABRIC_DIRS = [
  "F-foundations",
  "A-agents",
  "B-brand",
  "R-resources",
  "I-intelligence",
  "C-communication",
];

export function register(program: Command) {
  const venture = program
    .command("venture")
    .description("Manage ventures (list, create, export, import)");

  // ── venture list ──────────────────────────────────────────────────────
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
      const systems = config?.systems || {};
      const keys = Object.keys(systems);

      if (keys.length === 0) {
        console.log(chalk.dim("No ventures configured."));
        console.log(
          "Run",
          chalk.cyan("npx realize-os venture create --key my-venture"),
          "to create one."
        );
        return;
      }

      console.log();
      console.log(chalk.bold(`Ventures (${keys.length}):`));
      console.log();

      for (const key of keys) {
        const sys = systems[key];
        const name = sys.name || key;
        const dir = sys.directory || `systems/${key}`;
        const exists = await fileExists(join(projectDir, dir));
        const status = exists
          ? chalk.green("OK")
          : chalk.red("MISSING");
        const agents = Object.keys(sys.agents || {});

        console.log(
          `  ${chalk.bold(key)} — ${name} ${chalk.dim(`(${dir})`)} [${status}]`
        );
        if (agents.length > 0) {
          console.log(chalk.dim(`    Agents: ${agents.join(", ")}`));
        }
      }
      console.log();
    });

  // ── venture create ────────────────────────────────────────────────────
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

      // Check if already exists
      if (await fileExists(ventureDir)) {
        console.error(
          chalk.red("Error:"),
          `Venture '${key}' already exists at systems/${key}/`
        );
        process.exit(1);
      }

      // Create FABRIC structure
      spinner.start(`Creating venture '${key}'...`);
      for (const dir of FABRIC_DIRS) {
        await mkdir(join(ventureDir, dir), { recursive: true });
      }

      // Create venture identity
      await writeFile(
        join(ventureDir, "F-foundations", "venture-identity.md"),
        `# ${name}\n\n## Mission\n[Define your venture's mission]\n\n## Voice & Tone\n[Define the communication style]\n`,
        "utf-8"
      );

      // Create agent stub
      await writeFile(
        join(ventureDir, "A-agents", "chief.md"),
        `# Chief of Staff Agent\n\nRole: chief-of-staff\nModel: gemini_flash\nSkills: ["*"]\n\n## Instructions\n[Define agent behavior]\n`,
        "utf-8"
      );

      spinner.succeed(`Created venture '${key}' with FABRIC structure`);

      // Update realize-os.yaml
      const configPath = join(projectDir, "realize-os.yaml");
      if (await fileExists(configPath)) {
        spinner.start("Updating realize-os.yaml...");
        const configText = await readFile(configPath, "utf-8");
        const config = parseYaml(configText) || {};
        config.systems = config.systems || {};
        config.systems[key] = {
          name,
          directory: `systems/${key}`,
          ...(options.description ? { description: options.description } : {}),
          agents: {
            chief: {
              role: "chief-of-staff",
              model: "gemini_flash",
              skills: ["*"],
            },
          },
        };
        await writeFile(configPath, stringifyYaml(config), "utf-8");
        spinner.succeed("Updated realize-os.yaml");
      }

      console.log();
      console.log(chalk.green.bold("✅ Venture created!"));
      console.log(chalk.dim(`  Path: systems/${key}/`));
      console.log(
        chalk.dim("  Next: customize ") +
          chalk.cyan(`systems/${key}/F-foundations/venture-identity.md`)
      );
      console.log();
    });

  // ── venture export ────────────────────────────────────────────────────
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
        console.error(
          chalk.red("Error:"),
          `Venture '${options.key}' not found at systems/${options.key}/`
        );
        process.exit(1);
      }

      // For now, a simple JSON export of the directory listing
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

      const outputPath =
        options.output || join(projectDir, `${options.key}-export.json`);
      const exportData = {
        version: "1.0",
        venture_key: options.key,
        exported_at: new Date().toISOString(),
        files: files,
        file_count: files.length,
      };
      await writeFile(outputPath, JSON.stringify(exportData, null, 2), "utf-8");

      spinner.succeed(`Exported ${files.length} files to ${outputPath}`);
    });

  // ── venture import ────────────────────────────────────────────────────
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
        console.error(
          chalk.red("Error:"),
          `Export file not found: ${options.file}`
        );
        process.exit(1);
      }

      spinner.start("Importing venture...");
      const exportData = JSON.parse(
        await readFile(options.file, "utf-8")
      );

      const key = options.key || exportData.venture_key;
      const ventureDir = join(projectDir, "systems", key);

      if (await fileExists(ventureDir)) {
        spinner.fail(`Venture '${key}' already exists. Use a different --key.`);
        process.exit(1);
      }

      // Create the venture directory structure
      for (const dir of FABRIC_DIRS) {
        await mkdir(join(ventureDir, dir), { recursive: true });
      }

      spinner.succeed(
        `Imported venture '${key}' (${exportData.file_count || 0} files in manifest)`
      );
      console.log(
        chalk.dim(
          "  Note: File content import requires the source directory. " +
            "This creates the structure only."
        )
      );
    });
}
