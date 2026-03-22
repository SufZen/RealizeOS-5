/**
 * Minimal YAML parser/serializer.
 *
 * Uses a simple approach for the subset of YAML we need:
 * - Top-level keys
 * - Nested objects (2-level)
 * - String, number, and array values
 *
 * For a production CLI, you'd use `js-yaml`, but we keep
 * dependencies minimal here.
 */

/**
 * Parse a simple YAML string into an object.
 * This handles the common realize-os.yaml structure.
 */
export function parse(text: string): Record<string, any> {
  try {
    // Use a simple line-based parser for our YAML subset
    const result: Record<string, any> = {};
    const lines = text.split("\n");
    let currentKey = "";
    let currentIndent = 0;
    const stack: Array<{ key: string; obj: Record<string, any>; indent: number }> = [];

    for (const rawLine of lines) {
      const line = rawLine.replace(/\r$/, "");

      // Skip comments and empty lines
      if (line.trim().startsWith("#") || line.trim() === "") continue;

      const indent = line.length - line.trimStart().length;
      const trimmed = line.trim();

      // Key-value pair
      const match = trimmed.match(/^([^:]+):\s*(.*)$/);
      if (!match) continue;

      const key = match[1].trim();
      let value: any = match[2].trim();

      // Remove inline comments
      if (value.includes(" #")) {
        value = value.split(" #")[0].trim();
      }

      // Parse value types
      if (value === "" || value === undefined) {
        // Nested object — value comes from indented lines below
        if (indent === 0) {
          result[key] = {};
          stack.length = 0;
          stack.push({ key, obj: result[key], indent });
          currentKey = key;
          currentIndent = indent;
        } else {
          // Find parent
          while (stack.length > 0 && stack[stack.length - 1].indent >= indent) {
            stack.pop();
          }
          const parent = stack.length > 0 ? stack[stack.length - 1].obj : result;
          parent[key] = {};
          stack.push({ key, obj: parent[key], indent });
        }
      } else {
        // Leaf value
        if (value.startsWith('"') && value.endsWith('"')) {
          value = value.slice(1, -1);
        } else if (value.startsWith("'") && value.endsWith("'")) {
          value = value.slice(1, -1);
        } else if (value === "true") {
          value = true;
        } else if (value === "false") {
          value = false;
        } else if (/^\d+$/.test(value)) {
          value = parseInt(value, 10);
        } else if (/^\d+\.\d+$/.test(value)) {
          value = parseFloat(value);
        } else if (value.startsWith("[") && value.endsWith("]")) {
          // Inline array
          value = value
            .slice(1, -1)
            .split(",")
            .map((s: string) => {
              s = s.trim();
              if (s.startsWith('"') && s.endsWith('"')) return s.slice(1, -1);
              if (s.startsWith("'") && s.endsWith("'")) return s.slice(1, -1);
              return s;
            });
        }

        // Find parent
        while (stack.length > 0 && stack[stack.length - 1].indent >= indent) {
          stack.pop();
        }
        const parent = stack.length > 0 ? stack[stack.length - 1].obj : result;
        parent[key] = value;
      }
    }

    return result;
  } catch {
    return {};
  }
}

/**
 * Serialize an object to a simple YAML string.
 */
export function stringify(obj: Record<string, any>, indent = 0): string {
  const prefix = "  ".repeat(indent);
  let result = "";

  for (const [key, value] of Object.entries(obj)) {
    if (value === null || value === undefined) {
      result += `${prefix}${key}:\n`;
    } else if (typeof value === "object" && !Array.isArray(value)) {
      result += `${prefix}${key}:\n`;
      result += stringify(value, indent + 1);
    } else if (Array.isArray(value)) {
      const items = value.map((v) =>
        typeof v === "string" ? `"${v}"` : String(v)
      );
      result += `${prefix}${key}: [${items.join(", ")}]\n`;
    } else if (typeof value === "string") {
      // Quote strings with special chars
      if (/[:#{}[\],&*?|>!%@`]/.test(value) || value === "") {
        result += `${prefix}${key}: "${value}"\n`;
      } else {
        result += `${prefix}${key}: ${value}\n`;
      }
    } else {
      result += `${prefix}${key}: ${value}\n`;
    }
  }

  return result;
}
