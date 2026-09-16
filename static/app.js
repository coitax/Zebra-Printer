const state = {
  file: null,
  zoom: 1,
  previewTimer: null,
};

const els = {
  file: document.getElementById("file"),
  dropzone: document.getElementById("dropzone"),
  fileName: document.getElementById("fileName"),
  preset: document.getElementById("preset"),
  customSize: document.getElementById("customSize"),
  widthIn: document.getElementById("widthIn"),
  heightIn: document.getElementById("heightIn"),
  fit: document.getElementById("fit"),
  dither: document.getElementById("dither"),
  contrast: document.getElementById("contrast"),
  contrastValue: document.getElementById("contrastValue"),
  threshold: document.getElementById("threshold"),
  thresholdValue: document.getElementById("thresholdValue"),
  thresholdRow: document.getElementById("thresholdRow"),
  sharpen: document.getElementById("sharpen"),
  printer: document.getElementById("printer"),
  darkness: document.getElementById("darkness"),
  darknessValue: document.getElementById("darknessValue"),
  speed: document.getElementById("speed"),
  copies: document.getElementById("copies"),
  printBtn: document.getElementById("printBtn"),
  zplBtn: document.getElementById("zplBtn"),
  calibrateBtn: document.getElementById("calibrateBtn"),
  mediaCalibrateBtn: document.getElementById("mediaCalibrateBtn"),
  fitBadge: document.getElementById("fitBadge"),
  probeBtn: document.getElementById("probeBtn"),
  refreshPrintersBtn: document.getElementById("refreshPrintersBtn"),
  probePill: document.getElementById("probePill"),
  probeMsg: document.getElementById("probeMsg"),
  status: document.getElementById("status"),
  meta: document.getElementById("meta"),
  originalPreview: document.getElementById("originalPreview"),
  printPreview: document.getElementById("printPreview"),
};

init();

async function init() {
  bindControls();
  await Promise.all([loadPresets(), loadPrinters()]);
  updateThresholdVisibility();
}

function bindControls() {
  els.file.addEventListener("change", () => {
    if (els.file.files[0]) setFile(els.file.files[0]);
  });

  ["dragenter", "dragover"].forEach((eventName) => {
    els.dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      els.dropzone.classList.add("drag");
    });
  });
  ["dragleave", "drop"].forEach((eventName) => {
    els.dropzone.addEventListener(eventName, (event) => {
      event.preventDefault();
      els.dropzone.classList.remove("drag");
    });
  });
  els.dropzone.addEventListener("drop", (event) => {
    const file = event.dataTransfer.files[0];
    if (file) setFile(file);
  });

  [
    els.preset,
    els.widthIn,
    els.heightIn,
    els.fit,
    els.dither,
    els.contrast,
    els.threshold,
    els.sharpen,
  ].forEach((el) => el.addEventListener("input", onSettingsChange));

  els.darkness.addEventListener("input", () => {
    els.darknessValue.textContent = els.darkness.value;
  });

  document.querySelectorAll("[data-zoom]").forEach((button) => {
    button.addEventListener("click", () => {
      state.zoom = Number(button.dataset.zoom);
      document.querySelectorAll("[data-zoom]").forEach((item) => {
        item.classList.toggle("active", item === button);
      });
      applyZoom();
    });
  });

  els.printBtn.addEventListener("click", () => submitJob("/api/print", "Printed."));
  els.zplBtn.addEventListener("click", downloadZpl);
  els.calibrateBtn.addEventListener("click", printCalibration);
  els.mediaCalibrateBtn.addEventListener("click", calibrateMedia);
  els.probeBtn.addEventListener("click", () => probePrinter());
  els.refreshPrintersBtn.addEventListener("click", () => loadPrinters({ probe: true }));
  els.printer.addEventListener("change", () => probePrinter());
}

async function loadPresets() {
  const data = await fetchJson("/api/presets");
  els.preset.innerHTML = "";
  for (const preset of data.presets) {
    const option = document.createElement("option");
    option.value = preset.id;
    option.textContent = `${preset.label} · ${Math.round(preset.width_in * 203)}×${Math.round(preset.height_in * 203)} dots`;
    if (preset.id === data.default) option.selected = true;
    els.preset.appendChild(option);
  }
  const custom = document.createElement("option");
  custom.value = "custom";
  custom.textContent = "Custom size";
  els.preset.appendChild(custom);
}

