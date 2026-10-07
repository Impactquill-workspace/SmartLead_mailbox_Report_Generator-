/**
 * Frontend logic for Smartlead Mailbox Analytics Dashboard
 */

document.addEventListener("DOMContentLoaded", () => {
  // DOM Elements
  const startDateInput = document.getElementById("start-date");
  const endDateInput = document.getElementById("end-date");
  const clientSelect = document.getElementById("client-select");
  const reportForm = document.getElementById("report-form");
  const generateBtn = document.getElementById("generate-btn");
  const loadingState = document.getElementById("loading-state");
  const errorState = document.getElementById("error-state");
  const errorMessage = document.getElementById("error-message");
  const resultsSection = document.getElementById("results-section");

  // Presets
  const presetLastWeekBtn = document.getElementById("preset-last-week");
  const preset7DaysBtn = document.getElementById("preset-7-days");
  const preset14DaysBtn = document.getElementById("preset-14-days");

  // Tabs
  const tabMailbox = document.getElementById("tab-mailbox");
  const tabClient = document.getElementById("tab-client");
  const viewMailbox = document.getElementById("view-mailbox");
  const viewClient = document.getElementById("view-client");

  // Tables
  const mailboxTableBody = document.getElementById("mailbox-table-body");
  const clientTableBody = document.getElementById("client-table-body");
  const tableSearch = document.getElementById("table-search");
  const rowCount = document.getElementById("row-count");
  const downloadExcelBtn = document.getElementById("download-excel-btn");

  // State
  let currentReportData = null;
  let activeTab = "mailbox"; // 'mailbox' | 'client'
  let cachedPresetDates = null;

  // 1. Initialize Presets & Clients
  initPresets();
  loadClients();

  async function initPresets() {
    try {
      const res = await fetch("/api/reports/presets");
      if (res.ok) {
        const data = await res.json();
        cachedPresetDates = data.last_week;
        if (cachedPresetDates) {
          startDateInput.value = cachedPresetDates.start_date;
          endDateInput.value = cachedPresetDates.end_date;
        }
      }
    } catch (err) {
      console.warn("Could not load presets from server, falling back to local date math:", err);
      setFallbackLastWeek();
    }
  }

  function setFallbackLastWeek() {
    const today = new Date();
    const day = today.getDay();
    const diffToPrevMonday = (day === 0 ? 7 : day) + 6;
    const prevMonday = new Date(today);
    prevMonday.setDate(today.getDate() - diffToPrevMonday);
    const prevSunday = new Date(prevMonday);
    prevSunday.setDate(prevMonday.getDate() + 6);

    startDateInput.value = prevMonday.toISOString().split("T")[0];
    endDateInput.value = prevSunday.toISOString().split("T")[0];
  }

  async function loadClients() {
    try {
      const res = await fetch("/api/clients/");
      if (res.ok) {
        const clients = await res.json();
        clients.sort((a, b) => (a.name || "").localeCompare(b.name || ""));
        clients.forEach((c) => {
          const opt = document.createElement("option");
          opt.value = c.id;
          opt.textContent = `${c.name || "Client " + c.id} (ID: ${c.id})`;
          clientSelect.appendChild(opt);
        });
      }
    } catch (err) {
      console.error("Failed to load clients list:", err);
    }
  }

  // Preset Buttons Handlers
  presetLastWeekBtn.addEventListener("click", () => {
    if (cachedPresetDates) {
      startDateInput.value = cachedPresetDates.start_date;
      endDateInput.value = cachedPresetDates.end_date;
    } else {
      setFallbackLastWeek();
    }
  });

  preset7DaysBtn.addEventListener("click", () => {
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - 7);
    startDateInput.value = start.toISOString().split("T")[0];
    endDateInput.value = end.toISOString().split("T")[0];
  });

  preset14DaysBtn.addEventListener("click", () => {
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - 14);
    startDateInput.value = start.toISOString().split("T")[0];
    endDateInput.value = end.toISOString().split("T")[0];
  });

  // Tab switching
  tabMailbox.addEventListener("click", () => {
    activeTab = "mailbox";
    tabMailbox.className = "px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-indigo-600 text-white shadow-xs transition";
    tabClient.className = "px-3.5 py-1.5 text-xs font-medium rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-200/60 transition";
    viewMailbox.classList.remove("hidden");
    viewClient.classList.add("hidden");
    filterTables();
  });

  tabClient.addEventListener("click", () => {
    activeTab = "client";
    tabClient.className = "px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-indigo-600 text-white shadow-xs transition";
    tabMailbox.className = "px-3.5 py-1.5 text-xs font-medium rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-200/60 transition";
    viewClient.classList.remove("hidden");
    viewMailbox.classList.add("hidden");
    filterTables();
  });

  // Form submission
  reportForm.addEventListener("submit", async (e) => {
    e.preventDefault();

    const startDate = startDateInput.value;
    const endDate = endDateInput.value;
    const clientId = clientSelect.value ? parseInt(clientSelect.value, 10) : null;
    const statusFilter = document.querySelector('input[name="status_filter"]:checked')?.value || null;

    if (!startDate || !endDate) {
      alert("Please select both start and end dates.");
      return;
    }

    // UI State: Loading
    loadingState.classList.remove("hidden");
    resultsSection.classList.add("hidden");
    errorState.classList.add("hidden");
    generateBtn.disabled = true;
    generateBtn.classList.add("opacity-60", "cursor-not-allowed");

    try {
      const response = await fetch("/api/reports/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          start_date: startDate,
          end_date: endDate,
          client_id: clientId,
          status_filter: statusFilter,
        }),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || `Server returned status ${response.status}`);
      }

      currentReportData = await response.json();
      renderReport(currentReportData);
    } catch (err) {
      console.error("Report generation failed:", err);
      errorMessage.textContent = err.message || "An unexpected error occurred while fetching report.";
      errorState.classList.remove("hidden");
    } finally {
      loadingState.classList.add("hidden");
      generateBtn.disabled = false;
      generateBtn.classList.remove("opacity-60", "cursor-not-allowed");
    }
  });

  // Render Data
  function renderReport(data) {
    if (!data) return;

    // KPI Cards
    document.getElementById("kpi-clients").textContent = (data.total_clients || 0).toLocaleString();
    document.getElementById("kpi-mailboxes").textContent = (data.total_mailboxes || 0).toLocaleString();
    document.getElementById("kpi-leads").textContent = (data.total_leads_contacted || 0).toLocaleString();
    document.getElementById("kpi-sent").textContent = (data.total_sent || 0).toLocaleString();
    document.getElementById("kpi-bounced").textContent = (data.total_bounced || 0).toLocaleString();
    
    const rateElem = document.getElementById("kpi-rate");
    const rateBadge = document.getElementById("kpi-rate-badge");
    const rateVal = data.overall_bounce_rate || 0;
    rateElem.textContent = `${rateVal.toFixed(2)}%`;

    if (rateVal < 2.0) {
      rateBadge.innerHTML = `<span class="text-[10px] font-bold px-2 py-0.5 rounded badge-low">Good Deliverability</span>`;
    } else if (rateVal <= 4.0) {
      rateBadge.innerHTML = `<span class="text-[10px] font-bold px-2 py-0.5 rounded badge-med">Monitor Mailboxes</span>`;
    } else {
      rateBadge.innerHTML = `<span class="text-[10px] font-bold px-2 py-0.5 rounded badge-high">High Bounce Rate</span>`;
    }

    // Render Tables
    renderMailboxTable(data.clients || []);
    renderClientTable(data.clients || []);

    // Setup Download Button
    if (data.excel_file_path) {
      const parts = data.excel_file_path.split(/[\\/]/);
      const filename = parts[parts.length - 1];
      downloadExcelBtn.onclick = () => {
        window.location.href = `/api/reports/download/${encodeURIComponent(filename)}`;
      };
    } else {
      downloadExcelBtn.onclick = () => {
        window.location.href = `/api/reports/weekly/export?start_date=${encodeURIComponent(data.period_start)}&end_date=${encodeURIComponent(data.period_end)}`;
      };
    }

    resultsSection.classList.remove("hidden");
    filterTables();
  }

  function renderMailboxTable(clients) {
    mailboxTableBody.innerHTML = "";
    let count = 0;

    clients.forEach((c) => {
      (c.mailboxes || []).forEach((m) => {
        count++;
        const tr = document.createElement("tr");
        tr.className = "hover:bg-slate-50 transition border-b border-slate-100 search-row";
        tr.dataset.text = `${c.client_name} ${m.email}`.toLowerCase();

        const badgeClass = m.bounce_rate < 2.0 ? "badge-low" : m.bounce_rate <= 4.0 ? "badge-med" : "badge-high";

        tr.innerHTML = `
          <td class="py-2.5 px-4 text-slate-400 text-center font-sans">${count}</td>
          <td class="py-2.5 px-4 font-sans font-medium text-slate-800">${escapeHtml(c.client_name)}</td>
          <td class="py-2.5 px-4 text-indigo-700 font-semibold">${escapeHtml(m.email)}</td>
          <td class="py-2.5 px-4 text-right font-semibold text-emerald-700">${(m.leads_contacted || 0).toLocaleString()}</td>
          <td class="py-2.5 px-4 text-right font-semibold text-slate-800">${(m.sent || 0).toLocaleString()}</td>
          <td class="py-2.5 px-4 text-right text-slate-700">${(m.bounced || 0).toLocaleString()}</td>
          <td class="py-2.5 px-4 text-right">
            <span class="px-2 py-0.5 rounded text-[10px] font-bold ${badgeClass}">
              ${(m.bounce_rate || 0).toFixed(2)}%
            </span>
          </td>
          <td class="py-2.5 px-4 text-right text-slate-400 font-sans">${m.mailbox_id || "-"}</td>
        `;
        mailboxTableBody.appendChild(tr);
      });
    });
  }

  function renderClientTable(clients) {
    clientTableBody.innerHTML = "";
    let count = 0;

    clients.forEach((c) => {
      count++;
      const tr = document.createElement("tr");
      tr.className = "hover:bg-slate-50 transition border-b border-slate-100 search-row";
      tr.dataset.text = `${c.client_name} ${c.client_id}`.toLowerCase();

      const mailboxes = c.mailboxes || [];
      const totalLeads = mailboxes.reduce((acc, m) => acc + (m.leads_contacted || 0), 0);
      const totalSent = mailboxes.reduce((acc, m) => acc + (m.sent || 0), 0);
      const totalBounced = mailboxes.reduce((acc, m) => acc + (m.bounced || 0), 0);
      const rate = totalSent > 0 ? (totalBounced / totalSent) * 100 : 0;
      const badgeClass = rate < 2.0 ? "badge-low" : rate <= 4.0 ? "badge-med" : "badge-high";

      tr.innerHTML = `
        <td class="py-2.5 px-4 text-slate-400 text-center font-sans">${count}</td>
        <td class="py-2.5 px-4 font-sans font-bold text-slate-800">${escapeHtml(c.client_name)}</td>
        <td class="py-2.5 px-4 text-center text-slate-500 font-sans">${c.client_id}</td>
        <td class="py-2.5 px-4 text-center font-sans font-semibold text-indigo-600">${mailboxes.length}</td>
        <td class="py-2.5 px-4 text-right font-semibold text-emerald-700">${totalLeads.toLocaleString()}</td>
        <td class="py-2.5 px-4 text-right font-semibold text-slate-800">${totalSent.toLocaleString()}</td>
        <td class="py-2.5 px-4 text-right text-slate-700">${totalBounced.toLocaleString()}</td>
        <td class="py-2.5 px-4 text-right">
          <span class="px-2 py-0.5 rounded text-[10px] font-bold ${badgeClass}">
            ${rate.toFixed(2)}%
          </span>
        </td>
      `;
      clientTableBody.appendChild(tr);
    });
  }

  // Search / Filter table
  tableSearch.addEventListener("input", filterTables);

  function filterTables() {
    const q = (tableSearch.value || "").trim().toLowerCase();
    const activeBody = activeTab === "mailbox" ? mailboxTableBody : clientTableBody;
    const rows = activeBody.querySelectorAll(".search-row");
    let visibleCount = 0;

    rows.forEach((row) => {
      const text = row.dataset.text || "";
      if (!q || text.includes(q)) {
        row.classList.remove("hidden");
        visibleCount++;
      } else {
        row.classList.add("hidden");
      }
    });

    rowCount.textContent = `Showing ${visibleCount} of ${rows.length} records`;
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
});
