const STATUS_COLORS = {
  OK: "#46d18a",
  WARN: "#f2c94c",
  FAIL: "#f26b6b",
};

const tabs = document.querySelectorAll(".tab");
const panels = {
  overview: document.getElementById("panel-overview"),
  local: document.getElementById("panel-local"),
  link: document.getElementById("panel-link"),
};

const statusLine = document.getElementById("status-line");
const statusIndicator = document.getElementById("status-indicator");
const statusCard = document.getElementById("status-card");
const overallStatus = document.getElementById("overall-status");
const findingsList = document.getElementById("findings-list");
const overviewInterface = document.getElementById("overview-interface");
const overviewIp = document.getElementById("overview-ip");
const overviewGateway = document.getElementById("overview-gateway");
const testTarget = document.getElementById("test-target");
const testOutput = document.getElementById("test-output");
const diagProgress = document.getElementById("diag-progress");
const diagProgressBar = document.getElementById("diag-progress-bar");
const exportProgress = document.getElementById("export-progress");
const exportProgressBar = document.getElementById("export-progress-bar");
const localInfoGrid = document.getElementById("local-info-grid");
const linkReason = document.getElementById("link-reason");
const linkTips = document.getElementById("link-tips");
const linkStatus = document.getElementById("link-status");
const linkNpcap = document.getElementById("link-npcap");
const linkProgress = document.getElementById("link-progress");
const linkProgressBar = document.getElementById("link-progress-bar");
const npcapLink = document.getElementById("npcap-link");
const restartButton = document.getElementById("restart-app");
const linkInstructions = document.getElementById("link-instructions");
const openExportButton = document.getElementById("open-export");
const openExportFolderButton = document.getElementById("open-export-folder");

let lastExportPath = "";
let progressTimer = null;
let progressStart = 0;
let progressExpected = 0;
let exportTimer = null;
let exportStart = 0;
let exportExpected = 0;
let linkTimer = null;
let linkStart = 0;
let linkExpected = 0;
const NPCAP_TIPS = [
  "Install Npcap with WinPcap compatibility",
  "Ensure capture permissions are available",
  "Passive capture window will be 20 seconds",
];
const NPCAP_DOWNLOAD = "https://npcap.com/#download";

function setActiveTab(name) {
  tabs.forEach((tab) => {
    const anchor = tab.querySelector(".rpg-nav-a");
    const isActive = (anchor?.dataset.tab || tab.dataset.tab) === name;
    tab.classList.toggle("active", isActive);
    const navItem = tab.querySelector(".rpg-nav-item");
    if (navItem) {
      navItem.classList.toggle("is-active", isActive);
    }
  });
  Object.keys(panels).forEach((key) => {
    panels[key].classList.toggle("active", key === name);
  });
}

async function fetchJson(path, options) {
  const response = await fetch(path, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = payload.error?.message || "Request failed";
    throw new Error(message);
  }
  return payload;
}

function setStatusLine(active) {
  const host = window.location.host || "127.0.0.1:9876";
  const statusText = active ? "FASTAPI ACTIVE" : "FASTAPI DOWN";
  if (statusLine) {
    statusLine.textContent = `${host} | ${statusText}`;
  }
  if (statusIndicator) {
    statusIndicator.style.background = active ? STATUS_COLORS.OK : STATUS_COLORS.FAIL;
  }
}

async function loadHealth() {
  try {
    await fetchJson("/api/health");
    setStatusLine(true);
  } catch (error) {
    setStatusLine(false);
  }
}

function renderFindings(findings) {
  findingsList.innerHTML = "";
  if (!findings || !findings.length) {
    findingsList.innerHTML = "<li>No findings yet.</li>";
    return;
  }
  findings.forEach((item) => {
    const li = document.createElement("li");
    li.textContent = item;
    findingsList.appendChild(li);
  });
}

async function loadOverview() {
  try {
    const data = await fetchJson("/api/overview");
    const status = data.status || "WARN";
    overallStatus.textContent = status;
    if (statusCard) {
      statusCard.dataset.status = status;
    }
    overviewInterface.textContent = data.active_interface || "--";
    overviewIp.textContent = data.ip || "--";
    overviewGateway.textContent = data.gateway || "--";
    renderFindings(data.key_findings || []);
  } catch (error) {
    overallStatus.textContent = "FAIL";
    if (statusCard) {
      statusCard.dataset.status = "FAIL";
    }
    renderFindings(["Overview unavailable", error.message]);
  }
}

