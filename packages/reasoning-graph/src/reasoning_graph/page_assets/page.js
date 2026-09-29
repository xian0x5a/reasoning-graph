// Browser behaviour of the reasoning graph page: pan/zoom canvas, edge highlights,
// candidate focus, node popups, filters and navigation. The page embeds its data as
// JSON in #page-data; setupPage() runs at once, setupGraphs() once the graph svg exists.
const pageData = JSON.parse(document.getElementById("page-data").textContent);
const graphEdgeMaps = pageData.graphEdgeMaps;
const candidateFocusMap = pageData.candidateFocusMap;

function validBox(box) {
  return box && Number.isFinite(box.x) && Number.isFinite(box.y) && Number.isFinite(box.width) && Number.isFinite(box.height) && box.width > 1 && box.height > 1;
}

function paddedBox(box, pad = 40) {
  return { x: box.x - pad, y: box.y - pad, width: box.width + pad * 2, height: box.height + pad * 2 };
}

function readViewBox(svg) {
  const raw = svg.getAttribute("viewBox");
  if (!raw) return null;
  const [x, y, width, height] = raw.trim().split(/\s+/).map(Number);
  const box = { x, y, width, height };
  return validBox(box) ? box : null;
}

function contentBox(svg) {
  const boxes = [];
  [svg, ...svg.querySelectorAll("g")].forEach((element) => {
    try {
      const box = element.getBBox();
      if (validBox(box)) boxes.push(box);
    } catch (_) {}
  });
  if (boxes.length) {
    const largest = boxes.sort((a, b) => (b.width * b.height) - (a.width * a.height))[0];
    return paddedBox(largest);
  }
  return readViewBox(svg) || { x: 0, y: 0, width: 1000, height: 700 };
}

function hrefFor(anchor) {
  return anchor.getAttribute("href") || anchor.getAttribute("xlink:href") || anchor.getAttributeNS("http://www.w3.org/1999/xlink", "href") || "";
}

function showNodeModal(detailId) {
  const modal = document.getElementById("node-modal");
  const content = document.getElementById("node-modal-content");
  const title = document.getElementById("node-modal-title");
  const card = document.getElementById(detailId);
  if (!modal || !content || !card) return;
  const clone = card.cloneNode(true);
  clone.removeAttribute("id");
  const header = clone.querySelector("header");
  const code = header?.querySelector("code")?.textContent?.trim();
  const type = header?.querySelector(".pill")?.textContent?.trim();
  if (header) header.remove();
  const bar = modal.querySelector(".modal-bar");
  const closeButton = modal.querySelector("[data-close-modal]");
  bar?.querySelector(".modal-tabs")?.remove();
  const edgeBlock = clone.querySelector(".edge-block");
  if (edgeBlock) {
    const edgeCount = edgeBlock.querySelectorAll("li").length;
    edgeBlock.remove();
    const detailsCard = clone;
    detailsCard.setAttribute("role", "tabpanel");
    detailsCard.dataset.panel = "details";
    const edgesCard = document.createElement("article");
    edgesCard.className = detailsCard.className;
    const nodeType = detailsCard.getAttribute("data-node-type");
    if (nodeType) edgesCard.setAttribute("data-node-type", nodeType);
    edgesCard.setAttribute("role", "tabpanel");
    edgesCard.dataset.panel = "edges";
    edgesCard.hidden = true;
    edgesCard.appendChild(edgeBlock);
    const tabs = document.createElement("div");
    tabs.className = "modal-tabs";
    tabs.setAttribute("role", "tablist");
    tabs.setAttribute("aria-label", "Node card views");
    const detailsTab = document.createElement("button");
    detailsTab.type = "button";
    detailsTab.textContent = "Details";
    detailsTab.setAttribute("role", "tab");
    detailsTab.setAttribute("aria-selected", "true");
    detailsTab.classList.add("active");
    const edgesTab = document.createElement("button");
    edgesTab.type = "button";
    edgesTab.textContent = edgeCount > 0 ? "Edges (" + edgeCount + ")" : "Edges";
    edgesTab.setAttribute("role", "tab");
    edgesTab.setAttribute("aria-selected", "false");
    const selectTab = (name) => {
      const showDetails = name === "details";
      detailsCard.hidden = !showDetails;
      edgesCard.hidden = showDetails;
      detailsTab.classList.toggle("active", showDetails);
      edgesTab.classList.toggle("active", !showDetails);
      detailsTab.setAttribute("aria-selected", String(showDetails));
      edgesTab.setAttribute("aria-selected", String(!showDetails));
    };
    detailsTab.addEventListener("click", () => selectTab("details"));
    edgesTab.addEventListener("click", () => selectTab("edges"));
    tabs.replaceChildren(detailsTab, edgesTab);
    if (bar) {
      if (closeButton) bar.insertBefore(tabs, closeButton);
      else bar.appendChild(tabs);
    }
    content.replaceChildren(detailsCard, edgesCard);
  } else {
    content.replaceChildren(clone);
  }
  title.replaceChildren();
  if (code) {
    const codeEl = document.createElement("code");
    codeEl.textContent = code;
    title.appendChild(codeEl);
  }
  if (type) {
    const typeEl = document.createElement("span");
    typeEl.className = "pill";
    typeEl.textContent = type;
    title.appendChild(typeEl);
  }
  if (!code && !type) title.textContent = "Node details";
  if (typeof modal.showModal === "function") modal.showModal();
  else modal.setAttribute("open", "");
}

