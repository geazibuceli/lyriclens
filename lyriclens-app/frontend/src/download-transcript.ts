export async function downloadTranscript(
  jobId: string,
  pipeline: string,
  format: string,
) {
  const query = new URLSearchParams({ pipeline, format });
  const response = await fetch(`/api/jobs/${jobId}/export?${query}`);
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(
      typeof data?.detail === "string"
        ? data.detail
        : `Export failed (HTTP ${response.status}). Please retry.`,
    );
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = `${jobId}-${pipeline}.${format}`;
  document.body.append(link);
  try {
    link.click();
  } finally {
    link.remove();
    // Allow the browser to begin consuming the download before releasing it.
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  }
}
