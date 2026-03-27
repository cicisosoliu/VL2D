import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  API_BASE,
  createExport,
  exportUrl,
  fileUrl,
  listJobs,
  listSamples,
  type ExportRecord,
  type Job,
  type Sample,
  type SamplePage,
  type SampleReviewStatus,
  updateSample,
  uploadAndQueue,
} from "./lib/api";
import { StatusBadge } from "./components/StatusBadge";

const SUPPORTED_VIDEO_ACCEPT = ".mp4,.mov,video/mp4,video/quicktime";
const SUPPORTED_VIDEO_EXTENSIONS = [".mp4", ".mov"];
const REVIEW_FILTERS: Array<{ label: string; value: "" | SampleReviewStatus }> = [
  { label: "All", value: "" },
  { label: "Pending", value: "pending_review" },
  { label: "Approved", value: "approved" },
  { label: "Rejected", value: "rejected" },
];

function isSupportedVideoFile(file: File) {
  const lowercaseName = file.name.toLowerCase();
  return SUPPORTED_VIDEO_EXTENSIONS.some((extension) => lowercaseName.endsWith(extension));
}

function hasDegradedOCR(sample: Sample) {
  return (
    sample.flags.includes("ocr_provider_degraded") ||
    sample.frame_observations.some((observation) => Boolean(observation.metadata_json?.degraded))
  );
}

function isPlaceholderOCRText(value: string) {
  return value.trim().startsWith("UNVERIFIED ");
}

function visibleSampleText(sample: Sample, value: string) {
  if (hasDegradedOCR(sample) && isPlaceholderOCRText(value)) {
    return "";
  }
  return value;
}

function formatMs(value: number) {
  const seconds = Math.floor(value / 1000);
  const ms = value % 1000;
  return `${seconds}.${ms.toString().padStart(3, "0")}s`;
}

function SampleCard({
  sample,
  onSave,
}: {
  sample: Sample;
  onSave: (sample: Sample, reviewStatus: string, finalText: string) => void;
}) {
  const initialText = visibleSampleText(sample, sample.final_text || sample.raw_text);
  const [draftText, setDraftText] = useState(initialText);
  const visibleRawText = visibleSampleText(sample, sample.raw_text);
  const degradedOCR = hasDegradedOCR(sample);

  useEffect(() => {
    setDraftText(visibleSampleText(sample, sample.final_text || sample.raw_text));
  }, [sample.final_text, sample.raw_text, sample.id, sample.flags, sample.frame_observations]);

  const previewImage = useMemo(() => {
    const first = [...sample.frame_observations].sort((a, b) => a.frame_time_ms - b.frame_time_ms)[0];
    return fileUrl(first?.roi_path ?? first?.frame_path);
  }, [sample.frame_observations]);

  return (
    <article className="sample-card">
      <div className="sample-card-header">
        <div>
          <h3>Segment {sample.segment_index + 1}</h3>
          <p>
            {formatMs(sample.start_ms)} - {formatMs(sample.end_ms)} · {formatMs(sample.duration_ms)}
          </p>
        </div>
        <StatusBadge status={sample.review_status} />
      </div>

      <div className="sample-grid">
        <div className="sample-media">
          <audio controls src={fileUrl(sample.audio_path) ?? undefined} />
          {previewImage ? <img src={previewImage} alt={`Segment ${sample.segment_index + 1}`} /> : <div className="empty-image">No frame preview</div>}
        </div>

        <div className="sample-editor">
          {degradedOCR ? (
            <div className="warning-box">
              OCR provider is degraded or unavailable for this sample. The current text field does not contain verified OCR output.
            </div>
          ) : null}
          <label>
            Editable Text
            <textarea value={draftText} onChange={(event) => setDraftText(event.target.value)} />
          </label>
          <div className="sample-meta">
            <strong>OCR Raw</strong>
            <pre>{visibleRawText || "No OCR text detected"}</pre>
          </div>
          {sample.flags.length > 0 ? <div className="flags">Flags: {sample.flags.join(", ")}</div> : null}
          <div className="actions">
            <button onClick={() => onSave(sample, "pending_review", draftText)}>Save</button>
            <button className="approve" onClick={() => onSave(sample, "approved", draftText)}>
              Approve
            </button>
            <button className="reject" onClick={() => onSave(sample, "rejected", draftText)}>
              Reject
            </button>
          </div>
        </div>
      </div>
    </article>
  );
}

