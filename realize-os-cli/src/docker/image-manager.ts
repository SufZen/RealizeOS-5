/**
 * Docker image version management.
 *
 * Handles checking current/latest image versions and listing
 * running containers for the status command.
 */

import { execa } from "execa";

export interface ContainerInfo {
  name: string;
  image: string;
  status: string;
  ports: string;
}

/**
 * Get the list of running containers in a project directory.
 */
export async function getRunningContainers(
  projectDir: string
): Promise<ContainerInfo[]> {
  try {
    const { stdout } = await execa(
      "docker",
      ["compose", "ps", "--format", "json"],
      { cwd: projectDir }
    );

    if (!stdout.trim()) return [];

    // Docker Compose v2 outputs one JSON object per line
    const containers: ContainerInfo[] = [];
    for (const line of stdout.trim().split("\n")) {
      try {
        const c = JSON.parse(line);
        containers.push({
          name: c.Name || c.Service || "unknown",
          image: c.Image || "unknown",
          status: c.Status || c.State || "unknown",
          ports: c.Ports || c.Publishers || "",
        });
      } catch {
        // Skip malformed lines
      }
    }
    return containers;
  } catch {
    return [];
  }
}

/**
 * Get the current running image version (by digest or tag).
 */
export async function getCurrentImageVersion(
  projectDir: string
): Promise<string | null> {
  try {
    const { stdout } = await execa(
      "docker",
      ["compose", "images", "--format", "json"],
      { cwd: projectDir }
    );

    if (!stdout.trim()) return null;

    for (const line of stdout.trim().split("\n")) {
      try {
        const img = JSON.parse(line);
        if (img.Tag) return img.Tag;
        if (img.ID) return img.ID.slice(0, 12);
      } catch {
        // Skip
      }
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Get the latest pulled image version after `docker compose pull`.
 */
export async function getLatestImageVersion(
  projectDir: string
): Promise<string | null> {
  // After pulling, the local image tag reflects the latest
  return getCurrentImageVersion(projectDir);
}
