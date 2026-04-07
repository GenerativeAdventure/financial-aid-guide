/**
 * graph-viz.js — vis-network wrapper for the FSA knowledge graph
 * Exposes: GraphViz.init(), GraphViz.loadFull(), GraphViz.highlight(nodeIds)
 */

const GraphViz = (() => {
  // Community → color palette (matches community IDs 0-13 + overflow)
  const PALETTE = [
    "#4f7ef8", "#34d399", "#fbbf24", "#f87171",
    "#a78bfa", "#38bdf8", "#fb923c", "#e879f9",
    "#4ade80", "#facc15", "#60a5fa", "#f472b6",
    "#2dd4bf", "#818cf8", "#94a3b8", "#c084fc",
  ];

  const communityColor = (id) => PALETTE[(id ?? 0) % PALETTE.length];

  let network = null;
  let allNodes = new vis.DataSet();
  let allEdges = new vis.DataSet();
  let highlightedIds = new Set();

  function init() {
    const container = document.getElementById("graph-container");
    const data = { nodes: allNodes, edges: allEdges };
    const options = {
      nodes: {
        shape: "dot",
        size: 10,
        font: { size: 11, color: "#c8cadc", face: "-apple-system, sans-serif" },
        borderWidth: 1.5,
        chosen: true,
      },
      edges: {
        width: 1,
        color: { color: "#2e3248", highlight: "#4f7ef8", hover: "#6b95ff" },
        smooth: { type: "continuous", roundness: 0.2 },
        arrows: { to: { enabled: true, scaleFactor: 0.4 } },
        font: { size: 9, color: "#5a6080", align: "middle" },
        chosen: true,
      },
      physics: {
        solver: "forceAtlas2Based",
        forceAtlas2Based: {
          gravitationalConstant: -30,
          springLength: 80,
          springConstant: 0.08,
          damping: 0.4,
        },
        stabilization: { iterations: 150, updateInterval: 25 },
      },
      interaction: {
        hover: true,
        tooltipDelay: 150,
        navigationButtons: false,
        keyboard: false,
        zoomView: true,
        dragView: true,
      },
    };

    network = new vis.Network(container, data, options);

    // Tooltip on hover
    network.on("hoverNode", (params) => {
      const node = allNodes.get(params.node);
      if (node && node.title) container.title = node.title;
    });

    network.on("stabilizationIterationsDone", () => {
      network.setOptions({ physics: { enabled: false } });
    });
  }

  function _visNode(n) {
    const color = communityColor(n.community);
    return {
      id: n.id,
      label: _truncate(n.label, 28),
      title: `<div style="max-width:220px;font-size:12px;line-height:1.5">
        <b>${n.label}</b><br/>
        ${n.community_label ? `<span style="color:#7b82a0">${n.community_label}</span><br/>` : ""}
        ${n.source_location ? `<span style="color:#5a6080">${n.source_location}</span>` : ""}
      </div>`,
      color: {
        background: color + "33",
        border: color,
        highlight: { background: color + "66", border: color },
        hover:      { background: color + "44", border: color },
      },
      font: { color: "#c8cadc" },
      community: n.community,
      community_label: n.community_label,
    };
  }

  function _visEdge(e, idx) {
    return {
      id: `${e.source}-${e.target}-${idx}`,
      from: e.source,
      to: e.target,
      label: (e.relation || "").replace(/_/g, " "),
      title: e.relation,
    };
  }

  function _truncate(str, len) {
    return str && str.length > len ? str.slice(0, len - 1) + "…" : str;
  }

  async function loadFull() {
    const res = await fetch("/api/graph");
    const data = await res.json();

    allNodes.clear();
    allEdges.clear();

    allNodes.add(data.nodes.map(_visNode));
    allEdges.add(data.edges.map(_visEdge));

    buildLegend(data.nodes);
    network && network.fit({ animation: { duration: 600, easingFunction: "easeInOutQuad" } });
  }

  function buildLegend(nodes) {
    const seen = new Map();
    nodes.forEach(n => {
      if (!seen.has(n.community)) {
        seen.set(n.community, n.community_label || `Topic ${n.community}`);
      }
    });

    const legend = document.getElementById("graph-legend");
    legend.innerHTML = "";
    [...seen.entries()].slice(0, 10).forEach(([cid, label]) => {
      const color = communityColor(cid);
      const item = document.createElement("div");
      item.className = "legend-item";
      item.innerHTML = `<span class="legend-dot" style="background:${color}"></span><span>${label}</span>`;
      legend.appendChild(item);
    });
  }

  function highlight(nodeIds) {
    if (!network) return;
    highlightedIds = new Set(nodeIds);

    allNodes.forEach(n => {
      const isHighlighted = highlightedIds.has(n.id);
      const color = communityColor(n.community);
      allNodes.update({
        id: n.id,
        size: isHighlighted ? 18 : 10,
        color: {
          background: isHighlighted ? color + "99" : color + "1a",
          border: isHighlighted ? color : color + "55",
          highlight: { background: color + "cc", border: color },
          hover:      { background: color + "66", border: color },
        },
        font: { color: isHighlighted ? "#ffffff" : "#5a6080" },
      });
    });

    // Focus on highlighted nodes
    if (nodeIds.length > 0) {
      const positions = network.getPositions(nodeIds);
      const pts = Object.values(positions);
      if (pts.length > 0) {
        const cx = pts.reduce((s, p) => s + p.x, 0) / pts.length;
        const cy = pts.reduce((s, p) => s + p.y, 0) / pts.length;
        network.moveTo({ position: { x: cx, y: cy }, scale: 0.9,
          animation: { duration: 500, easingFunction: "easeInOutQuad" } });
      }
    }
  }

  function showSubgraph(subgraph) {
    if (!subgraph || !subgraph.nodes) return;
    const nodeIds = subgraph.nodes.map(n => n.id);
    highlight(nodeIds);
  }

  function fitAll() {
    network && network.fit({ animation: { duration: 500, easingFunction: "easeInOutQuad" } });
  }

  return { init, loadFull, highlight, showSubgraph, fitAll };
})();
