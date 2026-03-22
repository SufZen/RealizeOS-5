/**
 * realize-os stop — Stop the Docker containers.
 *
 * Runs `docker compose down` in the project directory.
 * Optionally removes volumes with --volumes flag.
 */

import { Command } from "commander";
import chalk from "chalk";
import ora from "ora";
import { execa } from "execa";
import { resolve } from "node:path";

export function register(program: Command) {
  program
    .command("stop")
    .description("Stop the RealizeOS Docker containers")
    .argument("[directory]", "Project directory", ".")
    .option("--volumes", "Remove named volumes (WARNING: deletes data)", false)
    .option("--remove-orphans", "Remove orphan containers", false)
    .action(async (directory: string, options) => {
      const projectDir = resolve(directory);
      const spinner = ora();

      const args = ["compose", "down"];
      if (options.volumes) args.push("--volumes");
      if (options.removeOrphans) args.push("--remove-orphans");

      if (options.volumes) {
        console.log(
          chalk.yellow("⚠️  Warning:"),
          "This will remove all data volumes. Your database and files will be deleted."
        );
      }

      spinner.start("Stopping RealizeOS...");
      try {
        await execa("docker", args, {
          cwd: projectDir,
          stdio: "pipe",
        });
        spinner.succeed("RealizeOS stopped");

        if (options.volumes) {
          console.log(chalk.dim("  Volumes have been removed."));
        }
        console.log();
      } catch (err: any) {
        spinner.fail("Failed to stop containers");
        console.error(chalk.red(err.stderr || err.message));
        process.exit(1);
      }
    });
}
