export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

export type Job = {
  id: string;
  video_id: string;
  status: string;
  progress_step: string | null;
  progress_message: string | null;
  progress_percent: number | null;
  error_message: string | null;
  stats: Record<string, unknown>;
  provider_stack: Record<string, string>;
  created_at: string;
  finished_at: string | null;
};

export type FrameObservation = {
  id: string;
  frame_path: string;
  roi_path: string | null;
  frame_time_ms: number;
  text: string;
  confidence: number;
  metadata_json?: Record<string, unknown>;
};

export type Sample = {
  id: string;
  job_id: string;
  video_id: string;
  segment_index: number;
  start_ms: number;
  end_ms: number;
  duration_ms: number;
  audio_path: string;
  raw_text: string;
  final_text: string;
  review_status: string;
  confidence_summary: Record<string, unknown>;
  flags: string[];
  frame_observations: FrameObservation[];
};

export type SamplePage = {
  items: Sample[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export type SampleReviewStatus = "pending_review" | "approved" | "rejected";

export type ExportRecord = {
  id: string;
  job_id: string;
  status: string;
  artifact_path: string | null;
  item_count: number;
  error_message: string | null;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function normalizeSamplePage(payload: SamplePage | Sample[], page: number, pageSize: number): SamplePage {
  if (Array.isArray(payload)) {
    const total = payload.length;
    const start = Math.max(0, (page - 1) * pageSize);
    const end = start + pageSize;
    return {
      items: payload.slice(start, end),
      total,
      page,
      page_size: pageSize,
      total_pages: total > 0 ? Math.ceil(total / pageSize) : 0,
    };
  }
  return payload;
}

export async function uploadAndQueue(file: File): Promise<Job> {
  const formData = new FormData();
  formData.append("file", file);
  const video = await request<{ id: string }>("/api/videos", {
    method: "POST",
    body: formData,
  });
  return request<Job>("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ video_id: video.id }),
  });
}

export function listJobs(): Promise<Job[]> {
  return request<Job[]>("/api/jobs");
}

export function listSamples(
  jobId: string,
  page: number,
  pageSize: number,
  reviewStatus?: SampleReviewStatus | "",
): Promise<SamplePage> {
  const params = new URLSearchParams({
    job_id: jobId,
    page: String(page),
    page_size: String(pageSize),
  });
  if (reviewStatus) {
    params.set("review_status", reviewStatus);
  }
  return request<SamplePage | Sample[]>(`/api/samples?${params.toString()}`).then((payload) =>
    normalizeSamplePage(payload, page, pageSize),
  );
}

export function updateSample(sampleId: string, payload: Partial<Pick<Sample, "final_text" | "review_status">>) {
  return request<Sample>(`/api/samples/${sampleId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function createExport(jobId: string) {
  return request<ExportRecord>("/api/exports", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_id: jobId }),
  });
}

export function fileUrl(relativePath: string | null | undefined): string | null {
  if (!relativePath) {
    return null;
  }
  return `${API_BASE}/files/${relativePath}`;
}

export function exportUrl(exportId: string): string {
  return `${API_BASE}/api/exports/${exportId}/download`;
}
