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
import { parse, stringify } from "../src/utils/yaml.js";
import { generateComposeFile } from "../src/docker/compose-template.js";
import { generateEnvFile } from "../src/docker/env-template.js";

// ---------------------------------------------------------------------------
// YAML Parser
// ---------------------------------------------------------------------------

describe("YAML Parser", () => {
  it("parses simple key-value pairs", () => {
    const result = parse("name: My Project\nversion: 5");
    expect(result.name).toBe("My Project");
    expect(result.version).toBe(5);
  });

  it("parses nested objects", () => {
    const yaml = `systems:
  my-venture:
    name: My Venture
    directory: systems/my-venture`;
    const result = parse(yaml);
    expect(result.systems).toBeDefined();
    expect(result.systems["my-venture"]).toBeDefined();
    expect(result.systems["my-venture"].name).toBe("My Venture");
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
      image: "ghcr.io/sufzen/realizeos:latest",
      withTelegram: false,
      withGws: false,
    });

    expect(result).toContain("services:");
    expect(result).toContain("api:");
    expect(result).toContain("ghcr.io/sufzen/realizeos:latest");
    expect(result).toContain("8080");
    expect(result).toContain("realize-data");
    expect(result).toContain("realize-shared");
  });

  it("includes telegram service when enabled", async () => {
    const result = await generateComposeFile({
      projectName: "test",
      port: "8080",
      image: "ghcr.io/sufzen/realizeos:latest",
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
      image: "ghcr.io/sufzen/realizeos:latest",
      withTelegram: false,
      withGws: false,
    });

    expect(result).not.toContain("telegram:");
  });

  it("includes GWS build arg when enabled", async () => {
    const result = await generateComposeFile({
      projectName: "test",
      port: "8080",
      image: "ghcr.io/sufzen/realizeos:latest",
      withTelegram: false,
      withGws: true,
    });

    expect(result).toContain('INSTALL_GWS: "true"');
  });

  it("uses custom port", async () => {
    const result = await generateComposeFile({
      projectName: "test",
      port: "9090",
      image: "ghcr.io/sufzen/realizeos:latest",
      withTelegram: false,
      withGws: false,
    });

    expect(result).toContain("9090");
  });

  it("includes health check", async () => {
    const result = await generateComposeFile({
      projectName: "test",
      port: "8080",
      image: "ghcr.io/sufzen/realizeos:latest",
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
      image: "ghcr.io/sufzen/realizeos:latest",
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