function infoItem(label, value) {
  const wrapper = document.createElement("div");
  wrapper.className = "info-item";

  const title = document.createElement("span");
  title.textContent = label;

  const content = document.createElement("strong");
  content.textContent = value || "--";

  wrapper.appendChild(title);
  wrapper.appendChild(content);
  return wrapper;
}

async function loadLocalInfo() {
  try {
    const data = await fetchJson("/api/local-info");
    const dnsServers = Array.isArray(data.dns_servers)
      ? data.dns_servers
      : data.dns_servers
      ? [data.dns_servers]
      : [];
    localInfoGrid.innerHTML = "";
    localInfoGrid.appendChild(infoItem("Active Interface", data.active_interface));
    localInfoGrid.appendChild(infoItem("IPv4", data.ip));
    localInfoGrid.appendChild(infoItem("Prefix", data.prefix));
    localInfoGrid.appendChild(infoItem("Gateway", data.gateway));
    localInfoGrid.appendChild(infoItem("Gateway MAC", data.gateway_mac));
    localInfoGrid.appendChild(infoItem("Gateway Vendor", data.gateway_vendor));
    localInfoGrid.appendChild(infoItem("MAC", data.mac));
    localInfoGrid.appendChild(infoItem("DNS Servers", dnsServers.join(", ")));
    localInfoGrid.appendChild(infoItem("DHCP Enabled", String(data.dhcp_enabled)));
    localInfoGrid.appendChild(infoItem("Link Speed", data.link_speed));
  } catch (error) {
    localInfoGrid.innerHTML = "";
    localInfoGrid.appendChild(infoItem("Local Info", error.message));
  }
}

function renderLinkTips(tips) {
  linkTips.innerHTML = "";
  tips.forEach((tip) => {
    const li = document.createElement("li");
    li.textContent = tip;
    linkTips.appendChild(li);
  });
}

function setNpcapDownload(url) {
  if (url) {
    npcapLink.href = url;
    npcapLink.style.display = "inline-flex";
  } else {
    npcapLink.style.display = "none";
  }
}

function updateNpcapLine(installed, reason, status) {
  if (!linkNpcap) {
    return;
  }
  let value = installed;
  if (value === undefined) {
    const text = String(reason || "").toLowerCase();
    if (text.includes("not installed")) {
      value = false;
    } else if (status && status !== "UNAVAILABLE" && status !== "NOT INSTALLED") {
      value = true;
    }
  }
  if (value === true) {
    linkNpcap.textContent = "Npcap: Installed";
  } else if (value === false) {
    linkNpcap.textContent = "Npcap: Not installed";
  } else {
    linkNpcap.textContent = "Npcap: Checking";
  }
}

async function loadLinkDiscovery() {
  startLinkProgress();
  try {
    const data = await fetchJson("/api/link-discovery");
    if (linkStatus) {
      linkStatus.textContent = data.status || "UNAVAILABLE";
    }
    linkReason.textContent = data.reason || "Unavailable";
    updateNpcapLine(data.npcap_installed, data.reason, data.status);
    renderLinkTips(data.tips || []);
    setNpcapDownload(data.download_url || "");

    const instructions = Array.isArray(data.instructions) ? data.instructions : [];
    linkInstructions.textContent = instructions.join(" | ");
    linkInstructions.style.display = instructions.length ? "block" : "none";

    if (data.restart_supported) {
      restartButton.style.display = "inline-flex";
      restartButton.disabled = false;
      restartButton.textContent = "Restart App";
    } else {
      restartButton.style.display = "none";
    }
  } catch (error) {
    if (linkStatus) {
      linkStatus.textContent = "CHECKING";
    }
    linkReason.textContent = error.message;
    updateNpcapLine(undefined);
  } finally {
    finishLinkProgress();
  }
}

async function loadNpcapStatus() {
  try {
    const data = await fetchJson("/api/npcap-status");
    updateNpcapLine(data.npcap_installed);
  } catch (error) {
    updateNpcapLine(undefined);
  }
}

