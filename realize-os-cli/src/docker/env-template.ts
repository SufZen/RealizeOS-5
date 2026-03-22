/**
 * Environment file template generator.
 *
 * Generates a .env file from the EJS template.
 */

import ejs from "ejs";
import { readFile } from "node:fs/promises";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const TEMPLATES_DIR = join(__dirname, "..", "..", "templates");

export interface EnvOptions {
  port: string;
  withGws: boolean;
}

/**
 * Generate a .env file from the EJS template.
 */
export async function generateEnvFile(options: EnvOptions): Promise<string> {
  const templatePath = join(TEMPLATES_DIR, ".env.ejs");
  const template = await readFile(templatePath, "utf-8");
  return ejs.render(template, options);
}
