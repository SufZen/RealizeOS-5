/**
 * Minimal YAML parser/serializer for RealizeOS config files.
 *
 * This intentionally supports the subset we write:
 * - top-level scalar keys
 * - nested objects
 * - inline scalar arrays
 * - arrays of objects, especially `systems:`
 */

function parseScalar(rawValue: string): any {
  let value: any = rawValue.trim();

  if (value.includes(" #")) {
    value = value.split(" #")[0].trim();
  }

  if (value.startsWith('"') && value.endsWith('"')) {
    return value.slice(1, -1);
  }
  if (value.startsWith("'") && value.endsWith("'")) {
    return value.slice(1, -1);
  }
  if (value === "true") {
    return true;
  }
  if (value === "false") {
    return false;
  }
  if (/^\d+$/.test(value)) {
    return parseInt(value, 10);
  }
  if (/^\d+\.\d+$/.test(value)) {
    return parseFloat(value);
  }
  if (value.startsWith("[") && value.endsWith("]")) {
    const inner = value.slice(1, -1).trim();
    if (!inner) {
      return [];
    }
    return inner.split(",").map((item: string) => parseScalar(item.trim()));
  }

  return value;
}

function parseKeyValue(trimmed: string): { key: string; value: string } | null {
  const match = trimmed.match(/^([^:]+):\s*(.*)$/);
  if (!match) {
    return null;
  }
  return { key: match[1].trim(), value: match[2].trim() };
}

function parseSystemsBlock(block: string[]): any {
  const hasListItems = block.some((line) => line.trimStart().startsWith("- "));
  if (!hasListItems) {
    return parseIndentedObject(block, 2);
  }

  const systems: Record<string, any>[] = [];
  let current: Record<string, any> | null = null;
  let currentNestedKey: string | null = null;

  for (const rawLine of block) {
    const line = rawLine.replace(/\r$/, "");
    if (line.trim() === "" || line.trim().startsWith("#")) {
      continue;
    }

    const indent = line.length - line.trimStart().length;
    const trimmed = line.trim();

    if (indent === 2 && trimmed.startsWith("- ")) {
      current = {};
      systems.push(current);
      currentNestedKey = null;
      const firstPair = parseKeyValue(trimmed.slice(2));
      if (firstPair) {
        current[firstPair.key] = parseScalar(firstPair.value);
      }
      continue;
    }

    if (!current) {
      continue;
    }

    const pair = parseKeyValue(trimmed);
    if (!pair) {
      continue;
    }

    if (indent === 4) {
      if (pair.value === "") {
        current[pair.key] = {};
        currentNestedKey = pair.key;
      } else {
        current[pair.key] = parseScalar(pair.value);
        currentNestedKey = null;
      }
    } else if (indent === 6 && currentNestedKey) {
      current[currentNestedKey][pair.key] = parseScalar(pair.value);
    }
  }

  return systems;
}

function parseIndentedObject(lines: string[], baseIndent = 0): Record<string, any> {
  const result: Record<string, any> = {};
  const stack: Array<{ obj: Record<string, any>; indent: number }> = [{ obj: result, indent: baseIndent - 2 }];

  for (const rawLine of lines) {
    const line = rawLine.replace(/\r$/, "");
    if (line.trim() === "" || line.trim().startsWith("#")) {
      continue;
    }

    const indent = line.length - line.trimStart().length;
    const pair = parseKeyValue(line.trim());
    if (!pair) {
      continue;
    }

    while (stack.length > 0 && stack[stack.length - 1].indent >= indent) {
      stack.pop();
    }

    const parent = stack.length > 0 ? stack[stack.length - 1].obj : result;
    if (pair.value === "") {
      parent[pair.key] = {};
      stack.push({ obj: parent[pair.key], indent });
    } else {
      parent[pair.key] = parseScalar(pair.value);
    }
  }

  return result;
}

export function parse(text: string): Record<string, any> {
  try {
    const result: Record<string, any> = {};
    const lines = text.split("\n");
    let index = 0;

    while (index < lines.length) {
      const rawLine = lines[index];
      const line = rawLine.replace(/\r$/, "");

      if (line.trim() === "" || line.trim().startsWith("#")) {
        index += 1;
        continue;
      }

      const indent = line.length - line.trimStart().length;
      if (indent !== 0) {
        index += 1;
        continue;
      }

      const pair = parseKeyValue(line.trim());
      if (!pair) {
        index += 1;
        continue;
      }

      if (pair.value !== "") {
        result[pair.key] = parseScalar(pair.value);
        index += 1;
        continue;
      }

      const block: string[] = [];
      index += 1;
      while (index < lines.length) {
        const nextLine = lines[index];
        const nextIndent = nextLine.length - nextLine.trimStart().length;
        if (nextLine.trim() !== "" && !nextLine.trim().startsWith("#") && nextIndent === 0) {
          break;
        }
        block.push(nextLine);
        index += 1;
      }

      result[pair.key] = pair.key === "systems" ? parseSystemsBlock(block) : parseIndentedObject(block, 2);
    }

    return result;
  } catch {
    return {};
  }
}

function formatScalar(value: any): string {
  if (typeof value === "string") {
    if (/[:#{}[\],&*?|>!%@`]/.test(value) || value === "") {
      return `"${value.replace(/"/g, '\\"')}"`;
    }
    return value;
  }
  return String(value);
}

function formatArrayItem(value: any): string {
  if (typeof value === "string") {
    return `"${value.replace(/"/g, '\\"')}"`;
  }
  return formatScalar(value);
}

export function stringify(obj: Record<string, any>, indent = 0): string {
  const prefix = "  ".repeat(indent);
  let result = "";

  for (const [key, value] of Object.entries(obj)) {
    if (value === null || value === undefined) {
      result += `${prefix}${key}:\n`;
    } else if (Array.isArray(value)) {
      if (value.every((item) => item === null || typeof item !== "object")) {
        result += `${prefix}${key}: [${value.map(formatArrayItem).join(", ")}]\n`;
      } else {
        result += `${prefix}${key}:\n`;
        for (const item of value) {
          const entries = Object.entries(item as Record<string, any>);
          const [firstKey, firstValue] = entries[0];
          result += `${prefix}  - ${firstKey}: ${formatScalar(firstValue)}\n`;
          for (const [childKey, childValue] of entries.slice(1)) {
            if (childValue && typeof childValue === "object" && !Array.isArray(childValue)) {
              result += `${prefix}    ${childKey}:\n`;
              result += stringify(childValue as Record<string, any>, indent + 3);
            } else if (Array.isArray(childValue)) {
              result += `${prefix}    ${childKey}: [${childValue.map(formatArrayItem).join(", ")}]\n`;
            } else {
              result += `${prefix}    ${childKey}: ${formatScalar(childValue)}\n`;
            }
          }
        }
      }
    } else if (typeof value === "object") {
      result += `${prefix}${key}:\n`;
      result += stringify(value as Record<string, any>, indent + 1);
    } else {
      result += `${prefix}${key}: ${formatScalar(value)}\n`;
    }
  }

  return result;
}