async function checkLinkDiscovery() {
  if (linkStatus) {
    linkStatus.textContent = "CHECKING";
  }
  linkReason.textContent = "Checking Npcap...";
  updateNpcapLine(undefined);
  renderLinkTips([]);
  setNpcapDownload("");
  linkInstructions.textContent = "";
  linkInstructions.style.display = "none";
  try {
    const data = await fetchJson("/api/npcap-status");
    const installed = data.npcap_installed === true;
    updateNpcapLine(installed);
    if (!installed) {
      if (linkStatus) {
        linkStatus.textContent = "NOT INSTALLED";
      }
      linkReason.textContent = "Npcap not installed.";
      renderLinkTips(NPCAP_TIPS);
      setNpcapDownload(NPCAP_DOWNLOAD);
      linkInstructions.textContent =
        "Download and install Npcap with WinPcap compatibility | After install, restart fastLANe to enable Link Discovery";
      linkInstructions.style.display = "block";
      finishLinkProgress();
      return;
    }
    linkReason.textContent = "Npcap installed. Starting discovery...";
    await loadLinkDiscovery();
  } catch (error) {
    if (linkStatus) {
      linkStatus.textContent = "CHECKING";
    }
    linkReason.textContent = error.message;
  }
}

async function runTest(type) {
  const target = testTarget.value.trim();
  if (!target) {
    testOutput.textContent = "Enter a target before running tests.";
    return;
  }

  testOutput.textContent = `Running ${type.toUpperCase()} against ${target}...`;
  startDiagProgress(type);

  try {
    const result = await fetchJson("/api/run-test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type, target }),
    });
    const lines = [];
    const summaryText = formatSummary(type, result.summary);
    if (summaryText) {
      lines.push("Summary:", summaryText);
    }
    const parsedPayload = result.parsed || safeParseJson(result.stdout);
    const parsedText = formatParsed(type, parsedPayload);
    if (parsedText) {
      lines.push("Details:", parsedText);
    } else if (result.stdout) {
      lines.push("Details:", formatPlainOutput(result.stdout));
    }
    if (result.stderr) {
      lines.push("Errors:", formatPlainOutput(result.stderr));
    }
    testOutput.textContent = lines.join("\n");
  } catch (error) {
    testOutput.textContent = `Test failed: ${error.message}`;
  } finally {
    finishDiagProgress();
  }
}

function startDiagProgress(type) {
  if (!diagProgress || !diagProgressBar) {
    return;
  }
  const map = {
    ping: 2500,
    dns: 2000,
    tnc: 5000,
    tracert: 12000,
  };
  progressExpected = map[type] || 4000;
  progressStart = performance.now();
  diagProgressBar.style.width = "0%";
  diagProgress.classList.remove("hidden");
  diagProgressBar.classList.add("is-charged");
  if (progressTimer) {
    clearInterval(progressTimer);
  }
  progressTimer = setInterval(updateDiagProgress, 120);
}

function updateDiagProgress() {
  const elapsed = performance.now() - progressStart;
  let ratio = elapsed / progressExpected;
  if (ratio > 1) {
    ratio = 1 + (ratio - 1) * 0.15;
  }
  const percent = Math.min(95, Math.round(5 + ratio * 90));
  diagProgressBar.style.width = `${percent}%`;
}

function finishDiagProgress() {
  if (!diagProgress || !diagProgressBar) {
    return;
  }
  if (progressTimer) {
    clearInterval(progressTimer);
    progressTimer = null;
  }
  diagProgressBar.style.width = "100%";
  setTimeout(() => {
    diagProgress.classList.add("hidden");
    diagProgressBar.classList.remove("is-charged");
    diagProgressBar.style.width = "0%";
  }, 400);
}

function startExportProgress() {
  if (!exportProgress || !exportProgressBar) {
    return;
  }
  exportExpected = 3000;
  exportStart = performance.now();
  exportProgressBar.style.width = "0%";
  exportProgress.classList.remove("hidden");
  exportProgressBar.classList.add("is-charged");
  if (exportTimer) {
    clearInterval(exportTimer);
  }
  exportTimer = setInterval(updateExportProgress, 120);
}

