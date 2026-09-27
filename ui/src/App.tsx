import { useEffect, useMemo, useRef, useState } from "react";
import type { AuditReport, Finding, ProjectManifest, ProjectPolicy, Severity, SystemProfile, WorkflowSpec, WorkflowValidationReceipt } from "./types";

type View = "overview" | "guardrails" | "graph" | "workflows" | "system" | "capsule";

const modalityLabels: Record<string, string> = {
  bulk_rna: "Bulk RNA",
  mirna: "miRNA",
  single_cell: "Single cell",
  spatial: "Spatial",
  somatic_variant: "Variants",
  copy_number: "Copy number",
  proteomics: "Proteomics",
  pathology: "Pathology",
  clinical: "Clinical"
};

const modalityGlyphs: Record<string, string> = {
  bulk_rna: "RNA",
  mirna: "miR",
  single_cell: "SC",
  spatial: "SP",
  somatic_variant: "VAR",
  copy_number: "CNV",
  proteomics: "PRO",
  pathology: "WSI",
  clinical: "CLN"
};

const nav: Array<{ id: View; label: string; icon: string }> = [
  { id: "overview", label: "Research cockpit", icon: "◈" },
  { id: "guardrails", label: "OncoGuard", icon: "⚠" },
  { id: "graph", label: "OncoGraph", icon: "⌘" },
  { id: "workflows", label: "Workflow fabric", icon: "⇝" },
  { id: "system", label: "System core", icon: "⬡" },
  { id: "capsule", label: "Research capsule", icon: "▣" }
];

const severityOrder: Severity[] = ["blocker", "high", "medium", "low", "info"];

function StatCard({ label, value, detail }: { label: string; value: string | number; detail: string }) {
  return (
    <article className="stat-card">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  );
}

function ScoreRing({ score, status }: { score: number; status: string }) {
  const angle = Math.max(0, Math.min(100, score)) * 3.6;
  return (
    <div className="score-wrap">
      <div className="score-ring" style={{ "--score-angle": `${angle}deg` } as React.CSSProperties}>
        <div>
          <strong>{score}</strong>
          <span>/ 100</span>
        </div>
      </div>
      <div>
        <p className={`status status-${status}`}>{status.replaceAll("_", " ")}</p>
        <h3>Scientific readiness</h3>
        <p className="muted">A blocker stops execution. Scores summarize implemented checks; they do not certify validity.</p>
      </div>
    </div>
  );
}

function FindingCard({ finding, compact = false }: { finding: Finding; compact?: boolean }) {
  const [open, setOpen] = useState(!compact && finding.severity === "blocker");
  return (
    <article className={`finding finding-${finding.severity}`}>
      <button className="finding-head" onClick={() => setOpen((value) => !value)}>
        <span className="severity-dot" />
        <span className="finding-code">{finding.code}</span>
        <span className="finding-copy">
          <strong>{finding.title}</strong>
          <small>{finding.message}</small>
        </span>
        <span className={`severity-pill ${finding.severity}`}>{finding.severity}</span>
        <span className="chevron">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div className="finding-body">
          {finding.evidence.length > 0 && (
            <div>
              <h4>Evidence</h4>
              <ul>{finding.evidence.map((item) => <li key={item}>{item}</li>)}</ul>
            </div>
          )}
          <div>
            <h4>Required action</h4>
            <p>{finding.remediation}</p>
          </div>
        </div>
      )}
    </article>
  );
}