function installDetailClicks(section) {
  section.querySelectorAll("a").forEach((anchor) => {
    const href = hrefFor(anchor);
    if (!href.startsWith("#details-")) return;
    anchor.addEventListener("click", (event) => {
      event.preventDefault();
      showNodeModal(href.slice(1));
    });
  });
}

function normalizeMermaidKey(value) {
  return String(value || "").replace(/^flowchart-/, "").replace(/-\d+$/, "");
}

function connectedNodeKeys(edge, fallback) {
  const classes = Array.from(edge.classList || []);
  const source = classes.find((item) => item.startsWith("LS-"))?.slice(3);
  const target = classes.find((item) => item.startsWith("LE-"))?.slice(3);
  if (source && target) return [normalizeMermaidKey(source), normalizeMermaidKey(target)];
  const id = edge.getAttribute("id") || "";
  const match = id.match(/^L[-_](.+)[-_]([^_-]+)[-_]\d+$/);
  if (match) return [normalizeMermaidKey(match[1]), normalizeMermaidKey(match[2])];
  return fallback ? [normalizeMermaidKey(fallback.from), normalizeMermaidKey(fallback.to)] : [];
}

function edgeContainerFor(target) {
  if (!target || !target.closest) return null;
  return target.closest("path.flowchart-link, path.edge-hitbox, path[class*='LS-'][class*='LE-'], path[id^='L-'], g.edgePath, .edgePath, g.edge-path, .edge-path");
}

function uniqueElements(items) {
  return Array.from(new Set(items.filter(Boolean)));
}

function edgeElements(svg) {
  return uniqueElements(
    Array.from(svg.querySelectorAll("path.flowchart-link, path[class*='LS-'][class*='LE-'], path[id^='L-'], g.edgePath, .edgePath, g.edge-path, .edge-path"))
      .filter((item) => !item.classList.contains("edge-hitbox"))
      .map((item) => item.matches?.("path") ? item : (item.closest?.("g") || item))
  );
}

function edgeLabels(svg) {
  const labelGroups = Array.from(svg.querySelectorAll(".edgeLabels"));
  return labelGroups.flatMap((group) =>
    Array.from(group.children).filter((child) => child.classList?.contains("edgeLabel"))
  );
}

function nodeElementFor(element) {
  if (!element) return null;
  return element.querySelector?.("g.node") || element.closest?.("g.node") || element.closest?.("g") || element;
}

function addEdgeHitbox(edge) {
  const path = edge.matches?.("path") ? edge : edge.querySelector("path:not(.edge-hitbox)");
  if (!path) return null;
  const existing = edge.matches?.("path")
    ? path.parentNode?.querySelector(`.edge-hitbox[data-edge-for="${path.id}"]`)
    : edge.querySelector(".edge-hitbox");
  if (existing) return existing;
  const hitbox = path.cloneNode(false);
  hitbox.removeAttribute("marker-end");
  hitbox.removeAttribute("marker-start");
  hitbox.classList.add("edge-hitbox");
  if (path.id) hitbox.dataset.edgeFor = path.id;
  path.parentNode.insertBefore(hitbox, path);
  return hitbox;
}

