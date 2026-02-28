import { appendFile, mkdir } from "node:fs/promises";
import path from "node:path";
import type { Plugin } from "@opencode-ai/plugin";

type TraceEvent = {
  timestamp: string;
  event_type: "tool" | "thought";
  payload: Record<string, unknown>;
};

type TokenUsage = {
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
  source: "explicit";
};

const TRACE_DIR_PARTS = [".opencode", "traces"];
const TRACE_FILE_NAME = "latest.jsonl";

const TOKEN_KEY_MAP: Record<string, keyof Omit<TokenUsage, "source">> = {
  input_tokens: "input_tokens",
  output_tokens: "output_tokens",
  total_tokens: "total_tokens",
  inputtokens: "input_tokens",
  outputtokens: "output_tokens",
  totaltokens: "total_tokens",
  prompt_tokens: "input_tokens",
  completion_tokens: "output_tokens",
};

let writeQueue: Promise<void> = Promise.resolve();
let traceEnabled = true;

const REPORT_MARKERS = [
  "generate_report.py",
  "generate-report/scripts/generate_report.py",
];

function envEnabled(name: string, fallback: boolean): boolean {
  const raw = process.env[name];
  if (raw === undefined) {
    return fallback;
  }
  const normalized = raw.trim().toLowerCase();
  if (["1", "true", "yes", "y", "on"].includes(normalized)) {
    return true;
  }
  if (["0", "false", "no", "n", "off"].includes(normalized)) {
    return false;
  }
  return fallback;
}

const AUTO_STOP_AFTER_REPORT = envEnabled(
  "TRAJECTORY_TRACE_AUTO_STOP_AFTER_REPORT",
  true,
);

function safeClone<T>(value: T): T | string {
  try {
    return JSON.parse(JSON.stringify(value)) as T;
  } catch {
    return String(value);
  }
}

function partsToThought(parts: unknown[]): string {
  const texts: string[] = [];
  for (const part of parts) {
    if (!part || typeof part !== "object") {
      continue;
    }
    const maybeText = (part as { text?: unknown }).text;
    if (typeof maybeText === "string" && maybeText.trim()) {
      texts.push(maybeText.trim());
    }
  }
  return texts.join("\n").slice(0, 4000);
}

function asTokenNumber(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value) && value >= 0) {
    return Math.floor(value);
  }
  return undefined;
}

function extractTokenUsage(value: unknown): TokenUsage | undefined {
  const usage: Omit<TokenUsage, "source"> = {};
  const visited = new WeakSet<object>();

  function walk(node: unknown): void {
    if (!node || typeof node !== "object") {
      return;
    }
    if (visited.has(node)) {
      return;
    }
    visited.add(node);

    if (Array.isArray(node)) {
      for (const item of node) {
        walk(item);
      }
      return;
    }

    const record = node as Record<string, unknown>;
    for (const [rawKey, rawValue] of Object.entries(record)) {
      const key = rawKey.toLowerCase();
      const mapped = TOKEN_KEY_MAP[key];
      const numeric = asTokenNumber(rawValue);
      if (mapped && numeric !== undefined) {
        usage[mapped] = numeric;
      }
      walk(rawValue);
    }
  }

  walk(value);

  if (
    usage.input_tokens === undefined &&
    usage.output_tokens === undefined &&
    usage.total_tokens === undefined
  ) {
    return undefined;
  }

  if (
    usage.total_tokens === undefined &&
    usage.input_tokens !== undefined &&
    usage.output_tokens !== undefined
  ) {
    usage.total_tokens = usage.input_tokens + usage.output_tokens;
  }

  return {
    ...usage,
    source: "explicit",
  };
}

function getEventName(event: unknown): string {
  if (!event || typeof event !== "object") {
    return "unknown";
  }
  const record = event as Record<string, unknown>;
  for (const key of ["type", "name", "event", "kind", "id"]) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return "unknown";
}

function extractCommandFromArgs(value: unknown): string {
  if (!value || typeof value !== "object") {
    return "";
  }
  const command = (value as Record<string, unknown>).command;
  return typeof command === "string" ? command : "";
}

function commandContainsAny(command: string, markers: string[]): boolean {
  if (!command) {
    return false;
  }
  const lower = command.toLowerCase();
  return markers.some((marker) => lower.includes(marker.toLowerCase()));
}

function isSuccessfulToolResult(value: unknown): boolean {
  if (!value || typeof value !== "object") {
    return false;
  }
  const metadata = (value as Record<string, unknown>).metadata;
  if (!metadata || typeof metadata !== "object") {
    return false;
  }
  const exit = (metadata as Record<string, unknown>).exit;
  return typeof exit === "number" && Number.isFinite(exit) && exit === 0;
}

async function appendTrace(baseDir: string, event: TraceEvent): Promise<void> {
  const traceDir = path.join(baseDir, ...TRACE_DIR_PARTS);
  const traceFile = path.join(traceDir, TRACE_FILE_NAME);

  const task = async (): Promise<void> => {
    await mkdir(traceDir, { recursive: true });
    await appendFile(traceFile, `${JSON.stringify(event)}\n`, "utf8");
  };

  writeQueue = writeQueue.then(task).catch(() => undefined);
  await writeQueue;
}

const TrajectoryLoggerPlugin: Plugin = async (ctx) => {
  return {
    event: async (input) => {
      try {
        if (!traceEnabled) {
          return;
        }
        const tokenUsage = extractTokenUsage(input.event);
        if (!tokenUsage) {
          return;
        }
        await appendTrace(ctx.directory, {
          timestamp: new Date().toISOString(),
          event_type: "thought",
          payload: {
            kind: "model_usage",
            event_name: getEventName(input.event),
            token_usage: tokenUsage,
          },
        });
      } catch {
      }
    },
    "tool.execute.before": async (input, output) => {
      try {
        if (!traceEnabled) {
          return;
        }

        await appendTrace(ctx.directory, {
          timestamp: new Date().toISOString(),
          event_type: "tool",
          payload: {
            phase: "before",
            tool: input.tool,
            session_id: input.sessionID,
            call_id: input.callID,
            args: safeClone(output.args),
          },
        });
      } catch {
      }
    },
    "tool.execute.after": async (input, output) => {
      try {
        if (!traceEnabled) {
          return;
        }

        await appendTrace(ctx.directory, {
          timestamp: new Date().toISOString(),
          event_type: "tool",
          payload: {
            phase: "after",
            tool: input.tool,
            session_id: input.sessionID,
            call_id: input.callID,
            args: safeClone(input.args),
            result: {
              title: output.title,
              output: output.output,
              metadata: safeClone(output.metadata),
            },
          },
        });

        const toolName = String(input.tool ?? "").toLowerCase();
        const command = extractCommandFromArgs(input.args);
        if (
          AUTO_STOP_AFTER_REPORT &&
          toolName === "bash" &&
          commandContainsAny(command, REPORT_MARKERS) &&
          isSuccessfulToolResult(output)
        ) {
          traceEnabled = false;
        }
      } catch {
      }
    },
    "chat.message": async (input, output) => {
      try {
        if (!traceEnabled) {
          return;
        }
        const tokenUsage = extractTokenUsage({
          input,
          output,
        });
        await appendTrace(ctx.directory, {
          timestamp: new Date().toISOString(),
          event_type: "thought",
          payload: {
            session_id: input.sessionID,
            agent: input.agent,
            message_id: input.messageID,
            variant: input.variant,
            thought: partsToThought(output.parts ?? []),
            message: safeClone(output.message),
            token_usage: tokenUsage,
          },
        });
      } catch {
      }
    },
  };
};

export default TrajectoryLoggerPlugin;
