/**
 * realize-os logs — Tail Docker container logs.
 *
 * Wraps `docker compose logs` with sensible defaults.
 */

import { Command } from "commander";
import chalk from "chalk";
import { execa } from "execa";
import { resolve } from "node:path";

export function register(program: Command) {
  program
    .command("logs")
    .description("Tail RealizeOS container logs")
    .argument("[directory]", "Project directory", ".")
    .option("-f, --follow", "Follow log output (default: true)", true)
    .option("-n, --tail <lines>", "Number of recent lines to show", "100")
    .option("--service <name>", "Show logs for a specific service")
    .option("--no-follow", "Don't follow — just print recent logs")
    .action(async (directory: string, options) => {
      const projectDir = resolve(directory);

      const args = ["compose", "logs"];

      if (options.follow) args.push("-f");
      args.push("--tail", options.tail);
      if (options.service) args.push(options.service);

      console.log(
        chalk.dim("Tailing logs") +
          (options.service ? chalk.dim(` for ${options.service}`) : "") +
          chalk.dim("... Press Ctrl+C to stop")
      );
      console.log();

      try {
        await execa("docker", args, {
          cwd: projectDir,
          stdio: "inherit", // Stream directly to terminal
        });
      } catch (err: any) {
        if (err.signal === "SIGINT") {
          // User pressed Ctrl+C — this is expected
          console.log();
          return;
        }
        console.error(chalk.red("Error:"), err.message);
        process.exit(1);
      }
    });
}
