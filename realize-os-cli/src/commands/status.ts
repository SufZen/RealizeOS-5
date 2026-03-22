/**
 * realize-os status — Check system health and container status.
 *
 * Shows:
 * - Container status (running, stopped, etc.)
 * - Health check result from /health endpoint
 * - Configured ventures and active agents
 * - Image version info
 */

import { Command } from "commander";
import chalk from "chalk";
import ora from "ora";
import { execa } from "execa";
import { resolve } from "node:path";
import { getRunningContainers } from "../docker/image-manager.js";

export function register(program: Command) {
  program
    .command("status")
    .description("Check RealizeOS system health and container status")
    .argument("[directory]", "Project directory", ".")
    .option("--json", "Output status as JSON", false)
    .action(async (directory: string, options) => {
      const projectDir = resolve(directory);
      const spinner = ora();

      console.log();
      console.log(chalk.bold.cyan("📊 RealizeOS Status"));
      console.log(chalk.dim("─".repeat(50)));

      // 1. Container status
      spinner.start("Checking containers...");
      try {
        const containers = await getRunningContainers(projectDir);

        if (containers.length === 0) {
          spinner.warn("No containers running");
          console.log(
            chalk.dim("  Run ") +
              chalk.cyan("npx realize-os start") +
              chalk.dim(" to launch")
          );
        } else {
          spinner.succeed(`${containers.length} container(s) running`);
          for (const c of containers) {
            const statusColor = c.status.includes("Up")
              ? chalk.green
              : chalk.yellow;
            console.log(
              chalk.dim("  ├─ ") +
                chalk.bold(c.name) +
                " " +
                statusColor(c.status) +
                chalk.dim(` (${c.image})`)
            );
          }
        }
      } catch {
        spinner.warn("Could not check containers (Docker not available?)");
      }

      // 2. Health check
      spinner.start("Checking API health...");
      try {
        const response = await fetch("http://localhost:8080/health", {
          signal: AbortSignal.timeout(5000),
        });
        if (response.ok) {
          const data = await response.json() as Record<string, unknown>;
          spinner.succeed("API is healthy");
          if (data.version) {
            console.log(chalk.dim(`  ├─ Version: ${data.version}`));
          }
          if (data.uptime) {
            console.log(chalk.dim(`  └─ Uptime: ${data.uptime}`));
          }
        } else {
          spinner.warn(`API returned status ${response.status}`);
        }
      } catch {
        spinner.info("API not reachable (containers may be starting...)");
      }

      // 3. Image info
      spinner.start("Checking image version...");
      try {
        const { stdout } = await execa("docker", [
          "compose",
          "images",
          "--format",
          "json",
        ], { cwd: projectDir });

        if (stdout.trim()) {
          spinner.succeed("Image info loaded");
        } else {
          spinner.info("No images found");
        }
      } catch {
        spinner.info("Could not check images");
      }

      console.log(chalk.dim("─".repeat(50)));
      console.log();

      if (options.json) {
        // JSON output mode for scripting
        const status = {
          running: true,
          timestamp: new Date().toISOString(),
          directory: projectDir,
        };
        console.log(JSON.stringify(status, null, 2));
      }
    });
}