function graphNodes(svg) {
  const nodes = new Map();
  const remember = (key, node) => {
    const normalized = normalizeMermaidKey(key);
    if (normalized && node && !nodes.has(normalized)) nodes.set(normalized, node);
  };
  svg.querySelectorAll("a").forEach((anchor) => {
    const href = hrefFor(anchor);
    if (!href.startsWith("#details-")) return;
    const key = href.replace(/^#details-/, "");
    remember(key, nodeElementFor(anchor));
  });
  svg.querySelectorAll("g.node").forEach((node) => {
    if (node.id) remember(node.id, node);
    const firstLine = (node.textContent || "").trim().split(/\s+/)[0];
    remember(firstLine, node);
  });
  svg.querySelectorAll("g[id]").forEach((node) => remember(node.id, node));
  return nodes;
}

function setupEdgeHighlights(section) {
  const svg = section.querySelector("svg");
  const canvas = section.querySelector(".graph-canvas");
  if (!svg || !canvas) return;
  const edgeMap = graphEdgeMaps[canvas.id] || [];
  const nodes = graphNodes(svg);
  const edges = edgeElements(svg);
  let hoveredEdge = null;
  let pinnedEdge = null;

  const clearClasses = () => {
    edges.forEach((edge) => edge.classList.remove("edge-hover", "edge-pinned"));
    nodes.forEach((node) => node.classList.remove("node-connected"));
  };
  const render = () => {
    clearClasses();
    const activeEdges = new Set([hoveredEdge, pinnedEdge].filter(Boolean));
    activeEdges.forEach((edge) => {
      edge.classList.toggle("edge-hover", edge === hoveredEdge && edge !== pinnedEdge);
      edge.classList.toggle("edge-pinned", edge === pinnedEdge);
      const fallback = edgeMap[edges.indexOf(edge)];
      connectedNodeKeys(edge, fallback).forEach((key) => {
        const node = nodes.get(key);
        if (node) node.classList.add("node-connected");
      });
    });
  };
  const clearPinned = () => { pinnedEdge = null; render(); };
  canvas.addEventListener("clear-graph-selection", clearPinned);

  edges.forEach((edge, index) => {
    const hitbox = addEdgeHitbox(edge);
    const fallback = edgeMap[index];
    if (fallback) edge.setAttribute("aria-label", `${fallback.from} to ${fallback.to}`);
    const targets = uniqueElements([edge, hitbox]);
    targets.forEach((target) => {
      target.addEventListener("mouseenter", () => { hoveredEdge = edge; render(); });
      target.addEventListener("mouseleave", () => { if (hoveredEdge === edge) hoveredEdge = null; render(); });
      target.addEventListener("pointerdown", (event) => event.stopPropagation());
      target.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        pinnedEdge = pinnedEdge === edge ? null : edge;
        render();
      });
    });
  });
  // Keep edge selection sticky while inspecting nodes/background.
  // Only edge clicks replace/toggle it; Escape remains keyboard escape hatch.
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") clearPinned(); });
}

function graphSectionForControl(control) {
  return control.closest(".graph-section");
}

function clearCandidateFocus(section) {
  const scope = section || document;
  scope.querySelectorAll(".graph-canvas.focus-active").forEach((canvas) => {
    canvas.classList.remove("focus-active");
    canvas.dispatchEvent(new CustomEvent("clear-graph-selection"));
  });
  scope.querySelectorAll(".node-focused, .edge-focused").forEach((element) => element.classList.remove("node-focused", "edge-focused"));
  scope.querySelectorAll("[data-candidate-focus-select]").forEach((select) => { select.value = ""; });
}

function applyCandidateFocus(section, candidateKey) {
  const focusNodes = new Set((candidateFocusMap[candidateKey] || [candidateKey]).map(normalizeMermaidKey));
  clearCandidateFocus(section);
  section.querySelectorAll("[data-candidate-focus-select]").forEach((select) => { select.value = candidateKey || ""; });
  section.querySelectorAll(".graph-canvas").forEach((canvas) => {
    const svg = canvas.querySelector("svg");
    if (!svg) return;
    const nodes = graphNodes(svg);
    let matched = false;
    nodes.forEach((node, key) => {
      if (focusNodes.has(key)) {
        const targetNode = nodeElementFor(node);
        if (targetNode) targetNode.classList.add("node-focused");
        node.classList.add("node-focused");
        matched = true;
      }
    });
    const edges = edgeElements(svg);
    const labels = edgeLabels(svg);
    const edgeMap = graphEdgeMaps[canvas.id] || [];
    edges.forEach((edge, index) => {
      const fallback = edgeMap[index];
      const endpoints = connectedNodeKeys(edge, fallback);
      if (endpoints.length >= 2 && endpoints.every((key) => focusNodes.has(key))) {
        edge.classList.add("edge-focused");
        const label = labels[index];
        if (label) label.classList.add("edge-focused");
        matched = true;
      }
    });
    canvas.classList.toggle("focus-active", matched);
  });
}

function setupCandidateFocus() {
  document.querySelectorAll("[data-candidate-focus-select]").forEach((select) => {
    select.addEventListener("change", () => {
      const section = graphSectionForControl(select);
      if (!section) return;
      const candidateKey = select.value || "";
      if (!candidateKey) clearCandidateFocus(section);
      else applyCandidateFocus(section, candidateKey);
    });
  });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") clearCandidateFocus(); });
}

