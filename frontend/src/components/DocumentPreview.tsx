import { useEffect, useState } from "react";
import { apiDownload, apiFileBlob } from "../api";
import { isIos } from "../pwa";

export function DocumentPreview({
  path,
  filename,
  contentType,
  token,
  onClose,
}: {
  path: string;
  filename: string;
  contentType?: string | null;
  token: string;
  onClose: () => void;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [type, setType] = useState(contentType ?? "");
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const phonePdf = isIos();

  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  useEffect(() => {
    let objectUrl = "";
    setLoading(true);
    setError(null);
    setText(null);
    apiFileBlob(path, token, filename)
      .then(async (file) => {
        objectUrl = file.url;
        setUrl(file.url);
        setType(file.type || contentType || "");
        if ((file.type || contentType || "").startsWith("text/")) {
          setText(await file.blob.text());
        }
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [path, token, contentType, filename]);

  const kind = previewKind(type, filename);

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="modal-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="document-preview-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="modal-head">
          <div>
            <h2 id="document-preview-title">{filename}</h2>
            <p className="muted" style={{ margin: 0 }}>
              {kind === "other" || (kind === "pdf" && phonePdf)
                ? "Open the file to view it on this phone."
                : "Document preview"}
            </p>
          </div>
          <div className="actions">
            {url ? (
              <a className="btn ghost small" href={url} target="_blank" rel="noopener">
                Open
              </a>
            ) : null}
            <button
              className="btn ghost small"
              type="button"
              onClick={() => void apiDownload(path, token, filename)}
            >
              Download
            </button>
            <button className="btn small" type="button" onClick={onClose}>Close</button>
          </div>
        </div>
        <div className="modal-body">
          {loading ? <p className="muted">Opening…</p> : null}
          {error ? <p className="error">{error}</p> : null}
          {!loading && !error && kind === "image" && url ? (
            <img className="doc-preview-image" src={url} alt={filename} />
          ) : null}
          {!loading && !error && kind === "pdf" && url && !phonePdf ? (
            <iframe className="doc-preview-frame" title={filename} src={url} />
          ) : null}
          {!loading && !error && kind === "pdf" && url && phonePdf ? (
            <div className="doc-preview-fallback">
              <p>Safari cannot show this PDF in the page. Open it to view or share it.</p>
              <a className="btn small" href={url} target="_blank" rel="noopener">Open PDF</a>
            </div>
          ) : null}
          {!loading && !error && kind === "text" ? (
            <pre className="doc-preview-text">{text ?? ""}</pre>
          ) : null}
          {!loading && !error && kind === "other" ? (
            <div className="doc-preview-fallback">
              <p>This file type cannot be previewed here. Open it to view it on your phone.</p>
              {url ? (
                <a className="btn small" href={url} target="_blank" rel="noopener">Open file</a>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function previewKind(type: string, filename: string): "image" | "pdf" | "text" | "other" {
  const lower = (type || "").toLowerCase();
  const name = filename.toLowerCase();
  if (lower.startsWith("image/") || /\.(png|jpe?g|webp|gif)$/.test(name)) return "image";
  if (lower.includes("pdf") || name.endsWith(".pdf")) return "pdf";
  if (lower.startsWith("text/") || name.endsWith(".txt")) return "text";
  return "other";
}
