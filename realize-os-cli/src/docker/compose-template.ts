/**
 * Docker Compose template generator.
 *
 * Generates a docker-compose.yml from the EJS template with
 * project-specific configuration.
 */

import ejs from "ejs";
import { readFile } from "node:fs/promises";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const TEMPLATES_DIR = join(__dirname, "..", "..", "templates");

export interface ComposeOptions {
  projectName: string;
  port: string;
  image: string;
  withTelegram: boolean;
  withGws: boolean;
}

/**
 * Generate a docker-compose.yml from the EJS template.
 */
export async function generateComposeFile(
  options: ComposeOptions
): Promise<string> {
  const templatePath = join(TEMPLATES_DIR, "docker-compose.yml.ejs");
  const template = await readFile(templatePath, "utf-8");
  return ejs.render(template, options);
}
