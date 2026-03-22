/**
 * realize-os start — Start the Docker containers.
 *
 * Runs `docker compose up -d` in the project directory.
 * Checks for Docker availability before starting.
 */

import { Command } from "commander";
import chalk from "chalk";
import ora from "ora";
import { execa } from "execa";
import { access } from "node:fs/promises";
import { resolve } from "node:path";

async function checkDocker(): Promise<boolean> {
  try {
    await execa("docker", ["compose", "version"]);
    return true;
  } catch {
    return false;
  }
}

export function register(program: Command) {
  program
    .command("start")
    .description("Start the RealizeOS Docker containers")
    .argument("[directory]", "Project directory", ".")
    .option("--build", "Rebuild containers before starting", false)
    .option("--detach", "Run in background (default: true)", true)
    .action(async (directory: string, options) => {
      const projectDir = resolve(directory);
      const spinner = ora();

      // Check Docker
      spinner.start("Checking Docker...");
      if (!(await checkDocker())) {
        spinner.fail(
          "Docker Compose not found. Install Docker Desktop: https://docker.com"
        );
        process.exit(1);
      }
      spinner.succeed("Docker is available");

      // Check docker-compose.yml exists
      try {
        await access(`${projectDir}/docker-compose.yml`);
      } catch {
        console.error(
          chalk.red("Error:"),
          "No docker-compose.yml found. Run",
          chalk.cyan("npx realize-os init"),
          "first."
        );
        process.exit(1);
      }

      // Start containers
      const args = ["compose", "up"];
      if (options.detach) args.push("-d");
      if (options.build) args.push("--build");

      spinner.start("Starting RealizeOS...");
      try {
        await execa("docker", args, {
          cwd: projectDir,
          stdio: "pipe",
        });
        spinner.succeed("RealizeOS is running!");

        console.log();
        console.log(
          chalk.dim("  Dashboard: ") +
            chalk.cyan("http://localhost:8080")
        );
        console.log(
          chalk.dim("  API:       ") +
            chalk.cyan("http://localhost:8080/docs")
        );
        console.log(
          chalk.dim("  Health:    ") +
            chalk.cyan("http://localhost:8080/health")
        );
        console.log();
        console.log(
          chalk.dim("  View logs: ") +
            chalk.cyan("npx realize-os logs")
        );
        console.log(
          chalk.dim("  Stop:      ") +
            chalk.cyan("npx realize-os stop")
        );
        console.log();
      } catch (err: any) {
        spinner.fail("Failed to start containers");
        console.error(chalk.red(err.stderr || err.message));
        process.exit(1);
      }
    });
}