async function loadPrinters({ probe = true } = {}) {
  try {
    const data = await fetchJson("/api/printers");
    els.printer.innerHTML = "";
    if (!data.printers.length) {
      els.printer.innerHTML = '<option value="">No Windows printers found</option>';
      setProbe("err", "No printers found", "Install the GK420D in Windows, then refresh.");
      setStatus("No printers found. Install the GK420D in Windows first.", "err");
      return;
    }
    for (const printer of data.printers) {
      const option = document.createElement("option");
      option.value = printer.name;
      const mark = printer.likely_zebra ? "Zebra" : "Other";
      const online = printer.online ? "online" : printer.status_text;
      option.textContent = `${printer.name} · ${mark} · ${online}`;
      if (printer.name === data.default) option.selected = true;
      els.printer.appendChild(option);
    }
    if (!data.zebra_found) {
      setProbe("err", "No Zebra queue", "Windows only sees other printers. Add the GK420D, then refresh.");
      setStatus("No Zebra / GK420D printer queue found yet.", "err");
      return;
    }
    if (probe) await probePrinter();
  } catch (error) {
    els.printer.innerHTML = '<option value="">Printer list unavailable</option>';
    setProbe("err", "Unavailable", error.message);
    setStatus(error.message, "err");
  }
}

async function probePrinter() {
  if (!els.printer.value) {
    setProbe("err", "No printer", "Choose a printer first.");
    return;
  }
  setProbe("checking", "Checking…", "Asking Windows and the printer for an identity reply.");
  try {
    const body = new FormData();
    body.append("printer_name", els.printer.value);
    const response = await fetch("/api/printers/probe", { method: "POST", body });
    if (!response.ok) throw new Error(await errorMessage(response));
    const data = await response.json();
    const details = [data.message];
    if (data.port) details.push(`Port ${data.port}`);
    if (data.driver) details.push(data.driver);
    if (data.hints && data.hints.length) details.push(data.hints[0]);
    if (data.talking) {
      setProbe("talking", "Talking", details.join(" "));
      setStatus(data.message, "ok");
    } else if (data.ok) {
      setProbe("online", "Online, no reply", details.join(" "));
      setStatus(data.message, "");
    } else {
      setProbe("offline", data.online ? "No handshake" : "Offline", details.join(" "));
      setStatus(data.message, "err");
    }
  } catch (error) {
    setProbe("err", "Probe failed", error.message);
    setStatus(error.message, "err");
  }
}

function setProbe(state, label, message) {
  els.probePill.dataset.state = state;
  els.probePill.textContent = label;
  els.probeMsg.textContent = message;
}

function setFile(file) {
  state.file = file;
  els.fileName.textContent = file.name;
  els.printBtn.disabled = false;
  els.zplBtn.disabled = false;
  queuePreview();
}

function onSettingsChange() {
  els.customSize.classList.toggle("hidden", els.preset.value !== "custom");
  updateThresholdVisibility();
  els.contrastValue.textContent = Number(els.contrast.value).toFixed(2);
  els.thresholdValue.textContent = els.threshold.value;
  if (state.file) queuePreview();
}

function updateThresholdVisibility() {
  els.thresholdRow.classList.toggle("hidden", els.dither.value !== "threshold");
}

function queuePreview() {
  clearTimeout(state.previewTimer);
  state.previewTimer = setTimeout(runPreview, 250);
}

async function runPreview() {
  if (!state.file) return;
  setStatus("Rendering 1-bit preview…");
  try {
    const data = await postForm("/api/preview");
    showPreview(els.originalPreview, data.original_png);
    showPreview(els.printPreview, data.print_png);
    applyZoom();
    els.meta.textContent = `${data.width_in.toFixed(2)}" × ${data.height_in.toFixed(2)}" · ${data.width_dots} × ${data.height_dots} dots @ 203 DPI`;
    if (data.fits_one_label) {
      els.fitBadge.textContent = `Fits one ${data.width_in.toFixed(2)}" × ${data.height_in.toFixed(2)}" label. Bitmap is ${data.bitmap_width}×${data.bitmap_height} dots.`;
      els.fitBadge.className = "fit-badge ok";
      setStatus("Preview is one label. If a print still crosses a gap, calibrate media first.", "ok");
    } else {
      els.fitBadge.textContent = `Bitmap ${data.bitmap_width}×${data.bitmap_height} does not match the ${data.width_dots}×${data.height_dots} label.`;
      els.fitBadge.className = "fit-badge err";
      setStatus("Image does not fit one label. Check the size preset.", "err");
    }
  } catch (error) {
    setStatus(error.message, "err");
  }
}