function updateExportProgress() {
  const elapsed = performance.now() - exportStart;
  let ratio = elapsed / exportExpected;
  if (ratio > 1) {
    ratio = 1 + (ratio - 1) * 0.2;
  }
  const percent = Math.min(95, Math.round(6 + ratio * 88));
  exportProgressBar.style.width = `${percent}%`;
}

function finishExportProgress() {
  if (!exportProgress || !exportProgressBar) {
    return;
  }
  if (exportTimer) {
    clearInterval(exportTimer);
    exportTimer = null;
  }
  exportProgressBar.style.width = "100%";
  setTimeout(() => {
    exportProgress.classList.add("hidden");
    exportProgressBar.classList.remove("is-charged");
    exportProgressBar.style.width = "0%";
  }, 400);
}

function startLinkProgress() {
  if (!linkProgress || !linkProgressBar) {
    return;
  }
  linkExpected = 20000;
  linkStart = performance.now();
  linkProgressBar.style.width = "0%";
  linkProgress.classList.remove("hidden");
  linkProgressBar.classList.add("is-charged");
  if (linkTimer) {
    clearInterval(linkTimer);
  }
  linkTimer = setInterval(updateLinkProgress, 120);
}

function updateLinkProgress() {
  const elapsed = performance.now() - linkStart;
  let ratio = elapsed / linkExpected;
  if (ratio > 1) {
    ratio = 1 + (ratio - 1) * 0.1;
  }
  const percent = Math.min(95, Math.round(5 + ratio * 90));
  linkProgressBar.style.width = `${percent}%`;
}

function finishLinkProgress() {
  if (!linkProgress || !linkProgressBar) {
    return;
  }
  if (linkTimer) {
    clearInterval(linkTimer);
    linkTimer = null;
  }
  linkProgressBar.style.width = "100%";
  setTimeout(() => {
    linkProgress.classList.add("hidden");
    linkProgressBar.classList.remove("is-charged");
    linkProgressBar.style.width = "0%";
  }, 400);
}

function safeParseJson(text) {
  if (!text) {
    return null;
  }
  const trimmed = String(text).trim();
  if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) {
    return null;
  }
  try {
    return JSON.parse(trimmed);
  } catch (error) {
    return null;
  }
}

function formatPlainOutput(text) {
  return String(text).replace(/\r\n/g, "\n").trim();
}

function formatSummary(type, summary) {
  if (!summary) {
    return "";
  }
  if (type === "ping") {
    const avg = summary.avg_ms !== null && summary.avg_ms !== undefined ? `${summary.avg_ms} ms` : "n/a";
    return `Sent: ${summary.sent} | Received: ${summary.received} | Avg: ${avg}`;
  }
  if (type === "dns") {
    return `Records: ${summary.record_count}`;
  }
  if (type === "tnc") {
    return `Ping: ${summary.ping_succeeded} | TCP: ${summary.tcp_test_succeeded} | Remote: ${summary.remote_address}:${summary.remote_port}`;
  }
  if (type === "tracert") {
    return `Hops: ${summary.hop_count}`;
  }
  return JSON.stringify(summary);
}

function formatParsed(type, parsed) {
  if (!parsed) {
    return "";
  }
  if (type === "ping") {
    const items = Array.isArray(parsed) ? parsed : [parsed];
    return items
      .map((item, index) => {
        const time = item.ResponseTime !== null && item.ResponseTime !== undefined ? `${item.ResponseTime} ms` : "n/a";
        const status = item.Status || "OK";
        return `${index + 1}. ${item.Address} | ${time} | ${status}`;
      })
      .join("\n");
  }
  if (type === "dns") {
    const items = Array.isArray(parsed) ? parsed : [parsed];
    return items
      .map((item) => {
        if (item.IPAddress) {
          return `${item.Type || "A"} ${item.Name} -> ${item.IPAddress}`;
        }
        if (item.NameHost) {
          return `${item.Type || "CNAME"} ${item.Name} -> ${item.NameHost}`;
        }
        return `${item.Type || "Record"} ${item.Name || ""}`;
      })
      .join("\n");
  }
  if (type === "tnc") {
    return [
      `Computer: ${parsed.ComputerName || "unknown"}`,
      `Remote: ${parsed.RemoteAddress || "unknown"}:${parsed.RemotePort || "n/a"}`,
      `Ping: ${parsed.PingSucceeded}`,
      `TCP: ${parsed.TcpTestSucceeded}`,
      `Interface: ${parsed.InterfaceAlias || "n/a"}`,
    ].join("\n");
  }
  if (type === "tracert") {
    const hops = parsed.hops || [];
    if (!hops.length) {
      return "";
    }
    return hops.map((hop) => `${hop.hop}. ${hop.raw}`).join("\n");
  }
  return "";
}

