/**
 * realize-os init — Scaffold a new RealizeOS project.
 *
 * Creates the project directory with:
 * - docker-compose.yml (generated from EJS template)
 * - .env (from template with user prompts)
 * - systems/ directory for ventures
 * - realize-os.yaml config stub
 */

import { Command } from "commander";
import chalk from "chalk";
import ora from "ora";
import { mkdir, writeFile, access } from "node:fs/promises";
import { join, resolve } from "node:path";
import { generateComposeFile } from "../docker/compose-template.js";
import { generateEnvFile } from "../docker/env-template.js";

/** Default realize-os.yaml config skeleton. */
const DEFAULT_CONFIG = `# RealizeOS Configuration
# See docs for full options: https://github.com/SufZen/RealizeOS-5

systems:
  my-venture:
    name: "My Venture"
    directory: systems/my-venture
    agents:
      chief:
        role: chief-of-staff
        model: gemini_flash
        skills: ["*"]

# Global settings
settings:
  default_model: gemini_flash
  timezone: UTC
`;

/** Gitignore for new projects. */
const GITIGNORE = `# Secrets — never commit
.env
setup.yaml

# Data
data/
*.db

# Python
__pycache__/
*.pyc
.venv/
venv/

# Node
node_modules/

# OS
.DS_Store
Thumbs.db

# Credentials
.credentials/
`;

async function fileExists(path: string): Promise<boolean> {
  try {
    await access(path);
    return true;
  } catch {
    return false;
  }
}

export function register(program: Command) {
  program
    .command("init")
    .description("Scaffold a new RealizeOS project")
    .argument("[directory]", "Target directory", ".")
    .option("--name <name>", "Project name", "realize-os")
    .option("--port <port>", "API port", "8080")
    .option("--image <image>", "Docker image", "ghcr.io/sufzen/realizeos:latest")
    .option("--with-telegram", "Include Telegram bot service", false)
    .option("--with-gws", "Include Google Workspace support", false)
    .option("--force", "Overwrite existing files", false)
    .action(async (directory: string, options) => {
      const targetDir = resolve(directory);
      const spinner = ora();

      console.log();
      console.log(
        chalk.bold.cyan("🚀 RealizeOS") +
          chalk.dim(" — Initializing new project")
      );
      console.log(chalk.dim(`   Target: ${targetDir}`));
      console.log();

      // Check Docker availability (warning only — user can install later)
      try {
        const { execa: execaFn } = await import("execa");
        await execaFn("docker", ["compose", "version"]);
      } catch {
        console.log(chalk.yellow("⚠  Docker Compose not detected."));
        console.log(chalk.dim("   Install Docker Desktop: https://docker.com"));
        console.log(chalk.dim("   You'll need it before running 'npx realize-os start'"));
        console.log();
      }

      // 1. Create directories
      spinner.start("Creating project structure...");
      const dirs = [
        targetDir,
        join(targetDir, "systems"),
        join(targetDir, "systems", "my-venture"),
        join(targetDir, "systems", "my-venture", "F-foundations"),
        join(targetDir, ".credentials"),
      ];
      for (const dir of dirs) {
        await mkdir(dir, { recursive: true });
      }
      spinner.succeed("Project structure created");

      // 2. Generate docker-compose.yml
      spinner.start("Generating docker-compose.yml...");
      const composePath = join(targetDir, "docker-compose.yml");
      if (!options.force && (await fileExists(composePath))) {
        spinner.warn("docker-compose.yml already exists (use --force to overwrite)");
      } else {
        const composeContent = await generateComposeFile({
          projectName: options.name,
          port: options.port,
          image: options.image,
          withTelegram: options.withTelegram,
          withGws: options.withGws,
        });
        await writeFile(composePath, composeContent, "utf-8");
        spinner.succeed("Generated docker-compose.yml");
      }

      // 3. Generate .env
      spinner.start("Generating .env...");
      const envPath = join(targetDir, ".env");
      if (!options.force && (await fileExists(envPath))) {
        spinner.warn(".env already exists (use --force to overwrite)");
      } else {
        const envContent = await generateEnvFile({
          port: options.port,
          withGws: options.withGws,
        });
        await writeFile(envPath, envContent, "utf-8");
        spinner.succeed("Generated .env");
      }

      // 4. Create realize-os.yaml
      spinner.start("Creating realize-os.yaml...");
      const configPath = join(targetDir, "realize-os.yaml");
      if (!options.force && (await fileExists(configPath))) {
        spinner.warn("realize-os.yaml already exists");
      } else {
        await writeFile(configPath, DEFAULT_CONFIG, "utf-8");
        spinner.succeed("Created realize-os.yaml");
      }

      // 5. Create .gitignore
      const gitignorePath = join(targetDir, ".gitignore");
      if (!(await fileExists(gitignorePath))) {
        await writeFile(gitignorePath, GITIGNORE, "utf-8");
      }

      // 6. Create venture identity stub
      const identityPath = join(
        targetDir,
        "systems",
        "my-venture",
        "F-foundations",
        "venture-identity.md"
      );
      if (!(await fileExists(identityPath))) {
        await writeFile(
          identityPath,
          `# Venture Identity\n\n## Name\nMy Venture\n\n## Mission\n[Describe your venture's mission]\n\n## Voice & Tone\n[Describe the communication style]\n`,
          "utf-8"
        );
      }

      // Done!
      console.log();
      console.log(chalk.green.bold("✅ Project initialized!"));
      console.log();
      console.log(chalk.bold("Next steps:"));
      console.log(
        chalk.dim("  1.") +
          " Edit " +
          chalk.cyan(".env") +
          " and add your API keys"
      );
      console.log(
        chalk.dim("  2.") +
          " Edit " +
          chalk.cyan("realize-os.yaml") +
          " to configure your system"
      );
      console.log(
        chalk.dim("  3.") +
          " Customize " +
          chalk.cyan("systems/my-venture/F-foundations/venture-identity.md")
      );
      console.log(
        chalk.dim("  4.") +
          " Run " +
          chalk.cyan("npx realize-os start") +
          " to launch"
      );
      console.log();
    });
}