export default function App() {
  const queryClient = useQueryClient();
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [uploadValidationError, setUploadValidationError] = useState<string | null>(null);
  const [lastExport, setLastExport] = useState<ExportRecord | null>(null);
  const [samplePage, setSamplePage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [reviewFilter, setReviewFilter] = useState<"" | SampleReviewStatus>("pending_review");

  const jobsQuery = useQuery({
    queryKey: ["jobs"],
    queryFn: listJobs,
    refetchInterval: 3000,
  });

  const samplesQuery = useQuery({
    queryKey: ["samples", selectedJobId, samplePage, pageSize, reviewFilter],
    queryFn: () => listSamples(selectedJobId!, samplePage, pageSize, reviewFilter),
    enabled: Boolean(selectedJobId),
    refetchInterval: 3000,
  });

  useEffect(() => {
    if (!selectedJobId && jobsQuery.data && jobsQuery.data.length > 0) {
      setSelectedJobId(jobsQuery.data[0].id);
    }
  }, [jobsQuery.data, selectedJobId]);

  useEffect(() => {
    setSamplePage(1);
  }, [selectedJobId, reviewFilter]);

  useEffect(() => {
    const totalPages = samplesQuery.data?.total_pages ?? 0;
    if (totalPages > 0 && samplePage > totalPages) {
      setSamplePage(totalPages);
    }
  }, [samplePage, samplesQuery.data?.total_pages]);

  const uploadMutation = useMutation({
    mutationFn: uploadAndQueue,
    onSuccess: (job) => {
      setSelectedJobId(job.id);
      setPendingFile(null);
      setUploadValidationError(null);
      void queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });

  const sampleMutation = useMutation({
    mutationFn: ({ sample, reviewStatus, finalText }: { sample: Sample; reviewStatus: string; finalText: string }) =>
      updateSample(sample.id, { review_status: reviewStatus, final_text: finalText }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["samples", selectedJobId] });
      await queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
  });

  const exportMutation = useMutation({
    mutationFn: (jobId: string) => createExport(jobId),
    onSuccess: (record) => setLastExport(record),
  });

  const selectedJob: Job | undefined = jobsQuery.data?.find((job) => job.id === selectedJobId);
  const samplePageData: SamplePage | undefined = samplesQuery.data;
  const sampleItems = samplePageData?.items ?? [];
  const totalSamples = samplePageData?.total ?? 0;
  const totalPages = samplePageData?.total_pages ?? 0;
  const pageStart = totalSamples === 0 ? 0 : (samplePage - 1) * pageSize + 1;
  const pageEnd = totalSamples === 0 ? 0 : Math.min(samplePage * pageSize, totalSamples);
  const activeFilterLabel = REVIEW_FILTERS.find((filter) => filter.value === reviewFilter)?.label ?? "All";

  return (
    <main className="app-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">VL2D Review Console</p>
          <h1>Turn Chinese-subtitle video into a reviewable speech dataset.</h1>
          <p className="hero-copy">
            Local-first processing with SQLite, a single worker, and direct sample approval before export.
          </p>
        </div>
        <div className="hero-note">
          <div>API: {API_BASE}</div>
          <div>Worker mode: single-process polling</div>
        </div>
      </header>

      <section className="panel upload-panel">
        <div>
          <h2>Upload Video</h2>
          <p>Select an MP4 or MOV video file, upload it to the backend, and enqueue a processing job.</p>
        </div>
        <div className="upload-controls">
          <input
            type="file"
            accept={SUPPORTED_VIDEO_ACCEPT}
            onChange={(event) => {
              const file = event.target.files?.[0] ?? null;
              if (file && !isSupportedVideoFile(file)) {
                setPendingFile(null);
                setUploadValidationError("Unsupported video format. VL2D accepts .mp4 and .mov files.");
                return;
              }
              setPendingFile(file);
              setUploadValidationError(null);
            }}
          />
          <button disabled={!pendingFile || uploadMutation.isPending} onClick={() => pendingFile && uploadMutation.mutate(pendingFile)}>
            {uploadMutation.isPending ? "Uploading..." : "Upload & Queue"}
          </button>
        </div>
        {uploadValidationError ? <p className="error">{uploadValidationError}</p> : null}
        {uploadMutation.error ? <p className="error">{String(uploadMutation.error)}</p> : null}
      </section>

      <div className="workspace">
        <section className="panel jobs-panel">
          <div className="section-heading">
            <h2>Jobs</h2>
            <button className="secondary" onClick={() => queryClient.invalidateQueries({ queryKey: ["jobs"] })}>
              Refresh
            </button>
          </div>
          <div className="jobs-list">
            {jobsQuery.data?.map((job) => (
              <button
                key={job.id}
                className={`job-row ${selectedJobId === job.id ? "selected" : ""}`}
                onClick={() => {
                  setSelectedJobId(job.id);
                  setLastExport(null);
                }}
              >
                <div className="job-row-top">
                  <strong>{job.id.slice(0, 8)}</strong>
                  <StatusBadge status={job.status} />
                </div>
                <div className="job-row-meta">
                  <span>{job.progress_step ?? "waiting"}</span>
                  <span>{job.progress_percent ?? 0}%</span>
                </div>
              </button>
            ))}
            {!jobsQuery.data?.length ? <div className="empty-state">No jobs yet.</div> : null}
          </div>
        </section>

        <section className="panel review-panel">
          <div className="section-heading">
            <div>
              <h2>Review Samples</h2>
              {selectedJob ? (
                <p>
                  <StatusBadge status={selectedJob.status} /> {selectedJob.progress_message ?? "Idle"}
                </p>
              ) : (
                <p>Select a job to inspect samples.</p>
              )}
            </div>
            <div className="toolbar">
              <div className="pager-summary">
                <span>
                  {totalSamples > 0 ? `Showing ${pageStart}-${pageEnd} of ${totalSamples}` : "No samples loaded"}
                </span>
                <label className="page-size-select">
                  Status
                  <select
                    value={reviewFilter}
                    onChange={(event) => setReviewFilter(event.target.value as "" | SampleReviewStatus)}
                  >
                    {REVIEW_FILTERS.map((filter) => (
                      <option key={filter.label} value={filter.value}>
                        {filter.label}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="page-size-select">
                  Per page
                  <select
                    value={pageSize}
                    onChange={(event) => {
                      setPageSize(Number(event.target.value));
                      setSamplePage(1);
                    }}
                  >
                    {[10, 20, 50].map((size) => (
                      <option key={size} value={size}>
                        {size}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <button
                className="secondary"
                disabled={!selectedJobId || exportMutation.isPending}
                onClick={() => selectedJobId && exportMutation.mutate(selectedJobId)}
              >
                {exportMutation.isPending ? "Exporting..." : "Export Approved"}
              </button>
              {lastExport ? (
                <a className="download-link" href={exportUrl(lastExport.id)}>
                  Download ZIP
                </a>
              ) : null}
            </div>
          </div>

          {selectedJob?.error_message ? <div className="error-box">{selectedJob.error_message}</div> : null}

          {selectedJobId ? (
            <div className="pagination-bar">
              <div>
                Page {samplePage} {totalPages > 0 ? `of ${totalPages}` : ""}
              </div>
              <div className="pagination-actions">
                <button
                  className="secondary"
                  disabled={samplePage <= 1}
                  onClick={() => setSamplePage((current) => Math.max(1, current - 1))}
                >
                  Previous
                </button>
                <button
                  className="secondary"
                  disabled={totalPages === 0 || samplePage >= totalPages}
                  onClick={() => setSamplePage((current) => current + 1)}
                >
                  Next
                </button>
              </div>
            </div>
          ) : null}

          <div className="samples-list">
            {sampleItems.map((sample) => (
              <SampleCard
                key={sample.id}
                sample={sample}
                onSave={(nextSample, reviewStatus, finalText) => sampleMutation.mutate({ sample: nextSample, reviewStatus, finalText })}
              />
            ))}
            {selectedJobId && sampleItems.length === 0 ? (
              <div className="empty-state">
                {reviewFilter
                  ? `No ${activeFilterLabel.toLowerCase()} samples on this job yet. If processing is still running, this list will refresh automatically.`
                  : "No samples yet. If the job is still running, this list will refresh automatically."}
              </div>
            ) : null}
            {!selectedJobId ? <div className="empty-state">Upload or select a job to start review.</div> : null}
          </div>

          {selectedJobId && totalPages > 1 ? (
            <div className="pagination-bar pagination-bar-bottom">
              <div>
                Page {samplePage} of {totalPages}
              </div>
              <div className="pagination-actions">
                <button
                  className="secondary"
                  disabled={samplePage <= 1}
                  onClick={() => setSamplePage((current) => Math.max(1, current - 1))}
                >
                  Previous
                </button>
                <button
                  className="secondary"
                  disabled={samplePage >= totalPages}
                  onClick={() => setSamplePage((current) => current + 1)}
                >
                  Next
                </button>
              </div>
            </div>
          ) : null}
        </section>
      </div>
    </main>
  );
}
