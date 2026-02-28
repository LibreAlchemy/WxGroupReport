import { appendFile, mkdir, readFile, stat } from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";
import type { Plugin } from "@opencode-ai/plugin";

type ArtifactEvent = {
  timestamp: string;
  session_id: string;
  call_id: string;
  command: string;
  report_path: string;
  sha256: string;
  size_bytes: number;
  modified_at: string;
};

const TRACE_DIR_PARTS = [".opencode", "traces"];
const TRACE_FILE_NAME = "report_artifacts.latest.jsonl";

let writeQueue: Promise<void> = Promise.resolve();

function normalizeSpace(value: string): string {
  return value.trim().replace(/\s+/g, " ");
}

function extractCommand(args: unknown): string {
  if (!args || typeof args !== "object") {
    return "";
  }
  const command = (args as { command?: unknown }).command;
  return typeof command === "string" ? command : "";
}

function isReportGenerationCommand(command: string): boolean {
  const lower = command.toLowerCase();
  return lower.includes("generate_report.py") || lower.includes("output_path=");
}

function parseOutputPath(command: string, outputText: string): string | undefined {
  const outputMatch = outputText.match(/(?:^|\n)output:\s*([^\n]+)/i);
  if (outputMatch && outputMatch[1]) {
    return outputMatch[1].trim();
  }

  const envQuoted = command.match(/OUTPUT_PATH\s*=\s*"([^"]+)"/);
  if (envQuoted && envQuoted[1]) {
    return envQuoted[1].trim();
  }

  const envSingle = command.match(/OUTPUT_PATH\s*=\s*'([^']+)'/);
  if (envSingle && envSingle[1]) {
    return envSingle[1].trim();
  }

  const envBare = command.match(/OUTPUT_PATH\s*=\s*([^\s]+)/);
  if (envBare && envBare[1]) {
    return envBare[1].trim();
  }

  return undefined;
}

async function fileSha256(filePath: string): Promise<string> {
  const content = await readFile(filePath);
  const hash = createHash("sha256");
  hash.update(content);
  return hash.digest("hex");
}

async function appendArtifact(baseDir: string, event: ArtifactEvent): Promise<void> {
  const traceDir = path.join(baseDir, ...TRACE_DIR_PARTS);
  const traceFile = path.join(traceDir, TRACE_FILE_NAME);

  const task = async (): Promise<void> => {
    await mkdir(traceDir, { recursive: true });
    await appendFile(traceFile, `${JSON.stringify(event)}\n`, "utf8");
  };

  writeQueue = writeQueue.then(task).catch(() => undefined);
  await writeQueue;
}

const ReportArtifactLoggerPlugin: Plugin = async (ctx) => {
  return {
    "tool.execute.after": async (input, output) => {
      try {
        if (input.tool !== "bash") {
          return;
        }

        const command = extractCommand(input.args);
        if (!command || !isReportGenerationCommand(command)) {
          return;
        }

        const outputText = typeof output.output === "string" ? output.output : "";
        const reportPathRaw = parseOutputPath(command, outputText);
        if (!reportPathRaw) {
          return;
        }

        const reportPath = path.isAbsolute(reportPathRaw)
          ? reportPathRaw
          : path.join(ctx.directory, reportPathRaw);
        const fileInfo = await stat(reportPath);
        const digest = await fileSha256(reportPath);

        await appendArtifact(ctx.directory, {
          timestamp: new Date().toISOString(),
          session_id: input.sessionID,
          call_id: input.callID,
          command: normalizeSpace(command).slice(0, 500),
          report_path: reportPath,
          sha256: digest,
          size_bytes: fileInfo.size,
          modified_at: fileInfo.mtime.toISOString(),
        });
      } catch {
      }
    },
  };
};

export default ReportArtifactLoggerPlugin;
