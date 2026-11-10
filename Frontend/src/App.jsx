import { useEffect, useState } from "react";
import { Line } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Filler,
} from "chart.js";
import "./index.css";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Filler);

const API = "http://127.0.0.1:8000";

function App() {
  const [file, setFile] = useState(null);
  const [report, setReport] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [history, setHistory] = useState([]);

  async function loadHistory() {
    try {
      const response = await fetch(`${API}/history`);
      if (!response.ok) throw new Error("History load nahi hui");
      setHistory(await response.json());
    } catch (err) {
      console.error(err);
    }
  }

  useEffect(() => {
    loadHistory();
  }, []);

  async function scanProject() {
    if (!file) return;
    setLoading(true);
    setReport(null);
    setError("");
    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch(`${API}/upload`, { method: "POST", body: formData });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Scan nahi ho paya.");
      setReport(result);
      await loadHistory();
    } catch (err) {
      setError(err.message || "Backend se connect nahi ho paya.");
    } finally {
      setLoading(false);
    }
  }

  function exportReport() {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${report.filename}-report.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  const scans = [...history].reverse();
  const chartData = {
    labels: scans.map((scan) => new Date(scan.created_at).toLocaleDateString()),
    datasets: [{
      label: "Health score",
      data: scans.map((scan) => scan.score),
      borderColor: "#8b7cff",
      backgroundColor: "rgba(139, 124, 255, 0.14)",
      pointBackgroundColor: "#a89cff",
      pointBorderColor: "#171827",
      pointRadius: 4,
      fill: true,
      tension: 0.38,
    }],
  };
  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: { backgroundColor: "#222337", titleColor: "#fff", bodyColor: "#c9c9dc", padding: 12 },
    },
    scales: {
      x: { grid: { color: "rgba(160,160,190,.08)" }, ticks: { color: "#85869d" } },
      y: { min: 0, max: 100, grid: { color: "rgba(160,160,190,.08)" }, ticks: { color: "#85869d" } },
    },
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top"><span className="brand-mark">⌘</span><span>Code<span className="brand-accent">Lens</span><small>CODE HEALTH, IN FOCUS</small></span></a>
        <div className="top-status"><span className="status-dot" /> LOCAL SCANNER <span className="top-divider" /> PYTHON + JAVASCRIPT</div>
      </header>

      <section className="hero" id="top">
        <div className="hero-copy">
          <div className="eyebrow"><span /> PROJECT QUALITY INSPECTOR</div>
          <h1>See the health<br />behind your <span>code.</span></h1>
          <p>Spot complexity, code smells, duplication and risky files before they slow your team down.</p>
        </div>
        <div className="hero-orbit" aria-hidden="true"><div className="orbit-ring ring-one"/><div className="orbit-ring ring-two"/><div className="orbit-core">CL</div><i className="orbit-dot dot-one"/><i className="orbit-dot dot-two"/><i className="orbit-dot dot-three"/></div>
      </section>

      <section className="panel upload-panel">
        <div className="panel-heading"><div><span className="section-kicker">01 / START A SCAN</span><h2>Analyze a project</h2><p>Choose a ZIP containing your Python or JavaScript source files.</p></div><span className="zip-pill">ZIP · MAX 20 MB</span></div>
        <div className="upload-controls">
          <label className="file-picker"><input type="file" accept=".zip" onChange={(event) => { setFile(event.target.files?.[0] || null); setReport(null); setError(""); }} /><span className="file-icon">↑</span><span className="file-copy"><strong>{file ? file.name : "Choose a project ZIP"}</strong><small>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB · Ready to scan` : "Click to browse your files"}</small></span><span className="browse-label">Browse</span></label>
          <button className="scan-button" onClick={scanProject} disabled={!file || loading}>{loading ? <><span className="spinner"/> Scanning…</> : <>Scan project <span>→</span></>}</button>
        </div>
        {error && <div className="error-banner">{error}</div>}
      </section>

      {report && <>
        <section className="section-block report-block">
          <div className="section-title"><div><span className="section-kicker">02 / SCAN RESULTS</span><h2>Project overview</h2></div><button className="quiet-button" onClick={exportReport}>↓ <span>Export JSON</span></button></div>
          <div className="stats-grid">
            <div className="stat-card grade-card"><span className="stat-label">HEALTH GRADE</span><div className={`grade-value grade-${String(report.grade).toLowerCase()}`}>{report.grade}</div><span className="stat-foot">Overall project health</span></div>
            <Stat label="Health score" value={`${report.score}`} suffix="/100" accent="purple" />
            <Stat label="Files scanned" value={report.files_scanned} accent="blue" />
            <Stat label="Lines of code" value={report.total_lines} accent="teal" />
            <Stat label="Functions" value={report.total_functions} accent="amber" />
            <Stat label="Maintainability" value={report.maintainability_index ?? "N/A"} suffix={report.maintainability_index == null ? "" : "/100"} accent="pink" />
          </div>
          <div className="content-grid">
            <article className="panel inner-panel"><div className="panel-heading compact"><div><span className="section-kicker">CODE REUSE</span><h3>Duplicate blocks</h3></div><span className="count-pill">{report.duplicates?.length || 0} FOUND</span></div>
              {report.duplicates?.length ? report.duplicates.map((duplicate, index) => <div className="duplicate-card" key={index}><pre>{duplicate.code}</pre><small>{duplicate.locations.map((location) => `${location.file}, line ${location.line}`).join(" · ")}</small></div>) : <div className="empty-state"><span>✓</span><p>No repeated code blocks found.</p></div>}
              {report.project_score_reasons?.length > 0 && <p className="score-reasons">{report.project_score_reasons.join(" · ")}</p>}
            </article>
            <article className="panel inner-panel"><div className="panel-heading compact"><div><span className="section-kicker">QUALITY OVER TIME</span><h3>Score trend</h3></div><span className="count-pill">{history.length} SCANS</span></div>
              {history.length > 0 ? <div className="chart-wrap"><Line data={chartData} options={chartOptions}/></div> : <div className="empty-state"><p>Trend appears after your first scan.</p></div>}
            </article>
          </div>
        </section>

        <section className="panel table-panel"><div className="panel-heading"><div><span className="section-kicker">03 / PRIORITIZE FIXES</span><h2>Riskiest files</h2><p>Files with the lowest health scores appear first.</p></div><span className="count-pill">{report.files.length} FILES</span></div>
          <div className="table-scroll"><div className="file-table table-head"><span>FILE</span><span>LINES</span><span>COMPLEXITY</span><span>MAINTAINABILITY</span><span>SCORE</span></div>
            {report.files.map((item) => <div className="file-table file-row" key={item.file}><div className="file-name"><strong>{item.file}</strong>{item.issue && <small className="issue-text">{item.issue}</small>}<small>{item.smells?.join(" · ") || "No major code smells found"}</small>{item.score_reasons?.length > 0 && <small className="reason-text">{item.score_reasons.join(" · ")}</small>}</div><span>{item.lines}</span><span>{item.complexity}</span><span>{item.maintainability_index == null ? "N/A" : `${item.maintainability_index} · ${item.maintainability_rank}`}</span><span className={`score-chip ${item.score < 60 ? "score-low" : item.score < 80 ? "score-mid" : "score-high"}`}>{item.score}/100</span></div>)}
          </div>
        </section>
      </>}

      <section className="section-block history-block"><div className="section-title"><div><span className="section-kicker">YOUR LOCAL SCAN LOG</span><h2>Recent scans</h2></div><span className="count-pill">LAST {history.length} SCANS</span></div>
        {history.length ? <div className="panel history-list">{history.map((scan) => <div className="history-row" key={scan.id}><div className="history-file"><span className="history-icon">⌁</span><span><strong>{scan.filename}</strong><small>{new Date(scan.created_at).toLocaleString()}</small></span></div><span className={`history-grade grade-${String(scan.grade).toLowerCase()}`}>{scan.grade}</span><strong className="history-score">{scan.score}<small>/100</small></strong></div>)}</div> : <div className="panel empty-history"><span className="history-icon">⌁</span><p>No scans yet. Upload a project ZIP to get started.</p></div>}
      </section>

      <footer className="footer"><span>CodeLens <b>·</b> Local code quality insights</span><span>YOUR CODE STAYS ON YOUR MACHINE</span></footer>
    </main>
  );
}

function Stat({ label, value, suffix = "", accent }) {
  return <div className={`stat-card stat-${accent}`}><span className="stat-label">{label}</span><div className="stat-number">{value}<small>{suffix}</small></div><div className="stat-accent"/></div>;
}

export default App;