function showPreview(img, b64) {
  img.src = `data:image/png;base64,${b64}`;
  img.hidden = false;
  const placeholder = img.parentElement.querySelector(".placeholder");
  if (placeholder) placeholder.hidden = true;
}

function applyZoom() {
  [els.originalPreview, els.printPreview].forEach((img) => {
    if (!img.naturalWidth) return;
    img.style.width = `${img.naturalWidth * state.zoom}px`;
    img.style.height = `${img.naturalHeight * state.zoom}px`;
  });
}

async function submitJob(url, successText) {
  if (!state.file) return;
  if (!els.printer.value) {
    setStatus("Choose a printer first.", "err");
    return;
  }
  setStatus("Sending raw ZPL…");
  try {
    await postForm(url);
    setStatus(successText, "ok");
  } catch (error) {
    setStatus(error.message, "err");
  }
}

async function downloadZpl() {
  if (!state.file) return;
  setStatus("Building ZPL…");
  try {
    const response = await fetch("/api/zpl", { method: "POST", body: buildForm() });
    if (!response.ok) throw new Error(await errorMessage(response));
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "sticker.zpl";
    link.click();
    URL.revokeObjectURL(url);
    setStatus("ZPL downloaded.", "ok");
  } catch (error) {
    setStatus(error.message, "err");
  }
}

async function printCalibration() {
  if (!els.printer.value) {
    setStatus("Choose a printer first.", "err");
    return;
  }
  const body = new FormData();
  appendShared(body);
  body.append("printer_name", els.printer.value);
  setStatus("Printing calibration label…");
  try {
    const response = await fetch("/api/calibrate", { method: "POST", body });
    if (!response.ok) throw new Error(await errorMessage(response));
    setStatus("One-label test sent. The black box must stay on a single label.", "ok");
  } catch (error) {
    setStatus(error.message, "err");
  }
}

async function calibrateMedia() {
  if (!els.printer.value) {
    setStatus("Choose a printer first.", "err");
    return;
  }
  const body = new FormData();
  appendShared(body);
  body.append("printer_name", els.printer.value);
  setStatus("Calibrating media — the printer will feed a few labels…");
  try {
    const response = await fetch("/api/media-calibrate", { method: "POST", body });
    if (!response.ok) throw new Error(await errorMessage(response));
    setStatus("Calibration sent. When it stops, press FEED once. It should advance exactly one label.", "ok");
  } catch (error) {
    setStatus(error.message, "err");
  }
}

function buildForm() {
  const body = new FormData();
  if (state.file) body.append("file", state.file);
  appendShared(body);
  body.append("printer_name", els.printer.value);
  return body;
}

function appendShared(body) {
  body.append("preset", els.preset.value);
  body.append("width_in", els.widthIn.value);
  body.append("height_in", els.heightIn.value);
  body.append("fit", els.fit.value);
  body.append("dither", els.dither.value);
  body.append("contrast", els.contrast.value);
  body.append("threshold", els.threshold.value);
  body.append("sharpen", els.sharpen.checked ? "true" : "false");
  body.append("darkness", els.darkness.value);
  body.append("speed", els.speed.value);
  body.append("copies", els.copies.value);
}

async function postForm(url) {
  const response = await fetch(url, { method: "POST", body: buildForm() });
  if (!response.ok) throw new Error(await errorMessage(response));
  return response.json();
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(await errorMessage(response));
  return response.json();
}

async function errorMessage(response) {
  try {
    const data = await response.json();
    return data.detail || response.statusText;
  } catch {
    return response.statusText;
  }
}

function setStatus(message, kind) {
  els.status.textContent = message;
  els.status.className = `status${kind ? ` ${kind}` : ""}`;
}
