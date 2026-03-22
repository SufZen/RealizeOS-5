/**
 * realize-os upgrade — Pull the latest image and restart.
 *
 * Steps:
 * 1. Pull latest Docker image from GHCR
 * 2. Stop running containers
 * 3. Start with new image
 * 4. Run any pending migrations
 * 5. Report the version change
 */

import { Command } from "commander";
import chalk from "chalk";
import ora from "ora";
import { execa } from "execa";
import { resolve } from "node:path";
import { getCurrentImageVersion, getLatestImageVersion } from "../docker/image-manager.js";

export function register(program: Command) {
  program
    .command("upgrade")
    .description("Pull the latest RealizeOS image and restart")
    .argument("[directory]", "Project directory", ".")
    .option("--dry-run", "Show what would be upgraded without doing it", false)
    .option("--force", "Force pull even if already up to date", false)
    .action(async (directory: string, options) => {
      const projectDir = resolve(directory);
      const spinner = ora();

      console.log();
      console.log(
        chalk.bold.cyan("⬆️  RealizeOS Upgrade")
      );
      console.log();

      // 1. Check current version
      spinner.start("Checking current version...");
      const currentVersion = await getCurrentImageVersion(projectDir);
      spinner.succeed(`Current version: ${chalk.dim(currentVersion || "unknown")}`);

      // 2. Pull latest
      spinner.start("Pulling latest image...");
      if (options.dryRun) {
        spinner.info("Dry run — skipping pull");
      } else {
        try {
          await execa("docker", ["compose", "pull"], {
            cwd: projectDir,
            stdio: "pipe",
          });
          spinner.succeed("Latest image pulled");
        } catch (err: any) {
          spinner.fail("Failed to pull image");
          console.error(chalk.red(err.stderr || err.message));
          process.exit(1);
        }
      }

      // 3. Check if upgrade needed
      const latestVersion = await getLatestImageVersion(projectDir);
      if (currentVersion === latestVersion && !options.force) {
        console.log(chalk.green("\n✅ Already on the latest version!"));
        return;
      }

      // 4. Restart with new image
      spinner.start("Restarting with new image...");
      if (options.dryRun) {
        spinner.info(`Dry run — would upgrade from ${currentVersion} to ${latestVersion}`);
      } else {
        try {
          await execa("docker", ["compose", "up", "-d", "--force-recreate"], {
            cwd: projectDir,
            stdio: "pipe",
          });
          spinner.succeed("Containers restarted with new image");
        } catch (err: any) {
          spinner.fail("Failed to restart containers");
          console.error(chalk.red(err.stderr || err.message));
          process.exit(1);
        }
      }

      // 5. Health check
      spinner.start("Waiting for health check...");
      let healthy = false;
      for (let i = 0; i < 30; i++) {
        try {
          const response = await fetch("http://localhost:8080/health", {
            signal: AbortSignal.timeout(2000),
          });
          if (response.ok) {
            healthy = true;
            break;
          }
        } catch {
          // Not ready yet
        }
        await new Promise((r) => setTimeout(r, 1000));
      }

      if (healthy) {
        spinner.succeed("System is healthy");
      } else {
        spinner.warn("Health check timed out — system may still be starting");
      }

      // Done
      console.log();
      if (currentVersion && latestVersion && currentVersion !== latestVersion) {
        console.log(
          chalk.green("✅ Upgraded: ") +
            chalk.dim(currentVersion) +
            chalk.dim(" → ") +
            chalk.bold(latestVersion)
        );
      } else {
        console.log(chalk.green("✅ Upgrade complete"));
      }
      console.log();
    });
}