// A graph opens fitted to the canvas width, never above its natural size, and the canvas
// grows as tall as that takes, up to a few screens. Fitted to a fixed-height canvas, a
// graph with a long column of observations opened too small to read. The page scroll
// still passes over the canvas, so a tall canvas reads like a tall figure.
const MAX_CANVAS_SCREENS = 2;

function fitCanvasHeight(canvas, box) {
  const scale = Math.min(1, canvas.clientWidth / box.width);
  const minHeight = parseFloat(getComputedStyle(canvas).minHeight) || 0;
  const height = Math.min(Math.max(box.height * scale, minHeight), window.innerHeight * MAX_CANVAS_SCREENS);
  canvas.style.height = `${Math.round(height)}px`;
}

function setupPanZoom(canvas) {
  const svg = canvas.querySelector("svg");
  if (!svg) return;
  svg.removeAttribute("width");
  svg.removeAttribute("height");
  svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
  svg.style.width = "100%";
  svg.style.height = "100%";

  let box = contentBox(svg);
  fitCanvasHeight(canvas, box);
  // Zoom stays between the fitted content box and a fixed zoom-in limit. Panning is
  // deliberately unbounded: the graph can be dragged right off the canvas the same
  // way the window can be scrolled away from a document, and "Reset view" brings it
  // back. Do not clamp box.x/box.y here, dragging with no limit is the intended feel.
  const bounds = { ...box };
  const initial = { ...box };
  const maxZoom = 50;
  const minWidth = bounds.width / maxZoom;
  const minHeight = bounds.height / maxZoom;

  const apply = () => svg.setAttribute("viewBox", `${box.x} ${box.y} ${box.width} ${box.height}`);
  apply();

  function clientPointInSvg(event) {
    const matrix = svg.getScreenCTM();
    if (matrix && svg.createSVGPoint) {
      const point = svg.createSVGPoint();
      point.x = event.clientX;
      point.y = event.clientY;
      return point.matrixTransform(matrix.inverse());
    }
    const rect = svg.getBoundingClientRect();
    return {
      x: box.x + ((event.clientX - rect.left) / Math.max(rect.width, 1)) * box.width,
      y: box.y + ((event.clientY - rect.top) / Math.max(rect.height, 1)) * box.height,
    };
  }

  function clientDeltaInSvg(dx, dy) {
    const matrix = svg.getScreenCTM();
    if (matrix) {
      const scaleX = Math.hypot(matrix.a, matrix.b);
      const scaleY = Math.hypot(matrix.c, matrix.d);
      if (scaleX > 0 && scaleY > 0) return { x: dx / scaleX, y: dy / scaleY };
    }
    const rect = svg.getBoundingClientRect();
    return {
      x: dx / Math.max(rect.width, 1) * box.width,
      y: dy / Math.max(rect.height, 1) * box.height,
    };
  }

  let canvasMode = false;
  const modifierPressed = (event) => event.ctrlKey || event.metaKey;
  const canUseCanvasDirectly = () => canvasMode;
  const canPan = (event) => canUseCanvasDirectly() || modifierPressed(event) || event.button === 1;
  const clearTextSelection = () => {
    const selection = window.getSelection && window.getSelection();
    if (selection && selection.rangeCount) selection.removeAllRanges();
  };

  canvas.addEventListener("wheel", (event) => {
    // Focus is the opt-in for wheel zoom: anywhere else the wheel keeps scrolling
    // the page, and a scroll that merely passes over the canvas does not zoom it.
    if (!canvas.contains(document.activeElement)) return;
    if (!canUseCanvasDirectly() && !modifierPressed(event)) return;
    event.preventDefault();
    const focus = clientPointInSvg(event);
    const factor = event.deltaY > 0 ? 1.14 : 0.88;
    const nextWidth = Math.min(Math.max(box.width * factor, minWidth), bounds.width);
    const nextHeight = Math.min(Math.max(box.height * factor, minHeight), bounds.height);
    box.x = focus.x - (focus.x - box.x) * (nextWidth / box.width);
    box.y = focus.y - (focus.y - box.y) * (nextHeight / box.height);
    box.width = nextWidth;
    box.height = nextHeight;
    apply();
  }, { passive: false });

  let dragging = false;
  let lastX = 0;
  let lastY = 0;
  function endDrag() {
    if (!dragging) return;
    dragging = false;
    canvas.classList.remove("panning");
    clearTextSelection();
  }
  canvas.addEventListener("pointerdown", (event) => {
    // Node links keep their own focus; anywhere else on the canvas claims the wheel.
    if (event.target.closest && event.target.closest("a")) return;
    canvas.focus({ preventScroll: true });
    if (edgeContainerFor(event.target)) return;
    if (!canPan(event)) return;
    event.preventDefault();
    clearTextSelection();
    dragging = true;
    lastX = event.clientX;
    lastY = event.clientY;
    canvas.classList.add("panning");
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    event.preventDefault();
    const delta = clientDeltaInSvg(event.clientX - lastX, event.clientY - lastY);
    box.x -= delta.x;
    box.y -= delta.y;
    lastX = event.clientX;
    lastY = event.clientY;
    apply();
  });
  canvas.addEventListener("pointerup", endDrag);
  canvas.addEventListener("pointercancel", endDrag);
  canvas.addEventListener("lostpointercapture", endDrag);

  const reset = document.querySelector(`[data-reset="${canvas.id}"]`);
  if (reset) reset.addEventListener("click", () => { box = { ...initial }; apply(); });

  const modeToggle = document.querySelector(`[data-canvas-mode="${canvas.id}"]`);
  function setCanvasMode(enabled) {
    canvasMode = enabled;
    canvas.classList.toggle("canvas-mode", canvasMode);
    // The pressed style carries the state; the label must not grow, or the button
    // reflows into two rows and the control bar jumps.
    if (modeToggle) modeToggle.setAttribute("aria-pressed", String(canvasMode));
    if (!canvasMode) endDrag();
  }
  if (modeToggle) modeToggle.addEventListener("click", () => setCanvasMode(!canvasMode));
  // Default on for mouse/trackpad only: wheel zoom still waits for a click on the
  // canvas, so the page is never hijacked. On touch screens canvas mode sets
  // touch-action:none and would trap page swipes over the tall canvas.
  setCanvasMode(window.matchMedia("(pointer: fine)").matches);
  // Esc releases the captured wheel so the page scrolls again under the pointer.
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && canvas.contains(document.activeElement)) document.activeElement.blur();
  });
}

