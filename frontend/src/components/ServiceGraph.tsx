import { useEffect, useMemo, useRef } from "react";
import * as d3 from "d3";
import type { Incident, ServiceGraphSnapshot } from "../types";

interface Props {
  graph: ServiceGraphSnapshot;
  incident: Incident | null;
  onNodeClick?: (service: string) => void;
}

interface SimNode extends d3.SimulationNodeDatum {
  id: string;
  group: string;
  health: number;
  logs_per_min: number;
  error_rate: number;
  mean_latency_ms: number;
}

interface SimLink extends d3.SimulationLinkDatum<SimNode> {
  weight: number;
}

const GROUP_COLOR: Record<string, string> = {
  edge:     "#60a5fa",
  core:     "#5eead4",
  commerce: "#f59e0b",
  delivery: "#a855f7",
  other:    "#94a3b8",
};

export default function ServiceGraph({ graph, incident, onNodeClick }: Props) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const simRef = useRef<d3.Simulation<SimNode, SimLink> | null>(null);
  const nodeMap = useRef<Map<string, SimNode>>(new Map());

  const blastHops = useMemo(() => incident?.impact_hops ?? {}, [incident]);
  const rootService = incident?.root_service ?? null;

  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);
    if (svg.select("g.layer").empty()) {
      svg.append("g").attr("class", "layer");
    }
    const layer = svg.select<SVGGElement>("g.layer");

    const width  = svgRef.current.clientWidth || 900;
    const height = 420;
    svg.attr("viewBox", `0 0 ${width} ${height}`);

    // Sync nodes — reuse existing node objects to preserve positions.
    const existing = nodeMap.current;
    const nodes: SimNode[] = graph.nodes.map((n) => {
      const prev = existing.get(n.id);
      if (prev) {
        prev.group = n.group;
        prev.health = n.health;
        prev.logs_per_min = n.logs_per_min;
        prev.error_rate = n.error_rate;
        prev.mean_latency_ms = n.mean_latency_ms;
        return prev;
      }
      const fresh: SimNode = {
        id: n.id,
        group: n.group,
        health: n.health,
        logs_per_min: n.logs_per_min,
        error_rate: n.error_rate,
        mean_latency_ms: n.mean_latency_ms,
        x: width / 2 + (Math.random() - 0.5) * 200,
        y: height / 2 + (Math.random() - 0.5) * 200,
      };
      existing.set(n.id, fresh);
      return fresh;
    });
    for (const id of Array.from(existing.keys())) {
      if (!graph.nodes.find((n) => n.id === id)) existing.delete(id);
    }
    const links: SimLink[] = graph.edges.map((e) => ({
      source: existing.get(e.source)!,
      target: existing.get(e.target)!,
      weight: e.weight,
    })).filter((l) => l.source && l.target);

    // --- simulation
    if (!simRef.current) {
      simRef.current = d3.forceSimulation<SimNode, SimLink>()
        .force("link", d3.forceLink<SimNode, SimLink>().id((d) => d.id).distance(90).strength(0.6))
        .force("charge", d3.forceManyBody().strength(-320))
        .force("center", d3.forceCenter(width / 2, height / 2))
        .force("collide", d3.forceCollide(28));
    }
    const sim = simRef.current;
    sim.nodes(nodes);
    (sim.force("link") as d3.ForceLink<SimNode, SimLink>).links(links);
    sim.alpha(0.35).restart();

    // --- render links
    const linkSel = layer
      .selectAll<SVGLineElement, SimLink>("line.link")
      .data(links, (d: SimLink) => `${(d.source as SimNode).id}->${(d.target as SimNode).id}`);
    linkSel.exit().remove();
    const linkEnter = linkSel.enter().append("line")
      .attr("class", "link")
      .attr("stroke", "rgba(148,163,184,0.25)")
      .attr("stroke-width", 1);
    const linkMerged = linkEnter.merge(linkSel as any)
      .attr("stroke", (d) => {
        const src = (d.source as SimNode).id;
        const tgt = (d.target as SimNode).id;
        if (incident && (src in blastHops) && (tgt in blastHops)) {
          return "rgba(244,63,94,0.8)";
        }
        return "rgba(148,163,184,0.22)";
      })
      .attr("stroke-width", (d) => 0.8 + d.weight * 2.2);

    // --- render node groups
    const nodeSel = layer
      .selectAll<SVGGElement, SimNode>("g.node")
      .data(nodes, (d: SimNode) => d.id);
    nodeSel.exit().remove();
    const nodeEnter = nodeSel.enter().append("g").attr("class", "node");

    nodeEnter.append("circle").attr("class", "ring-pulse");
    nodeEnter.append("circle").attr("class", "dot");
    nodeEnter.append("text").attr("class", "label");
    nodeEnter.append("text").attr("class", "hop");

    const nodeMerged = nodeEnter.merge(nodeSel as any);

    nodeMerged.select<SVGCircleElement>("circle.dot")
      .attr("r", (d) => 6 + Math.min(d.logs_per_min / 6, 10))
      .attr("fill", (d) => GROUP_COLOR[d.group] || GROUP_COLOR.other)
      .attr("fill-opacity", 0.22)
      .attr("stroke", (d) => GROUP_COLOR[d.group] || GROUP_COLOR.other)
      .attr("stroke-width", 1.6)
      .attr("filter", (d) => (d.id in blastHops ? "url(#glow)" : null));

    nodeMerged.select<SVGCircleElement>("circle.ring-pulse")
      .attr("r", (d) => (d.id === rootService ? 14 : 0))
      .attr("fill", "none")
      .attr("stroke", "#f43f5e")
      .attr("stroke-width", 1.5)
      .attr("opacity", (d) => (d.id === rootService ? 0.85 : 0))
      .attr("class", (d) => (d.id === rootService ? "ring-pulse animate-pulseRing" : "ring-pulse"));

    nodeMerged.select<SVGTextElement>("text.label")
      .attr("text-anchor", "middle")
      .attr("dy", 26)
      .attr("fill", (d) => (d.id in blastHops ? "#f8fafc" : "#94a3b8"))
      .attr("font-size", 10)
      .attr("font-family", "JetBrains Mono, monospace")
      .attr("font-weight", (d) => (d.id in blastHops ? 600 : 400))
      .text((d) => d.id);

    nodeMerged.select<SVGTextElement>("text.hop")
      .attr("text-anchor", "middle")
      .attr("dy", -12)
      .attr("font-size", 9)
      .attr("font-weight", 600)
      .attr("font-family", "JetBrains Mono, monospace")
      .attr("fill", "#f43f5e")
      .text((d) => (d.id in blastHops && blastHops[d.id] > 0 ? `+${blastHops[d.id]}` : ""));

    // defs for glow
    if (svg.select("defs#gdefs").empty()) {
      const defs = svg.append("defs").attr("id", "gdefs");
      const filter = defs.append("filter").attr("id", "glow")
        .attr("x", "-50%").attr("y", "-50%").attr("width", "200%").attr("height", "200%");
      filter.append("feGaussianBlur").attr("stdDeviation", 3).attr("result", "coloredBlur");
      const merge = filter.append("feMerge");
      merge.append("feMergeNode").attr("in", "coloredBlur");
      merge.append("feMergeNode").attr("in", "SourceGraphic");
    }

    // --- click to open service drawer
    nodeMerged.style("cursor", onNodeClick ? "pointer" : "default")
      .on("click", (_event, d: SimNode) => {
        if (onNodeClick) onNodeClick(d.id);
      });

    // --- drag behaviour
    nodeMerged.call(
      d3.drag<SVGGElement, SimNode>()
        .on("start", (event, d) => {
          if (!event.active) sim.alphaTarget(0.3).restart();
          d.fx = d.x; d.fy = d.y;
        })
        .on("drag", (event, d) => { d.fx = event.x; d.fy = event.y; })
        .on("end", (event, d) => {
          if (!event.active) sim.alphaTarget(0);
          d.fx = null; d.fy = null;
        }),
    );

    sim.on("tick", () => {
      linkMerged
        .attr("x1", (d) => (d.source as SimNode).x ?? 0)
        .attr("y1", (d) => (d.source as SimNode).y ?? 0)
        .attr("x2", (d) => (d.target as SimNode).x ?? 0)
        .attr("y2", (d) => (d.target as SimNode).y ?? 0);
      nodeMerged.attr("transform", (d) => `translate(${d.x ?? 0},${d.y ?? 0})`);
    });
  }, [graph, incident, blastHops, rootService, onNodeClick]);

  return (
    <div className="relative">
      <svg ref={svgRef} className="w-full h-[420px]" />
      <div className="absolute bottom-2 left-2 flex gap-3 mono text-[10px] text-slate-500">
        {Object.entries(GROUP_COLOR).map(([g, c]) => (
          <span key={g} className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full" style={{ background: c }} />
            {g}
          </span>
        ))}
      </div>
    </div>
  );
}