async function exportReport(format) {
  if (window.pywebview?.api?.save_report) {
    try {
      startExportProgress();
      const result = await window.pywebview.api.save_report(format);
      if (result.cancelled) {
        finishExportProgress();
        return;
      }
      if (result.pending) {
        testOutput.textContent = `Saving export to: ${result.path}`;
        lastExportPath = result.path || "";
        syncExportButtons();
        return;
      }
      if (!result.ok) {
        throw new Error(result.error || "Export failed");
      }
      testOutput.textContent = `Export saved: ${result.path}`;
      lastExportPath = result.path || "";
      syncExportButtons();
      finishExportProgress();
      return;
    } catch (error) {
      testOutput.textContent = `Export failed: ${error.message}`;
      finishExportProgress();
      return;
    }
  }

  try {
    startExportProgress();
    const response = await fetch("/api/export", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ format }),
    });
    if (!response.ok) {
      throw new Error("Export failed");
    }
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    const filename = response.headers.get("Content-Disposition")?.split("filename=")[1] || `fastlane_report.${format}`;
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
    finishExportProgress();
  } catch (error) {
    testOutput.textContent = `Export failed: ${error.message}`;
    finishExportProgress();
  }
}

function bindEvents() {
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const anchor = tab.querySelector(".rpg-nav-a");
      const target = anchor?.dataset.tab || tab.dataset.tab;
      setActiveTab(target);
      if (target === "overview") {
        loadOverview();
      }
      if (target === "local") {
        loadLocalInfo();
      }
      if (target === "link") {
        checkLinkDiscovery();
      }
    });
  });

  document.querySelectorAll("[data-test]").forEach((button) => {
    button.addEventListener("click", () => runTest(button.dataset.test));
  });

  document.querySelectorAll("[data-export]").forEach((button) => {
    button.addEventListener("click", () => exportReport(button.dataset.export));
  });

  restartButton.addEventListener("click", () => restartApp());
  openExportButton.addEventListener("click", () => openExportFile());
  openExportFolderButton.addEventListener("click", () => openExportFolder());
}

async function init() {
  bindEvents();
  await loadHealth();
  await loadOverview();
  await loadLocalInfo();
  await loadNpcapStatus();
  syncExportButtons();
}

init();

async function restartApp() {
  restartButton.disabled = true;
  restartButton.textContent = "Restarting...";
  try {
    await fetchJson("/api/restart", { method: "POST" });
    linkInstructions.style.display = "block";
    linkInstructions.textContent = "Restarting fastLANe...";
  } catch (error) {
    restartButton.disabled = false;
    restartButton.textContent = "Restart App";
    linkInstructions.style.display = "block";
    linkInstructions.textContent = `Restart failed: ${error.message}`;
  }
}

window.fastlaneExportDone = function (result) {
  if (!result) {
    return;
  }
  if (result.ok) {
    testOutput.textContent = `Export saved: ${result.path}`;
    lastExportPath = result.path || "";
    syncExportButtons();
  } else {
    testOutput.textContent = `Export failed: ${result.error || "Unknown error"}`;
  }
  finishExportProgress();
};

function syncExportButtons() {
  const available = Boolean(lastExportPath && window.pywebview?.api?.open_export);
  openExportButton.disabled = !available;
  openExportFolderButton.disabled = !available;
}

async function openExportFile() {
  if (!lastExportPath) {
    return;
  }
  try {
    await window.pywebview.api.open_export(lastExportPath);
  } catch (error) {
    testOutput.textContent = `Open failed: ${error.message}`;
  }
}

async function openExportFolder() {
  if (!lastExportPath) {
    return;
  }
  try {
    await window.pywebview.api.open_export_folder(lastExportPath);
  } catch (error) {
    testOutput.textContent = `Open folder failed: ${error.message}`;
  }
}
