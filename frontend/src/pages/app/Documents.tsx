import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, apiDownload, viewDocument } from "../../api";
import { DocumentPreview } from "../../components/DocumentPreview";
import { useWorkspace } from "../../context/WorkspaceContext";
import { documentDownloadPath, documentFileType, formatFileSize, groupDocumentsByCategory, type CompanyDocument, type DocumentCategory } from "../../types";
import { IconDownload, IconEye, IconTrash } from "../../components/icons";
import { EmptyState, IconButton, matchesSearch, PageHeader, SearchField, TableSkeleton, formatDate } from "../../ui";

export default function DocumentsPage() {
  const { token, company, companies, setCompanyId, notify, hasPermission } = useWorkspace();
  const canManageOrg = hasPermission("documents.manage");
  const [rows, setRows] = useState<CompanyDocument[]>([]);
  const [categories, setCategories] = useState<DocumentCategory[]>([]);
  const [query, setQuery] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [viewing, setViewing] = useState<CompanyDocument | null>(null);

  async function load() {
    if (!company) {
      setRows([]);
      setCategories([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const [files, cats] = await Promise.all([
        api<CompanyDocument[]>(`/documents?company_id=${company.id}`, { token }),
        api<DocumentCategory[]>(`/document-categories?company_id=${company.id}`, { token }),
      ]);
      setRows(files);
      setCategories(cats);
      setError(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setQuery("");
    setCategoryFilter("");
    load().catch((err: Error) => {
      setError(err.message);
      setLoading(false);
    });
  }, [company?.id, token]);

  const visible = useMemo(() => {
    return rows.filter((row) => {
      if (categoryFilter && row.category_id !== categoryFilter) return false;
      return matchesSearch(
        query,
        row.employee_name,
        row.employee_number,
        row.filename,
        row.category,
        row.event_label,
      );
    });
  }, [rows, query, categoryFilter]);
  const groups = useMemo(() => groupDocumentsByCategory(visible, categories), [visible, categories]);
  const filtered = Boolean(query.trim() || categoryFilter);

  async function removeUpload(row: CompanyDocument) {
    if (row.source !== "UPLOAD") return;
    setBusy(true);
    try {
      await api(`/employees/${row.employee_id}/documents/${row.id}`, { method: "DELETE", token });
      setRows((current) => current.filter((item) => !(item.id === row.id && item.source === "UPLOAD")));
      notify("Document removed.");
    } catch (err) {
      notify(err instanceof Error ? err.message : "Could not delete document");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="titles-page">
      <PageHeader
        title="Documents"
        description={`Files for ${company?.name ?? "this company"}, grouped by category. Lifecycle files stay read-only. Edit categories in Settings.`}
      />
      <div className="filters">
        <SearchField value={query} onChange={setQuery} placeholder="Name, number, or file" />
        <label>
          Company
          <select value={company?.id ?? ""} onChange={(event) => setCompanyId(event.target.value)}>
            {companies.map((row) => (
              <option key={row.id} value={row.id}>{row.name}</option>
            ))}
          </select>
        </label>
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
      {error ? <p className="error">{error}</p> : null}

      {loading ? (
        <section className="card"><TableSkeleton cols={4} /></section>
      ) : groups.length === 0 ? (
        <section className="card">
          <EmptyState
            title={filtered ? "No matching documents" : "No documents yet"}
            note={
              filtered
                ? "Nothing matched those filters."
                : "Upload a file on an employee profile. Lifecycle attachments appear under Lifecycle."
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
                <col className="docs-col-employee" />
                <col />
                <col className="docs-col-type" />
                <col className="docs-col-size" />
                <col className="docs-col-uploaded" />
                <col className="docs-col-actions" />
              </colgroup>
              <thead>
                <tr>
                  <th>Employee</th>
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
                    <td data-label="Employee">
                      <Link className="row-link" to={`/app/people/${row.employee_id}`}>
                        {row.employee_name || "Employee"}
                      </Link>
                      <div className="muted">{row.employee_number}</div>
                    </td>
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
                        onClick={() => viewDocument(documentDownloadPath("", row), token, row.filename, () => setViewing(row))}
                      >
                        <IconEye />
                      </IconButton>
                      <IconButton
                        label="Download"
                        onClick={() => void apiDownload(documentDownloadPath("", row), token, row.filename)}
                      >
                        <IconDownload />
                      </IconButton>
                      {canManageOrg && row.source === "UPLOAD" ? (
                        <IconButton label="Delete" disabled={busy} onClick={() => void removeUpload(row)}>
                          <IconTrash />
                        </IconButton>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <ul className="titles-list">
              {group.rows.map((row) => (
                <li key={`${row.source}-${row.id}`} className="titles-row">
                  <div className="titles-row-top">
                    <div className="titles-main">
                      <strong>
                        <Link className="row-link" to={`/app/people/${row.employee_id}`}>
                          {row.employee_name || "Employee"}
                        </Link>
                      </strong>
                      <span>
                        {[row.filename, documentFileType(row.filename, row.content_type), formatFileSize(row.size)].filter(Boolean).join(" · ")}
                      </span>
                      {row.note || (row.source === "LIFECYCLE" && row.event_label) ? (
                        <span>{[row.note, row.source === "LIFECYCLE" ? row.event_label : null].filter(Boolean).join(" · ")}</span>
                      ) : null}
                    </div>
                  </div>
                  <div className="row-actions icons">
                    <IconButton
                      label="View"
                      onClick={() => viewDocument(documentDownloadPath("", row), token, row.filename, () => setViewing(row))}
                    >
                      <IconEye />
                    </IconButton>
                    <IconButton
                      label="Download"
                      onClick={() => void apiDownload(documentDownloadPath("", row), token, row.filename)}
                    >
                      <IconDownload />
                    </IconButton>
                    {canManageOrg && row.source === "UPLOAD" ? (
                      <IconButton label="Delete" disabled={busy} onClick={() => void removeUpload(row)}>
                        <IconTrash />
                      </IconButton>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        ))
      )}
      {viewing ? (
        <DocumentPreview
          path={documentDownloadPath("", viewing)}
          filename={viewing.filename}
          contentType={viewing.content_type}
          token={token}
          onClose={() => setViewing(null)}
        />
      ) : null}
    </div>
  );
}