function Overview({ manifest, report, goTo }: { manifest: ProjectManifest; report: AuditReport; goTo: (view: View) => void }) {
  const modalities = useMemo(() => {
    const counts = new Map<string, number>();
    manifest.assays.forEach((assay) => counts.set(assay.modality, (counts.get(assay.modality) ?? 0) + 1));
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [manifest]);
  const urgent = report.findings.filter((finding) => finding.severity === "blocker" || finding.severity === "high").slice(0, 4);

  return (
    <>
      <section className="hero panel">
        <div className="hero-copy">
          <span className="eyebrow">ACTIVE RESEARCH QUESTION</span>
          <h1>{manifest.objective.question}</h1>
          <div className="hero-meta">
            <span>{manifest.disease_context}</span><i />
            <span>{manifest.objective.analysis_type}</span><i />
            <span className="sensitivity">{manifest.data_sensitivity} data</span>
          </div>
        </div>
        <div className="hero-mark" aria-hidden="true"><img src="/melinoe-mark.png" alt="" /></div>
      </section>

      <section className="stats-grid">
        <StatCard label="Patients" value={report.summary.patient_count} detail="linked research units" />
        <StatCard label="Specimens" value={report.summary.specimen_count} detail="tumour and reference material" />
        <StatCard label="Assays" value={report.summary.assay_count} detail="registered data objects" />
        <StatCard label="Modalities" value={report.summary.modality_count} detail="connected evidence layers" />
      </section>

      <section className="overview-grid">
        <article className="panel readiness-card">
          <div className="section-title"><span>ONCOGUARD</span><button onClick={() => goTo("guardrails")}>Inspect all findings →</button></div>
          <ScoreRing score={report.summary.score} status={report.summary.status} />
          <div className="severity-counts">
            {severityOrder.slice(0, 4).map((severity) => (
              <div key={severity}><span className={`severity-dot ${severity}`} /><strong>{report.summary.finding_counts[severity]}</strong><small>{severity}</small></div>
            ))}
          </div>
        </article>

        <article className="panel modality-card">
          <div className="section-title"><span>CONNECTED EVIDENCE</span><button onClick={() => goTo("graph")}>Open graph →</button></div>
          <div className="modality-orbit">
            <div className="orbit-core"><span>ONCO</span><strong>GRAPH</strong></div>
            {modalities.map(([modality, count], index) => (
              <div className={`modality-node node-${index + 1}`} key={modality}>
                <b>{modalityGlyphs[modality] ?? "DAT"}</b>
                <span>{modalityLabels[modality] ?? modality}</span>
                <small>{count}</small>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="panel urgent-panel">
        <div className="section-title"><span>EXECUTION GATE</span><b>{urgent.length} priority findings shown</b></div>
        <div className="finding-list">{urgent.map((finding) => <FindingCard finding={finding} compact key={finding.code} />)}</div>
      </section>
    </>
  );
}

function Guardrails({ report }: { report: AuditReport }) {
  const [filter, setFilter] = useState<Severity | "all">("all");
  const findings = filter === "all" ? report.findings : report.findings.filter((item) => item.severity === filter);
  return (
    <section>
      <div className="page-heading">
        <div><span className="eyebrow">DETERMINISTIC SCIENTIFIC SAFETY</span><h1>OncoGuard audit</h1><p>Every finding is traceable to a declared rule. No language model can waive a blocker.</p></div>
        <ScoreRing score={report.summary.score} status={report.summary.status} />
      </div>
      <div className="filter-row">
        {(["all", ...severityOrder] as const).map((severity) => (
          <button className={filter === severity ? "active" : ""} onClick={() => setFilter(severity)} key={severity}>
            {severity} {severity !== "all" && <span>{report.summary.finding_counts[severity]}</span>}
          </button>
        ))}
      </div>
      <div className="finding-list full">{findings.map((finding, index) => <FindingCard finding={finding} key={`${finding.code}-${index}`} />)}</div>
    </section>
  );
}

function Graph({ manifest }: { manifest: ProjectManifest }) {
  const assaysBySpecimen = useMemo(() => {
    const map = new Map<string, typeof manifest.assays>();
    manifest.assays.forEach((assay) => map.set(assay.specimen_id, [...(map.get(assay.specimen_id) ?? []), assay]));
    return map;
  }, [manifest]);
  return (
    <section>
      <div className="page-heading simple"><div><span className="eyebrow">PATIENT → SPECIMEN → ASSAY</span><h1>OncoGraph explorer</h1><p>The graph makes biological dependence visible before modelling begins.</p></div></div>
      <div className="graph-layout">
        <aside className="panel graph-legend">
          <h3>Graph inventory</h3>
          <p><b>{manifest.patients.length}</b> patient nodes</p>
          <p><b>{manifest.specimens.length}</b> specimen nodes</p>
          <p><b>{manifest.assays.length}</b> assay nodes</p>
          <hr />
          <small>Orphaned links remain visible instead of being silently dropped.</small>
        </aside>
        <div className="panel graph-canvas">
          {manifest.patients.map((patient) => {
            const specimens = manifest.specimens.filter((item) => item.patient_id === patient.id);
            return (
              <div className="patient-lane" key={patient.id}>
                <div className="graph-patient"><span>{patient.id}</span><small>{patient.diagnosis ?? "Unspecified"}</small></div>
                <div className="connector" />
                <div className="lane-specimens">
                  {specimens.map((specimen) => (
                    <div className="specimen-chain" key={specimen.id}>
                      <div className="graph-specimen"><span>{specimen.id}</span><small>{specimen.tissue_type}</small></div>
                      <div className="assay-stack">
                        {(assaysBySpecimen.get(specimen.id) ?? []).map((assay) => (
                          <div className="graph-assay" key={assay.id}><b>{modalityGlyphs[assay.modality] ?? "DAT"}</b><span>{assay.id}</span></div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
          {manifest.specimens.filter((item) => !manifest.patients.some((patient) => patient.id === item.patient_id)).map((specimen) => (
            <div className="patient-lane orphan" key={specimen.id}>
              <div className="graph-patient"><span>{specimen.patient_id}</span><small>Unknown patient</small></div>
              <div className="connector" />
              <div className="specimen-chain">
                <div className="graph-specimen"><span>{specimen.id}</span><small>{specimen.tissue_type}</small></div>
                <div className="assay-stack">
                  {(assaysBySpecimen.get(specimen.id) ?? []).map((assay) => (
                    <div className="graph-assay" key={assay.id}><b>{modalityGlyphs[assay.modality] ?? "DAT"}</b><span>{assay.id}</span></div>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

const workflowCards = [
  ["bulk-transcriptomics", "bulk_rna"],
  ["single-cell-tumour-atlas", "single_cell"],
  ["somatic-landscape", "somatic_variant"],
  ["digital-pathology", "pathology"],
  ["proteomic-response", "proteomics"],
  ["multimodal-integration", "clinical"]
];

function Workflows({ blocked, workflows }: { blocked: boolean; workflows: WorkflowSpec[] }) {
  const [evidence, setEvidence] = useState<WorkflowValidationReceipt | null>(null);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);

  async function inspectEvidence(spec: WorkflowSpec) {
    if (!spec.validation) return;
    try {
      setEvidenceError(null);
      const response = await fetch(spec.validation.evidence_path);
      if (!response.ok) throw new Error(`Evidence unavailable (${response.status})`);
      setEvidence(await response.json() as WorkflowValidationReceipt);
    } catch (caught) {
      setEvidenceError(caught instanceof Error ? caught.message : "Evidence unavailable");
    }
  }

  return (
    <section>
      <div className="page-heading simple"><div><span className="eyebrow">VERSION-PINNED ANALYSIS</span><h1>Workflow fabric</h1><p>One research question, multiple evidence layers, explicit execution gates.</p></div></div>
      {blocked && <div className="gate-banner"><b>Execution locked</b><span>Resolve OncoGuard blockers before a workflow can consume this project.</span></div>}
      <div className="workflow-grid">
        {workflowCards.map(([id, modality], index) => {
          const spec = workflows.find((item) => item.id === id);
          const validation = spec?.maturity === "validated" ? spec.validation : undefined;
          return (
            <article className={`workflow-card panel ${validation ? "workflow-validated" : ""}`} key={id}>
              <div className="workflow-number">0{index + 1}</div><div className="workflow-icon">{modalityGlyphs[modality]}</div>
              <h3>{spec?.title ?? id.replaceAll("-", " ")}</h3><p>{spec?.summary ?? "Workflow contract unavailable"}</p>
              {validation && <div className="validation-line"><b>VALIDATED</b><span>{validation.independent_cohorts} cohorts · {validation.patients} patients · {validation.events} events</span></div>}
              <div className="workflow-foot"><span>{validation ? `v${spec?.version} · reference passed` : "Design contract"}</span><button disabled={!validation} onClick={() => spec && void inspectEvidence(spec)}>{validation ? "Evidence" : blocked ? "Locked" : "Validation pending"}</button></div>
            </article>
          );
        })}
      </div>
      {evidenceError && <div className="gate-banner"><b>Evidence error</b><span>{evidenceError}</span></div>}
      {evidence && <article className="panel evidence-panel">
        <div><span className="eyebrow">EXECUTED GOLD STUDY</span><h2>Five-cohort PDAC reference benchmark</h2><p>{evidence.claim_boundary}</p></div>
        <div className="evidence-stats"><div><b>{evidence.cohorts}</b><span>independent cohorts</span></div><div><b>{evidence.patients}</b><span>eligible patients</span></div><div><b>{evidence.events}</b><span>survival events</span></div><div><b>{evidence.metrics.filter((item) => item.passed).length}/{evidence.metrics.length}</b><span>reference checks passed</span></div></div>
        <small>{evidence.execution_engine} · validated {new Date(evidence.validated_at).toLocaleDateString()}</small>
      </article>}
    </section>
  );
}

function formatBytes(value: number): string {
  const gib = value / 1024 / 1024 / 1024;
  return `${gib.toFixed(gib >= 100 ? 0 : 1)} GiB`;
}

function Platform({ system, policy }: { system: SystemProfile | null; policy: ProjectPolicy | null }) {
  const capability = (name: string) => system?.capabilities[name];
  const state = (ready: boolean | undefined) => ready ? "ready" : "unavailable";
  return (
    <section>
      <div className="page-heading simple"><div><span className="eyebrow">OS-ENFORCED RESEARCH BOUNDARY</span><h1>System core</h1><p>These are detected guarantees on this machine—not marketing switches.</p></div></div>
      {!system && <div className="gate-banner"><b>Inspecting host</b><span>Reading compute and isolation capabilities…</span></div>}
      {system && <>
        <div className="capability-grid">
          <article className="panel capability-card"><span className={`cap-state ${state(system.encrypted_vault_ready)}`}>{state(system.encrypted_vault_ready)}</span><b>Project Vault</b><p>Encrypted file contents and names. Plaintext exists only in an unlocked FUSE workspace.</p><small>{capability("vault")?.version ?? "Vault engine not installed"}</small></article>
          <article className="panel capability-card"><span className={`cap-state ${state(system.offline_execution_ready)}`}>{state(system.offline_execution_ready)}</span><b>Network containment</b><p>Analysis runs with a read-only host, project-scoped writes, ephemeral temporary storage, and no network.</p><small>{capability("sandbox")?.version ?? "Sandbox engine unavailable"}</small></article>
          <article className="panel capability-card"><span className="cap-state ready">active</span><b>Research state</b><p>Manifest, audit, environment, policy, hardware, random seed, and data checksums freeze into one record.</p><small>melinoe-research-state/1.0</small></article>
          <article className="panel capability-card"><span className="cap-state ready">active</span><b>Tamper-evident ledger</b><p>Workflow and vault events form a hash chain that exposes edits, removal, reordering, or corruption.</p><small>SHA-256 chained JSONL</small></article>
          <article className="panel capability-card"><span className="cap-state ready">active</span><b>Signed workflow locks</b><p>Only validated contracts with evidence, immutable OCI digests, and offline-verifiable signatures can become executable.</p><small>{capability("signing")?.version ?? "Ed25519 signing unavailable"}</small></article>
          <article className="panel capability-card"><span className="cap-state ready">active</span><b>Offline knowledge packs</b><p>Versioned databases travel as signed, checksummed archives and install into a content-addressed local registry.</p><small>melinoe-knowledge-pack/1.0</small></article>
          <article className="panel capability-card"><span className="cap-state ready">active</span><b>Safe checkpoints</b><p>Project manifests, audits, and research state roll back atomically while source data remain untouched.</p><small>automatic pre-restore backup</small></article>
          <article className="panel capability-card"><span className="cap-state ready">portable</span><b>Local → HPC handoff</b><p>Signed workflow, state, Slurm profile, container checksum, and RO-Crate metadata travel as one gated bundle.</p><small>{capability("apptainer")?.available && capability("slurm")?.available ? "Local HPC tools detected" : "Bundle creation ready · cluster executes"}</small></article>
        </div>
        <div className="system-layout">
          <article className="panel machine-card">
            <div className="section-title"><span>COMPUTE PROFILE</span><b>{system.compute.recommended_tier.replaceAll("_", " ")}</b></div>
            <div className="machine-row"><span>Processor</span><b>{system.compute.cpu_model}</b></div>
            <div className="machine-row"><span>Logical CPUs</span><b>{system.compute.logical_cpus}</b></div>
            <div className="machine-row"><span>Memory</span><b>{formatBytes(system.compute.memory_bytes)}</b></div>
            <div className="machine-row"><span>Free project storage</span><b>{formatBytes(system.compute.disk_free_bytes)}</b></div>
            <div className="machine-row"><span>Accelerator</span><b>{system.compute.gpu ?? "CPU execution"}</b></div>
            <div className="machine-row"><span>Kernel</span><b>{system.kernel}</b></div>
          </article>
          <article className="panel policy-card">
            <div className="section-title"><span>ACTIVE DATA POLICY</span><b>{policy?.sensitivity ?? "unknown"}</b></div>
            <div className="policy-rule"><span>Encryption</span><b>{policy?.encryption_required ? "Required" : "Recommended"}</b></div>
            <div className="policy-rule"><span>Workflow network</span><b>{policy?.network.replaceAll("_", " ") ?? "—"}</b></div>
            <div className="policy-rule"><span>Export boundary</span><b>{policy?.export.replaceAll("_", " ") ?? "—"}</b></div>
            <div className="policy-rule"><span>Source data in capsule</span><b>{policy?.source_data_in_capsules ? "Allowed" : "Never"}</b></div>
            <div className="policy-rule"><span>Locked labels during training</span><b>{policy?.locked_test_labels_hidden_during_training ? "Hidden" : "Visible"}</b></div>
            <p className="policy-note">Policy is derived from the manifest sensitivity and consumed by execution planning. It is not user-interface decoration.</p>
          </article>
        </div>
        <article className="panel trust-chain">
          <div className="section-title"><span>ENFORCEMENT CHAIN</span><b>6 live</b></div>
          <div className="trust-steps"><div><b>01</b><span>OncoGraph</span><small>Declare biological units</small></div><i>→</i><div><b>02</b><span>OncoGuard</span><small>Block invalid designs</small></div><i>→</i><div><b>03</b><span>Project Vault</span><small>Protect data at rest</small></div><i>→</i><div><b>04</b><span>Isolation</span><small>Contain execution</small></div><i>→</i><div><b>05</b><span>Signed handoff</span><small>Bind digest and state</small></div><i>→</i><div><b>06</b><span>Validated workflow</span><small>1 gold study live</small></div></div>
        </article>
      </>}
    </section>
  );
}

function Capsule({ manifest, report, download }: { manifest: ProjectManifest; report: AuditReport; download: () => Promise<void> }) {
  return (
    <section>
      <div className="page-heading simple"><div><span className="eyebrow">PORTABLE RESEARCH RECORD</span><h1>Research Capsule</h1><p>Export the project state without silently copying source patient data.</p></div></div>
      <div className="capsule-layout">
        <article className="panel capsule-card">
          <div className="capsule-visual"><div className="capsule-disc"><img src="/melinoe-mark.png" alt="" /></div><div className="capsule-lines" /></div>
          <div className="capsule-copy"><span className="eyebrow">CAPSULE PREVIEW</span><h2>{manifest.title}</h2><p>{manifest.objective.question}</p>
            <ul><li>Canonical manifest</li><li>OncoGuard audit</li><li>Research-state snapshot</li><li>Integrity index</li><li>Execution provenance</li><li>Human-readable summary</li></ul>
            <button className="primary-action" onClick={download}>Export capsule <span>↓</span></button>
          </div>
        </article>
        <aside className="panel capsule-audit"><h3>Export state</h3><div><span>Status</span><b className={`status-text ${report.summary.status}`}>{report.summary.status.replaceAll("_", " ")}</b></div><div><span>Readiness</span><b>{report.summary.score}/100</b></div><div><span>Engine</span><b>OncoGuard {report.engine_version}</b></div><div><span>Source data</span><b>Not included</b></div><p>Blocked projects can still be exported for repair and review. The blocked state remains embedded in the capsule.</p></aside>
      </div>
    </section>
  );
}

export default function App() {
  const [manifest, setManifest] = useState<ProjectManifest | null>(null);
  const [report, setReport] = useState<AuditReport | null>(null);
  const [system, setSystem] = useState<SystemProfile | null>(null);
  const [policy, setPolicy] = useState<ProjectPolicy | null>(null);
  const [workflows, setWorkflows] = useState<WorkflowSpec[]>([]);
  const [view, setView] = useState<View>("overview");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  async function runAudit(project: ProjectManifest) {
    const response = await fetch("/api/audit", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(project) });
    if (!response.ok) throw new Error(`Audit failed (${response.status})`);
    setReport(await response.json());
  }

  async function loadDemo() {
    try {
      setLoading(true); setError(null);
      const response = await fetch("/api/demo");
      if (!response.ok) throw new Error(`Demo failed to load (${response.status})`);
      const project = await response.json() as ProjectManifest;
      setManifest(project);
      const policyResponse = await fetch(`/api/policy/${project.data_sensitivity}`);
      if (!policyResponse.ok) throw new Error(`Policy failed to load (${policyResponse.status})`);
      setPolicy(await policyResponse.json());
      await runAudit(project);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Unknown error"); }
    finally { setLoading(false); }
  }

  useEffect(() => {
    void loadDemo();
    void fetch("/api/system").then((response) => {
      if (!response.ok) throw new Error(`System inspection failed (${response.status})`);
      return response.json() as Promise<SystemProfile>;
    }).then(setSystem).catch(() => setSystem(null));
    void fetch("/api/workflows").then((response) => {
      if (!response.ok) throw new Error(`Workflow registry failed (${response.status})`);
      return response.json() as Promise<WorkflowSpec[]>;
    }).then(setWorkflows).catch(() => setWorkflows([]));
  }, []);

  async function importManifest(file: File) {
    try {
      const project = JSON.parse(await file.text()) as ProjectManifest;
      setManifest(project); setLoading(true); setError(null);
      const policyResponse = await fetch(`/api/policy/${project.data_sensitivity}`);
      if (!policyResponse.ok) throw new Error(`Policy failed to load (${policyResponse.status})`);
      setPolicy(await policyResponse.json());
      await runAudit(project); setView("overview");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Could not import manifest"); }
    finally { setLoading(false); if (fileInput.current) fileInput.current.value = ""; }
  }

  async function downloadCapsule() {
    if (!manifest) return;
    const response = await fetch("/api/capsule", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(manifest) });
    if (!response.ok) { setError(`Capsule export failed (${response.status})`); return; }
    const url = URL.createObjectURL(await response.blob());
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = `${manifest.project_id}-research-capsule.zip`; anchor.click();
    URL.revokeObjectURL(url);
  }

  if (loading) return <div className="loading-screen"><img className="loading-mark" src="/melinoe-mark.png" alt="Melinoë" /><span>Mapping evidence</span></div>;
  if (error || !manifest || !report) return <div className="error-screen"><h1>Melinoë could not start</h1><p>{error ?? "Project state unavailable"}</p><button onClick={loadDemo}>Retry demo</button></div>;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><img className="brand-mark" src="/melinoe-mark.png" alt="Melinoë emblem" /><div><strong>MELINOË</strong><span>CANCER RESEARCH OS</span></div></div>
        <div className="project-chip"><span className="pulse" /><div><small>ACTIVE PROJECT</small><b>{manifest.project_id.replaceAll("_", " ")}</b></div></div>
        <nav>{nav.map((item) => <button key={item.id} className={view === item.id ? "active" : ""} onClick={() => setView(item.id)}><span>{item.icon}</span>{item.label}{item.id === "guardrails" && report.summary.finding_counts.blocker > 0 && <b>{report.summary.finding_counts.blocker}</b>}</button>)}</nav>
        <div className="sidebar-bottom"><div className="local-badge"><span>●</span><div><b>Local-only session</b><small>No project data uploaded</small></div></div><p>Research use only<br />Not for clinical decision-making</p></div>
      </aside>
      <main>
        <header className="topbar">
          <div className="breadcrumbs"><span>WORKBENCH</span><i>/</i><b>{nav.find((item) => item.id === view)?.label}</b></div>
          <div className="top-actions"><button className="ghost" onClick={loadDemo}>Reset demo</button><button className="import" onClick={() => fileInput.current?.click()}>Import manifest <span>↑</span></button><input ref={fileInput} hidden type="file" accept="application/json,.json" onChange={(event) => event.target.files?.[0] && void importManifest(event.target.files[0])} /></div>
        </header>
        <div className="content">
          {view === "overview" && <Overview manifest={manifest} report={report} goTo={setView} />}
          {view === "guardrails" && <Guardrails report={report} />}
          {view === "graph" && <Graph manifest={manifest} />}
          {view === "workflows" && <Workflows blocked={report.summary.status === "blocked"} workflows={workflows} />}
          {view === "system" && <Platform system={system} policy={policy} />}
          {view === "capsule" && <Capsule manifest={manifest} report={report} download={downloadCapsule} />}
        </div>
      </main>
    </div>
  );
}
