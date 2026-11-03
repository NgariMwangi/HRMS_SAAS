import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, apiDownload, apiUploadForm, viewDocument } from "../api";
import { DocumentPreview } from "./DocumentPreview";
import { documentDownloadPath, documentFileType, formatFileSize, groupDocumentsByCategory, uploadableCategories, type CompanyDocument, type DocumentCategory } from "../types";
import { IconEye, IconDownload, IconTrash } from "./icons";
import { EmptyState, IconButton, matchesSearch, SearchField, formatDate } from "../ui";

const MAX_BYTES = 50 * 1024 * 1024;

export function EmployeeDocuments({
  employeeId,
  companyId,
  token,
  apiBase,
  canManage,
  profilePath,
}: {
  employeeId: string;
  companyId: string;
  token: string;
  apiBase: string;
  canManage: boolean;
  profilePath?: (id: string) => string;
}) {
  const [rows, setRows] = useState<CompanyDocument[]>([]);
  const [categories, setCategories] = useState<DocumentCategory[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const choices = useMemo(() => uploadableCategories(categories), [categories]);
  const [categoryId, setCategoryId] = useState("");
  const [issuedOn, setIssuedOn] = useState("");
  const [expiresOn, setExpiresOn] = useState("");
  const [note, setNote] = useState("");
  const [viewing, setViewing] = useState<CompanyDocument | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [query, setQuery] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");

  useEffect(() => {
    if (!categoryId && choices[0]) setCategoryId(choices[0].id);
  }, [choices, categoryId]);

  useEffect(() => {
    Promise.all([
      api<CompanyDocument[]>(`${apiBase}/employees/${employeeId}/documents`, { token }),
      api<DocumentCategory[]>(`${apiBase}/document-categories?company_id=${companyId}`, { token }),
    ])
      .then(([files, cats]) => {
        setRows(files);
        setCategories(cats);
      })
      .catch((err: Error) => setError(err.message));
  }, [employeeId, companyId, token, apiBase]);

  const visible = useMemo(() => {
    return rows.filter((row) => {
      if (categoryFilter && row.category_id !== categoryFilter) return false;
      return matchesSearch(query, row.filename, row.category, row.note, row.event_label);
    });
  }, [rows, query, categoryFilter]);
  const groups = useMemo(() => groupDocumentsByCategory(visible, categories), [visible, categories]);
  const filtered = Boolean(query.trim() || categoryFilter);

  async function onUpload(event: FormEvent) {
    event.preventDefault();
    if (!canManage || !file || !categoryId) return;
    if (file.size > MAX_BYTES) {
      setError("Each document must be 50 MB or smaller");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const body = new FormData();
      body.append("file", file);
      body.append("category_id", categoryId);
      if (issuedOn) body.append("issued_on", issuedOn);
      if (expiresOn) body.append("expires_on", expiresOn);
      if (note.trim()) body.append("note", note.trim());
      const saved = await apiUploadForm<CompanyDocument>(`${apiBase}/employees/${employeeId}/documents`, body, token);
      setRows((current) => [saved, ...current.filter((row) => row.id !== saved.id)]);
      setFile(null);
      setIssuedOn("");
      setExpiresOn("");
      setNote("");
      setShowForm(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not upload document");
    } finally {
      setBusy(false);
    }
  }

  async function remove(row: CompanyDocument) {
    if (row.source !== "UPLOAD") return;
    setBusy(true);
    setError(null);
    try {
      await api(`${apiBase}/employees/${employeeId}/documents/${row.id}`, { method: "DELETE", token });
      setRows((current) => current.filter((item) => item.id !== row.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete document");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="filters">
        <SearchField value={query} onChange={setQuery} placeholder="File or note" />
        <label>
          Category
          <select value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}>
            <option value="">All categories</option>
            {categories.map((row) => (
              <option key={row.id} value={row.id}>{row.name}</option>
            ))}
          </select>
        </label>
      </div>
      <section className="card card-pad">
        <div className="card-head" style={{ padding: 0, border: "none" }}>
          <div>
            <h3>Documents</h3>
            <p>Uploads and read-only lifecycle files for this person.</p>
          </div>
          {canManage && !showForm ? (
            <button className="btn small" type="button" onClick={() => { setShowForm(true); setError(null); }}>
              Upload new document
            </button>
          ) : null}
        </div>
        {canManage && showForm ? (
          <form className="nested-block" onSubmit={onUpload} style={{ marginTop: 16 }}>
            {choices.length === 0 ? (
              <p className="muted" style={{ margin: 0 }}>Add an editable category in Settings before you upload a file.</p>
            ) : (
              <div className="form-grid">
                <label>
                  Category
                  <select required value={categoryId} onChange={(event) => setCategoryId(event.target.value)}>
                    {choices.map((row) => (
                      <option key={row.id} value={row.id}>{row.name}</option>
                    ))}
                  </select>
                </label>
                <label>
                  File
                  <input
                    required
                    type="file"
                    accept=".pdf,.doc,.docx,.txt,image/jpeg,image/png,image/webp"
                    onChange={(event) => {
                      const next = event.target.files?.[0] ?? null;
                      setFile(next);
                      if (next && next.size > MAX_BYTES) {
                        setError("Each document must be 50 MB or smaller");
                      } else {
                        setError(null);
                      }
                    }}
                  />
                  <span className="muted">PDF, Word, image, or text. Up to 50 MB.</span>
                </label>
                <label>Issued<input type="date" value={issuedOn} onChange={(event) => setIssuedOn(event.target.value)} /></label>
                <label>
                  Expiry
                  <input type="date" min={issuedOn || undefined} value={expiresOn} onChange={(event) => setExpiresOn(event.target.value)} />
                </label>
                <label style={{ gridColumn: "1 / -1" }}>
                  Note
                  <input value={note} onChange={(event) => setNote(event.target.value)} />
                </label>
              </div>
            )}
            <div className="actions" style={{ marginTop: 12 }}>
              {choices.length ? (
                <button className="btn small" type="submit" disabled={busy || !file}>
                  {busy ? "Uploading…" : "Upload"}
                </button>
              ) : null}
              <button
                className="btn ghost small"
                type="button"
                onClick={() => {
                  setShowForm(false);
                  setFile(null);
                  setIssuedOn("");
                  setExpiresOn("");
                  setNote("");
                  setError(null);
                }}
              >
                Cancel
              </button>
            </div>
          </form>
        ) : null}
        {error ? <p className="error">{error}</p> : null}
      </section>
      {groups.length === 0 ? (
        <section className="card">
          <EmptyState
            title={filtered ? "No matching documents" : "No documents"}
            note={
              filtered
                ? "Nothing matched those filters."
                : "Uploads and lifecycle files for this person will list here."
            }
          />
        </section>
      ) : (
        groups.map((group) => (
          <section key={group.id || group.name} className="card docs-group">
            <div className="card-head docs-category">
              <div>
                <h3>{group.name} Documents</h3>
                <p>{group.rows.length === 1 ? "1 file" : `${group.rows.length} files`}</p>
              </div>
            </div>
            <table className="docs-table">
              <colgroup>
                <col />
                <col className="docs-col-type" />
                <col className="docs-col-size" />
                <col className="docs-col-uploaded" />
                <col className="docs-col-actions" />
              </colgroup>
              <thead>
                <tr>
                  <th>File</th>
                  <th>Type</th>
                  <th>Size</th>
                  <th>Uploaded</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {group.rows.map((row) => (
                  <tr key={`${row.source}-${row.id}`}>
                    <td className="docs-file" data-label="File">
                      {row.filename}
                      {row.note ? <div className="muted">{row.note}</div> : null}
                      {row.source === "LIFECYCLE" && row.event_label ? (
                        <div className="muted">{row.event_label}</div>
                      ) : null}
                    </td>
                    <td data-label="Type">{documentFileType(row.filename, row.content_type)}</td>
                    <td data-label="Size">{formatFileSize(row.size)}</td>
                    <td data-label="Uploaded">{formatDate(row.created_at)}</td>
                    <td className="row-actions">
                      <IconButton
                        label="View"
                        onClick={() => viewDocument(documentDownloadPath(apiBase, row), token, row.filename, () => setViewing(row))}
                      >
                        <IconEye />
                      </IconButton>
                      <IconButton
                        label="Download"
                        onClick={() => void apiDownload(documentDownloadPath(apiBase, row), token, row.filename)}
                      >
                        <IconDownload />
                      </IconButton>
                      {canManage && row.source === "UPLOAD" ? (
                        <IconButton label="Delete" disabled={busy} onClick={() => void remove(row)}>
                          <IconTrash />
                        </IconButton>
                      ) : null}
                      {profilePath && row.employee_id !== employeeId ? (
                        <Link className="btn ghost small" to={profilePath(row.employee_id)}>Open</Link>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        ))
      )}
      {viewing ? (
        <DocumentPreview
          path={documentDownloadPath(apiBase, viewing)}
          filename={viewing.filename}
          contentType={viewing.content_type}
          token={token}
          onClose={() => setViewing(null)}
        />
      ) : null}
    </>
  );
}
