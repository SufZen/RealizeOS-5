/**
 * Tests for the RealizeOS CLI.
 *
 * Covers:
 * - YAML parser/serializer
 * - Docker compose template generation
 * - Environment template generation
 * - CLI help output
 */

import { describe, it, expect } from "vitest";
import { mkdtemp, readFile, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { parse, stringify } from "../src/utils/yaml.js";
import { generateComposeFile } from "../src/docker/compose-template.js";
import { generateEnvFile } from "../src/docker/env-template.js";
import { FABRIC_DIRS, validateVentureKey, writeVentureTemplate } from "../src/venture-template.js";

// ---------------------------------------------------------------------------
// YAML Parser
// ---------------------------------------------------------------------------

describe("YAML Parser", () => {
  it("parses simple key-value pairs", () => {
    const result = parse("name: My Project\nversion: 5");
    expect(result.name).toBe("My Project");
    expect(result.version).toBe(5);
  });

  it("parses legacy nested systems objects", () => {
    const yaml = `systems:
  my-venture:
    name: My Venture
    directory: systems/my-venture`;
    const result = parse(yaml);
    expect(result.systems).toBeDefined();
    expect(result.systems["my-venture"]).toBeDefined();
    expect(result.systems["my-venture"].name).toBe("My Venture");
  });

  it("parses V5 systems lists", () => {
    const yaml = `systems:
  - key: my-venture
    name: My Venture
    directory: systems/my-venture
    routing:
      content: [writer, reviewer]`;
    const result = parse(yaml);
    expect(result.systems).toHaveLength(1);
    expect(result.systems[0].key).toBe("my-venture");
    expect(result.systems[0].routing.content).toEqual(["writer", "reviewer"]);
  });

  it("parses boolean values", () => {
    const result = parse("enabled: true\ndisabled: false");
    expect(result.enabled).toBe(true);
    expect(result.disabled).toBe(false);
  });

  it("parses quoted strings", () => {
    const result = parse('name: "Hello World"');
    expect(result.name).toBe("Hello World");
  });

  it("parses inline arrays", () => {
    const result = parse('skills: ["skill1", "skill2"]');
    expect(result.skills).toEqual(["skill1", "skill2"]);
  });

  it("skips comments", () => {
    const result = parse("# This is a comment\nname: Test");
    expect(result.name).toBe("Test");
  });

  it("handles empty input", () => {
    const result = parse("");
    expect(result).toEqual({});
  });

  it("handles malformed input gracefully", () => {
    const result = parse("not valid yaml at all {{{}}}");
    expect(result).toBeDefined();
  });
});

// ---------------------------------------------------------------------------
// YAML Serializer
// ---------------------------------------------------------------------------

describe("YAML Serializer", () => {
  it("serializes simple key-value pairs", () => {
    const result = stringify({ name: "Test", version: 5 });
    expect(result).toContain("name: Test");
    expect(result).toContain("version: 5");
  });

  it("serializes nested objects", () => {
    const result = stringify({
      systems: { "my-venture": { name: "Test" } },
    });
    expect(result).toContain("systems:");
    expect(result).toContain("  my-venture:");
    expect(result).toContain("    name: Test");
  });

  it("serializes arrays of objects as YAML lists", () => {
    const result = stringify({
      systems: [{ key: "my-venture", name: "My Venture", directory: "systems/my-venture" }],
    });
    expect(result).toContain("systems:");
    expect(result).toContain("  - key: my-venture");
    expect(result).toContain("    directory: systems/my-venture");
  });

  it("serializes arrays as inline", () => {
    const result = stringify({ skills: ["a", "b"] });
    expect(result).toContain('skills: ["a", "b"]');
  });

  it("serializes boolean values", () => {
    const result = stringify({ enabled: true, disabled: false });
    expect(result).toContain("enabled: true");
    expect(result).toContain("disabled: false");
  });

  it("quotes strings with special characters", () => {
    const result = stringify({ url: "http://localhost:8080" });
    expect(result).toContain('"http://localhost:8080"');
  });
});

// ---------------------------------------------------------------------------
// Docker Compose Template
// ---------------------------------------------------------------------------

describe("Docker Compose Template", () => {
  it("generates valid compose file", async () => {
    const result = await generateComposeFile({
      projectName: "test-project",
      port: "8080",
      image: "ghcr.io/sufzen/realizeos-5:latest",
      withTelegram: false,
      withGws: false,
    });

    expect(result).toContain("services:");
    expect(result).toContain("api:");
    expect(result).toContain("ghcr.io/sufzen/realizeos-5:latest");
    expect(result).toContain("8080");
    expect(result).toContain("realize-data");
    expect(result).toContain("realize-shared");
  });

  it("includes telegram service when enabled", async () => {
    const result = await generateComposeFile({
      projectName: "test",
      port: "8080",
      image: "ghcr.io/sufzen/realizeos-5:latest",
      withTelegram: true,
      withGws: false,
    });

    expect(result).toContain("telegram:");
    expect(result).toContain("realizeos-telegram");
    expect(result).toContain("python cli.py bot");
  });

  it("excludes telegram service when disabled", async () => {
    const result = await generateComposeFile({
      projectName: "test",
      port: "8080",
      image: "ghcr.io/sufzen/realizeos-5:latest",
      withTelegram: false,
      withGws: false,
    });

    expect(result).not.toContain("telegram:");
  });

  it("includes GWS build arg when enabled", async () => {
    const result = await generateComposeFile({
      projectName: "test",
      port: "8080",
      image: "ghcr.io/sufzen/realizeos-5:latest",
      withTelegram: false,
      withGws: true,
    });

    expect(result).toContain('INSTALL_GWS: "true"');
  });

  it("uses custom port", async () => {
    const result = await generateComposeFile({
      projectName: "test",
      port: "9090",
      image: "ghcr.io/sufzen/realizeos-5:latest",
      withTelegram: false,
      withGws: false,
    });

    expect(result).toContain("9090");
  });

  it("includes health check", async () => {
    const result = await generateComposeFile({
      projectName: "test",
      port: "8080",
      image: "ghcr.io/sufzen/realizeos-5:latest",
      withTelegram: false,
      withGws: false,
    });

    expect(result).toContain("healthcheck");
    expect(result).toContain("/health");
  });

  it("includes named volumes section", async () => {
    const result = await generateComposeFile({
      projectName: "test",
      port: "8080",
      image: "ghcr.io/sufzen/realizeos-5:latest",
      withTelegram: false,
      withGws: false,
    });

    expect(result).toContain("volumes:");
    expect(result).toContain("realize-data:");
    expect(result).toContain("realize-shared:");
  });
});

// ---------------------------------------------------------------------------
// Environment Template
// ---------------------------------------------------------------------------

describe("Environment Template", () => {
  it("generates valid env file", async () => {
    const result = await generateEnvFile({
      port: "8080",
      withGws: false,
    });

    expect(result).toContain("ANTHROPIC_API_KEY=");
    expect(result).toContain("GOOGLE_AI_API_KEY=");
    expect(result).toContain("REALIZE_PORT=8080");
  });

  it("uses custom port", async () => {
    const result = await generateEnvFile({
      port: "9090",
      withGws: false,
    });

    expect(result).toContain("REALIZE_PORT=9090");
  });

  it("includes GWS keys when enabled", async () => {
    const result = await generateEnvFile({
      port: "8080",
      withGws: true,
    });

    expect(result).toContain("GOOGLE_CLIENT_ID=");
    expect(result).toContain("GOOGLE_CLIENT_SECRET=");
    // Should not be commented out
    expect(result).not.toContain("# GOOGLE_CLIENT_ID=");
  });

  it("comments GWS keys when disabled", async () => {
    const result = await generateEnvFile({
      port: "8080",
      withGws: false,
    });

    expect(result).toContain("# GOOGLE_CLIENT_ID=");
  });

  it("includes rate limits", async () => {
    const result = await generateEnvFile({
      port: "8080",
      withGws: false,
    });

    expect(result).toContain("RATE_LIMIT_PER_MINUTE=");
    expect(result).toContain("COST_LIMIT_PER_HOUR_USD=");
  });
});

// ---------------------------------------------------------------------------
// Venture Template
// ---------------------------------------------------------------------------

describe("Venture Template", () => {
  it("accepts safe user-defined venture folder slugs", () => {
    expect(validateVentureKey("my-saas")).toBe("my-saas");
    expect(validateVentureKey("client-work-2")).toBe("client-work-2");
  });

  it("rejects unsafe venture folder slugs", () => {
    expect(() => validateVentureKey("My SaaS")).toThrow();
    expect(() => validateVentureKey("../escape")).toThrow();
    expect(() => validateVentureKey("client_work")).toThrow();
    expect(() => validateVentureKey("con")).toThrow();
  });

  it("writes the full V5 FABRIC starter structure", async () => {
    const projectDir = await mkdtemp(join(tmpdir(), "realize-cli-test-"));
    try {
      await writeVentureTemplate(projectDir, "my-saas", "My SaaS");

      for (const dir of FABRIC_DIRS) {
        const info = await stat(join(projectDir, "systems", "my-saas", dir));
        expect(info.isDirectory()).toBe(true);
      }

      const identity = await readFile(
        join(projectDir, "systems", "my-saas", "F-foundations", "venture-identity.md"),
        "utf-8"
      );
      expect(identity).toContain("My SaaS");

      const weeklyReview = await stat(
        join(projectDir, "systems", "my-saas", "R-routines", "skills", "weekly-review.yaml")
      );
      expect(weeklyReview.isFile()).toBe(true);
    } finally {
      await rm(projectDir, { recursive: true, force: true });
    }
  });
});