function setupFilters() {
  const buttons = document.querySelectorAll("[data-filter]");
  const cards = document.querySelectorAll("#node-details-section .detail-card");
  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      const filter = button.getAttribute("data-filter") || "all";
      buttons.forEach((item) => item.classList.toggle("active", item === button));
      cards.forEach((card) => {
        const type = card.getAttribute("data-node-type") || "";
        card.hidden = filter !== "all" && type !== filter;
      });
    });
  });
  const allButton = document.querySelector('[data-filter="all"]');
  if (allButton) allButton.classList.add("active");
}

function closeModal(modal) {
  if (modal.close) modal.close();
  else modal.removeAttribute("open");
}

function setupFloatingNav() {
  const nav = document.querySelector(".floating-nav");
  const toggle = nav?.querySelector(".nav-toggle");
  if (!nav || !toggle) return;
  toggle.addEventListener("click", () => {
    const open = !nav.classList.contains("open");
    nav.classList.toggle("open", open);
    toggle.setAttribute("aria-expanded", String(open));
  });
  nav.querySelectorAll("a").forEach((link) => link.addEventListener("click", () => {
    nav.classList.remove("open");
    toggle.setAttribute("aria-expanded", "false");
  }));
  document.addEventListener("click", (event) => {
    if (!nav.contains(event.target)) {
      nav.classList.remove("open");
      toggle.setAttribute("aria-expanded", "false");
    }
  });
}

function setupModal() {
  const modal = document.getElementById("node-modal");
  if (!modal) return;
  modal.querySelector("[data-close-modal]")?.addEventListener("click", () => closeModal(modal));
  modal.addEventListener("click", (event) => {
    if (event.target === modal) closeModal(modal);
  });
}

function runSetup(label, callback) {
  try {
    callback();
  } catch (error) {
    console.warn(`${label} setup failed`, error);
  }
}

function setupPage() {
  document.querySelectorAll(".case-section").forEach((section) => runSetup("case links", () => installDetailClicks(section)));
  runSetup("filters", setupFilters);
  runSetup("modal", setupModal);
  runSetup("floating nav", setupFloatingNav);
}

function setupGraphs() {
  document.querySelectorAll(".graph-section").forEach((section) => {
    const canvas = section.querySelector(".graph-canvas");
    if (canvas) runSetup("pan/zoom", () => setupPanZoom(canvas));
    runSetup("node detail clicks", () => installDetailClicks(section));
    runSetup("edge highlights", () => setupEdgeHighlights(section));
  });
  runSetup("candidate focus", setupCandidateFocus);
}
