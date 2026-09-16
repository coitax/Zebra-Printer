const state = {
  file: null,
  zoom: "fit",
  previewTimer: null,
  sourceImage: null,
  crop: { left: 0, top: 0, right: 1, bottom: 1 },
  detectedCrop: null,
  suggestedPreset: null,
  labelLike: false,
  drag: null,
  page: 1,
  pages: 1,
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
  cropBtn: document.getElementById("cropBtn"),
  resetCropBtn: document.getElementById("resetCropBtn"),
  cropBox: document.getElementById("cropBox"),
  cropCanvas: document.getElementById("cropCanvas"),
  lockAspect: document.getElementById("lockAspect"),
  pageRow: document.getElementById("pageRow"),
  pdfPage: document.getElementById("pdfPage"),
  pdfPageCount: document.getElementById("pdfPageCount"),
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
    document.addEventListener(eventName, (event) => {
      event.preventDefault();
      if (hasFiles(event)) els.dropzone.classList.add("drag");
    });
  });
  document.addEventListener("dragleave", (event) => {
    if (!event.relatedTarget) els.dropzone.classList.remove("drag");
  });
  document.addEventListener("drop", (event) => {
    event.preventDefault();
    els.dropzone.classList.remove("drag");
    const file = event.dataTransfer?.files?.[0];
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
      state.zoom = button.dataset.zoom === "fit" ? "fit" : Number(button.dataset.zoom);
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
  els.cropBtn.addEventListener("click", () => applyDetectedCrop({ preview: true }));
  els.resetCropBtn.addEventListener("click", () => resetCrop());
  els.lockAspect.addEventListener("change", () => {
    if (els.lockAspect.checked) applyAspectToCrop();
    drawCropper();
    queuePreview();
  });
  els.pdfPage.addEventListener("change", () => {
    if (!state.file) return;
    state.page = Math.max(1, Math.min(state.pages, Number(els.pdfPage.value) || 1));
    els.pdfPage.value = String(state.page);
    loadSourceImage(state.file);
  });
  els.preset.addEventListener("change", () => {
    if (els.lockAspect.checked && state.sourceImage) fitCurrentCropToAspect();
    drawCropper();
    queuePreview();
  });
  bindCropper();
}

async function loadPresets() {
  const data = await fetchJson("/api/presets");
  const defaultPreset = data.default || "4x6";
  els.preset.innerHTML = "";
  for (const preset of data.presets) {
    const option = document.createElement("option");
    option.value = preset.id;
    option.dataset.widthIn = String(preset.width_in);
    option.dataset.heightIn = String(preset.height_in);
    option.textContent = `${preset.label} · ${Math.round(preset.width_in * 203)}×${Math.round(preset.height_in * 203)} dots`;
    if (preset.id === defaultPreset) option.selected = true;
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

function hasFiles(event) {
  return Array.from(event.dataTransfer?.types || []).includes("Files");
}

function isSupportedFile(file) {
  if (isPdfFile(file) || (file.type && file.type.startsWith("image/"))) return true;
  if (file.type === "application/octet-stream" || !file.type) return true;
  return /\.(png|jpe?g|webp|gif|bmp|tif{1,2}|pdf)$/i.test(file.name);
}

async function setFile(file) {
  if (!(await looksLikePrintFile(file))) {
    setStatus("Drop a PDF or image (PNG, JPEG, WebP, TIFF).", "err");
    return;
  }
  state.file = file;
  state.page = 1;
  state.pages = 1;
  state.detectedCrop = null;
  state.suggestedPreset = null;
  state.labelLike = false;
  els.pdfPage.value = "1";
  els.fileName.textContent = file.name || "Dropped file";
  els.printBtn.disabled = false;
  els.zplBtn.disabled = false;
  els.cropBtn.disabled = false;
  els.resetCropBtn.disabled = false;
  loadRenderedSource(file);
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
      const fillPct = Math.round((data.ink_fill_ratio || 0) * 100);
      if (data.low_ink_fill) {
        els.fitBadge.textContent = `Ink covers ~${fillPct}% of label height — may look smaller than ${data.height_in.toFixed(2)}". Try Cover fit or adjust crop.`;
        els.fitBadge.className = "fit-badge err";
        setStatus("Preview letterboxes on the label. Switch to Cover or recrop to fill 4×6.", "err");
      } else {
        els.fitBadge.textContent = `Fits one ${data.width_in.toFixed(2)}" × ${data.height_in.toFixed(2)}" label. Bitmap is ${data.bitmap_width}×${data.bitmap_height} dots.`;
        els.fitBadge.className = "fit-badge ok";
        setStatus("Preview is one label. If a print still crosses a gap, calibrate media first.", "ok");
      }
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
  img.onload = () => applyZoom();
  img.src = `data:image/png;base64,${b64}`;
  img.hidden = false;
  const placeholder = img.parentElement.querySelector(".placeholder");
  if (placeholder) placeholder.hidden = true;
  applyZoom();
}

function applyZoom() {
  [els.originalPreview, els.printPreview].forEach((img) => {
    if (!img.naturalWidth) return;
    if (state.zoom === "fit") {
      img.classList.add("fit");
      img.classList.remove("dots");
      img.style.width = "";
      img.style.height = "";
      return;
    }
    img.classList.remove("fit");
    img.classList.add("dots");
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
  const copies = Math.max(1, Number(els.copies.value) || 1);
  setStatus(copies > 1 ? `Printing ${copies} stickers with a cooldown…` : "Sending raw ZPL…");
  els.printBtn.disabled = true;
  try {
    await postForm(url);
    setStatus(
      copies > 1
        ? `Printed ${copies} stickers with a pause between each.`
        : successText,
      "ok"
    );
  } catch (error) {
    setStatus(error.message, "err");
  } finally {
    els.printBtn.disabled = !state.file;
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
    setStatus("One-label test sent. The black box must stay on a single 4×4 sticker.", "ok");
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
  body.append(
    "crop",
    `${state.crop.left},${state.crop.top},${state.crop.right},${state.crop.bottom}`
  );
  body.append("page", String(state.page));
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

function isPdfFile(file) {
  return file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
}

async function looksLikePrintFile(file) {
  if (isSupportedFile(file) || isPdfFile(file)) return true;
  return (await sniffKind(file)) !== "unknown";
}

async function sniffKind(file) {
  try {
    const header = new Uint8Array(await file.slice(0, 8).arrayBuffer());
    if (header[0] === 0x25 && header[1] === 0x50 && header[2] === 0x44 && header[3] === 0x46) {
      return "pdf";
    }
    if (header[0] === 0x89 && header[1] === 0x50 && header[2] === 0x4e && header[3] === 0x47) return "image";
    if (header[0] === 0xff && header[1] === 0xd8) return "image";
    if (header[0] === 0x47 && header[1] === 0x49 && header[2] === 0x46) return "image";
    if (header[0] === 0x42 && header[1] === 0x4d) return "image";
    if ((header[0] === 0x49 && header[1] === 0x49) || (header[0] === 0x4d && header[1] === 0x4d)) return "image";
    if (header[0] === 0x52 && header[1] === 0x49 && header[2] === 0x46 && header[3] === 0x46) return "image";
  } catch {
    return "unknown";
  }
  return "unknown";
}

function loadSourceImage(file) {
  loadRenderedSource(file);
}

async function loadRenderedSource(file) {
  setStatus("Reading file…");
  const body = new FormData();
  body.append("file", file);
  body.append("page", String(state.page));
  try {
    const response = await fetch("/api/source", { method: "POST", body });
    if (!response.ok) throw new Error(await errorMessage(response));
    const data = await response.json();
    setPageControls(data.page, data.pages);
    const image = new Image();
    image.onload = () => {
      state.sourceImage = image;
      applySourceSuggestions(data);
      showCropper();
      queuePreview();
      if (state.labelLike) {
        setStatus("Found the 4×6 shipping label. It will fill the sticker. Drag the crop box if needed.", "ok");
      } else {
        setStatus("File ready. Crop if you need to, then print.", "ok");
      }
    };
    image.onerror = () => {
      setStatus("The server read the file, but the preview image failed to load.", "err");
    };
    image.src = `data:image/png;base64,${data.png}`;
  } catch (error) {
    setStatus(error.message, "err");
  }
}

function setPageControls(page, pages) {
  state.page = page;
  state.pages = pages;
  els.pdfPage.value = String(page);
  els.pdfPage.max = String(pages);
  els.pdfPageCount.textContent = pages > 1 ? `of ${pages}` : "";
  els.pageRow.classList.toggle("hidden", pages <= 1);
}

function showCropper() {
  if (!state.sourceImage) return;
  els.cropBox.classList.remove("hidden");
  sizeCropCanvas();
  drawCropper();
}

function cropFromList(values) {
  if (!values || values.length !== 4) return null;
  const [left, top, right, bottom] = values.map(Number);
  if ([left, top, right, bottom].some((value) => Number.isNaN(value))) return null;
  return { left, top, right, bottom };
}

function applySourceSuggestions(data) {
  state.detectedCrop = cropFromList(data.crop);
  state.suggestedPreset = data.suggested_preset || "4x6";
  state.labelLike = Boolean(data.label_like);
  const presetId = state.suggestedPreset;
  if (presetId && [...els.preset.options].some((option) => option.value === presetId)) {
    els.preset.value = presetId;
  } else {
    els.preset.value = "4x6";
  }
  els.customSize.classList.toggle("hidden", els.preset.value !== "custom");
  if (state.labelLike) {
    els.fit.value = cropMatchesPreset() ? "cover" : "contain";
    els.dither.value = "threshold";
    els.contrast.value = "1";
    els.contrastValue.textContent = "1.00";
    els.sharpen.checked = false;
    updateThresholdVisibility();
  }
  if (state.detectedCrop) {
    state.crop = { ...state.detectedCrop };
    if (els.lockAspect.checked) fitCurrentCropToAspect();
  } else {
    resetCrop({ preview: false });
  }
  drawCropper();
}

function applyDetectedCrop({ preview = true } = {}) {
  if (!state.sourceImage) return;
  if (state.detectedCrop) {
    state.crop = { ...state.detectedCrop };
    if (state.suggestedPreset) els.preset.value = state.suggestedPreset;
    if (els.lockAspect.checked) fitCurrentCropToAspect();
    showCropper();
    if (preview) queuePreview();
    setStatus("Auto-cropped to the shipping label.", "ok");
    return;
  }
  if (state.file) loadSourceImage(state.file);
}

function resetCrop({ preview = true } = {}) {
  if (els.lockAspect.checked && state.sourceImage) {
    applyAspectToCrop();
  } else {
    state.crop = { left: 0, top: 0, right: 1, bottom: 1 };
  }
  drawCropper();
  if (preview) queuePreview();
}

function labelAspect() {
  const width = Number(els.preset.value === "custom" ? els.widthIn.value : currentPresetInches().width);
  const height = Number(els.preset.value === "custom" ? els.heightIn.value : currentPresetInches().height);
  if (!width || !height) return 1;
  return width / height;
}

function cropMatchesPreset() {
  if (!state.detectedCrop || !state.sourceImage) return false;
  const cropW = (state.detectedCrop.right - state.detectedCrop.left) * state.sourceImage.width;
  const cropH = (state.detectedCrop.bottom - state.detectedCrop.top) * state.sourceImage.height;
  if (cropW < 8 || cropH < 8) return false;
  const cropAspect = cropW / cropH;
  const labelAsp = labelAspect();
  const tolerance = 0.12;
  return (
    Math.abs(cropAspect - labelAsp) <= tolerance ||
    Math.abs(cropAspect - 1 / labelAsp) <= tolerance
  );
}

function currentPresetInches() {
  const option = els.preset.selectedOptions[0];
  if (!option || els.preset.value === "custom") {
    return { width: Number(els.widthIn.value) || 4, height: Number(els.heightIn.value) || 6 };
  }
  return {
    width: Number(option.dataset.widthIn) || 4,
    height: Number(option.dataset.heightIn) || 4,
  };
}

function applyAspectToCrop() {
  if (!state.sourceImage) return;
  const { width, height } = largestAspectBox();
  const left = (1 - width) / 2;
  const top = (1 - height) / 2;
  state.crop = { left, top, right: left + width, bottom: top + height };
}

function largestAspectBox() {
  const aspect = labelAspect();
  const imageAspect = state.sourceImage.width / state.sourceImage.height;
  if (imageAspect > aspect) {
    return { width: aspect / imageAspect, height: 1 };
  }
  return { width: 1, height: imageAspect / aspect };
}

function fitCurrentCropToAspect() {
  if (!state.sourceImage) return;
  const aspect = labelAspect();
  const imageAspect = state.sourceImage.width / state.sourceImage.height;
  const target = aspect / imageAspect;
  const current = state.crop;
  const isFull =
    current.left <= 0.001 && current.top <= 0.001 && current.right >= 0.999 && current.bottom >= 0.999;
  if (isFull) {
    applyAspectToCrop();
    return;
  }
  let width = current.right - current.left;
  let height = current.bottom - current.top;
  const centerX = (current.left + current.right) / 2;
  const centerY = (current.top + current.bottom) / 2;
  if (width / height < target) {
    width = height * target;
  } else {
    height = width / target;
  }
  if (width > 1) {
    height *= 1 / width;
    width = 1;
  }
  if (height > 1) {
    width *= 1 / height;
    height = 1;
  }
  const left = clamp(centerX - width / 2, 0, 1 - width);
  const top = clamp(centerY - height / 2, 0, 1 - height);
  state.crop = { left, top, right: left + width, bottom: top + height };
}

function sizeCropCanvas() {
  const canvas = els.cropCanvas;
  const image = state.sourceImage;
  if (!image) return;
  canvas.width = 320;
  canvas.height = 220;
}

function cropLayout() {
  const canvas = els.cropCanvas;
  const image = state.sourceImage;
  const scale = Math.min(canvas.width / image.width, canvas.height / image.height);
  const drawW = image.width * scale;
  const drawH = image.height * scale;
  const offsetX = (canvas.width - drawW) / 2;
  const offsetY = (canvas.height - drawH) / 2;
  return { scale, drawW, drawH, offsetX, offsetY };
}

function cropRect() {
  const { scale, offsetX, offsetY } = cropLayout();
  const image = state.sourceImage;
  return {
    x: offsetX + state.crop.left * image.width * scale,
    y: offsetY + state.crop.top * image.height * scale,
    w: (state.crop.right - state.crop.left) * image.width * scale,
    h: (state.crop.bottom - state.crop.top) * image.height * scale,
  };
}

function drawCropper() {
  const canvas = els.cropCanvas;
  const image = state.sourceImage;
  if (!canvas || !image) return;
  const ctx = canvas.getContext("2d");
  const { offsetX, offsetY, drawW, drawH } = cropLayout();
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#0c0a08";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(image, offsetX, offsetY, drawW, drawH);
  const rect = cropRect();
  ctx.fillStyle = "rgba(12, 10, 8, 0.55)";
  ctx.fillRect(offsetX, offsetY, drawW, drawH);
  ctx.clearRect(rect.x, rect.y, rect.w, rect.h);
  ctx.drawImage(
    image,
    state.crop.left * image.width,
    state.crop.top * image.height,
    (state.crop.right - state.crop.left) * image.width,
    (state.crop.bottom - state.crop.top) * image.height,
    rect.x,
    rect.y,
    rect.w,
    rect.h
  );
  ctx.strokeStyle = "#e3a008";
  ctx.lineWidth = 2;
  ctx.strokeRect(rect.x + 1, rect.y + 1, rect.w - 2, rect.h - 2);
  ctx.fillStyle = "#e3a008";
  for (const handle of handlePoints(rect)) {
    ctx.fillRect(handle.x - 5, handle.y - 5, 10, 10);
  }
}

function handlePoints(rect) {
  return [
    { id: "nw", x: rect.x, y: rect.y },
    { id: "n", x: rect.x + rect.w / 2, y: rect.y },
    { id: "ne", x: rect.x + rect.w, y: rect.y },
    { id: "e", x: rect.x + rect.w, y: rect.y + rect.h / 2 },
    { id: "se", x: rect.x + rect.w, y: rect.y + rect.h },
    { id: "s", x: rect.x + rect.w / 2, y: rect.y + rect.h },
    { id: "sw", x: rect.x, y: rect.y + rect.h },
    { id: "w", x: rect.x, y: rect.y + rect.h / 2 },
  ];
}

function bindCropper() {
  const canvas = els.cropCanvas;
  canvas.addEventListener("pointerdown", onCropPointerDown);
  window.addEventListener("pointermove", onCropPointerMove);
  window.addEventListener("pointerup", onCropPointerUp);
  window.addEventListener("resize", () => {
    if (!state.sourceImage || els.cropBox.classList.contains("hidden")) return;
    sizeCropCanvas();
    drawCropper();
  });
}

function canvasPoint(event) {
  const bounds = els.cropCanvas.getBoundingClientRect();
  const scaleX = els.cropCanvas.width / bounds.width;
  const scaleY = els.cropCanvas.height / bounds.height;
  return {
    x: (event.clientX - bounds.left) * scaleX,
    y: (event.clientY - bounds.top) * scaleY,
  };
}

function hitHandle(point) {
  const rect = cropRect();
  for (const handle of handlePoints(rect)) {
    if (Math.abs(point.x - handle.x) <= 12 && Math.abs(point.y - handle.y) <= 12) {
      return handle.id;
    }
  }
  if (
    point.x >= rect.x &&
    point.x <= rect.x + rect.w &&
    point.y >= rect.y &&
    point.y <= rect.y + rect.h
  ) {
    return "move";
  }
  return null;
}

function onCropPointerDown(event) {
  if (!state.sourceImage) return;
  const point = canvasPoint(event);
  const handle = hitHandle(point);
  if (!handle) return;
  event.preventDefault();
  els.cropCanvas.setPointerCapture(event.pointerId);
  state.drag = { handle, start: point, crop: { ...state.crop } };
}

function onCropPointerMove(event) {
  if (!state.drag || !state.sourceImage) return;
  const point = canvasPoint(event);
  const { scale } = cropLayout();
  const dx = (point.x - state.drag.start.x) / (state.sourceImage.width * scale);
  const dy = (point.y - state.drag.start.y) / (state.sourceImage.height * scale);
  applyCropDrag(state.drag.handle, state.drag.crop, dx, dy);
  drawCropper();
}

function onCropPointerUp() {
  if (!state.drag) return;
  state.drag = null;
  queuePreview();
}

function applyCropDrag(handle, start, dx, dy) {
  let { left, top, right, bottom } = start;
  const aspect = labelAspect();
  const imageAspect = state.sourceImage.width / state.sourceImage.height;
  const lock = els.lockAspect.checked;

  if (handle === "move") {
    const width = right - left;
    const height = bottom - top;
    left = clamp(left + dx, 0, 1 - width);
    top = clamp(top + dy, 0, 1 - height);
    state.crop = { left, top, right: left + width, bottom: top + height };
    return;
  }

  if (handle.includes("w")) left = clamp(left + dx, 0, right - 0.04);
  if (handle.includes("e")) right = clamp(right + dx, left + 0.04, 1);
  if (handle.includes("n")) top = clamp(top + dy, 0, bottom - 0.04);
  if (handle.includes("s")) bottom = clamp(bottom + dy, top + 0.04, 1);

  if (lock) {
    const target = aspect / imageAspect;
    const width = right - left;
    const height = bottom - top;
    let nextW = width;
    let nextH = height;
    if (handle === "n" || handle === "s") {
      nextW = height * target;
    } else if (handle === "e" || handle === "w") {
      nextH = width / target;
    } else {
      nextH = width / target;
    }
    if (handle.includes("e")) right = left + nextW;
    if (handle.includes("w")) left = right - nextW;
    if (handle.includes("s")) bottom = top + nextH;
    if (handle.includes("n")) top = bottom - nextH;
    if (left < 0) {
      right -= left;
      left = 0;
    }
    if (top < 0) {
      bottom -= top;
      top = 0;
    }
    if (right > 1) {
      left -= right - 1;
      right = 1;
    }
    if (bottom > 1) {
      top -= bottom - 1;
      bottom = 1;
    }
  }

  state.crop = {
    left: clamp(left, 0, 1),
    top: clamp(top, 0, 1),
    right: clamp(right, 0, 1),
    bottom: clamp(bottom, 0, 1),
  };
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}
