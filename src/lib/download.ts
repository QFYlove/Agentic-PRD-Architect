export interface MarkdownDownload {
  filename: string;
  blob: Blob;
}

export function createMarkdownDownload(
  runId: string,
  version: number,
  content: string,
): MarkdownDownload {
  const safeRunId = runId.replace(/[^a-zA-Z0-9-]/g, "").slice(0, 36);
  return {
    filename: `agentic-prd-${safeRunId}-v${version}.md`,
    blob: new Blob([content], { type: "text/markdown;charset=utf-8" }),
  };
}

export function triggerMarkdownDownload(download: MarkdownDownload): void {
  const url = URL.createObjectURL(download.blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = download.filename;
  link.click();
  URL.revokeObjectURL(url);
}
