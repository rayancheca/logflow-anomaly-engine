import { useEffect, useRef, useState } from "react";
import * as d3 from "d3";
import type { CorrelationMatrix } from "../types";
import { getCorrelations } from "../api";

export default function CorrelationHeatmap() {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [data, setData] = useState<CorrelationMatrix | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const c = await getCorrelations();
        if (!cancelled) setData(c);
      } catch {
        /* noop */
      }
    }
    load();
    const id = setInterval(load, 3500);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  useEffect(() => {
    if (!svgRef.current || !data) return;
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const width = svgRef.current.clientWidth || 360;
    const services = data.services;
    const n = services.length;
    if (n === 0) return;
    const margin = { top: 66, right: 8, bottom: 8, left: 86 };
    const innerW = width - margin.left - margin.right;
    const innerH = innerW; // square
    const cell = innerW / n;
    const totalH = innerH + margin.top + margin.bottom;
    svg.attr("viewBox", `0 0 ${width} ${totalH}`);

    const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);
    const color = d3.scaleLinear<string>()
      .domain([-1, 0, 1])
      .range(["#60a5fa", "#11151d", "#f43f5e"])
      .clamp(true);

    for (let i = 0; i < n; i++) {
      for (let j = 0; j < n; j++) {
        const v = data.matrix[i]?.[j] ?? 0;
        g.append("rect")
          .attr("x", j * cell)
          .attr("y", i * cell)
          .attr("width", cell - 1)
          .attr("height", cell - 1)
          .attr("fill", color(v))
          .attr("rx", 1.5)
          .append("title")
          .text(`${services[i]} × ${services[j]} = ${v.toFixed(2)}`);
      }
    }

    // row labels
    g.append("g")
      .selectAll("text")
      .data(services)
      .join("text")
      .attr("x", -6)
      .attr("y", (_, i) => i * cell + cell / 2 + 3)
      .attr("text-anchor", "end")
      .attr("font-size", Math.max(8, Math.min(10, cell - 2)))
      .attr("font-family", "JetBrains Mono, monospace")
      .attr("fill", "#94a3b8")
      .text((s) => s);

    // col labels (rotated)
    g.append("g")
      .selectAll("text")
      .data(services)
      .join("text")
      .attr("transform", (_, i) => `translate(${i * cell + cell / 2}, -6) rotate(-45)`)
      .attr("text-anchor", "start")
      .attr("font-size", Math.max(8, Math.min(10, cell - 2)))
      .attr("font-family", "JetBrains Mono, monospace")
      .attr("fill", "#94a3b8")
      .text((s) => s);

    // legend
    const legW = 120;
    const legH = 6;
    const legendX = margin.left + innerW - legW;
    const legendY = 14;
    const lg = svg.append("g").attr("transform", `translate(${legendX},${legendY})`);
    const defs = svg.append("defs");
    const grad = defs.append("linearGradient")
      .attr("id", "corr-grad").attr("x1", 0).attr("y1", 0).attr("x2", 1).attr("y2", 0);
    grad.append("stop").attr("offset", "0%").attr("stop-color", "#60a5fa");
    grad.append("stop").attr("offset", "50%").attr("stop-color", "#11151d");
    grad.append("stop").attr("offset", "100%").attr("stop-color", "#f43f5e");
    lg.append("rect").attr("width", legW).attr("height", legH).attr("fill", "url(#corr-grad)").attr("rx", 2);
    lg.append("text").attr("x", 0).attr("y", -3).attr("fill", "#94a3b8")
      .attr("font-size", 8).attr("font-family", "JetBrains Mono, monospace").text("-1");
    lg.append("text").attr("x", legW / 2).attr("y", -3).attr("text-anchor", "middle").attr("fill", "#94a3b8")
      .attr("font-size", 8).attr("font-family", "JetBrains Mono, monospace").text("0");
    lg.append("text").attr("x", legW).attr("y", -3).attr("text-anchor", "end").attr("fill", "#94a3b8")
      .attr("font-size", 8).attr("font-family", "JetBrains Mono, monospace").text("+1");
  }, [data]);

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <div className="panel-title">error-rate correlation · {data?.window_seconds ?? 60}s window</div>
        <div className="mono text-[10px] text-slate-600">pearson</div>
      </div>
      {!data || data.services.length === 0 ? (
        <div className="text-[11px] text-slate-600 mono p-4">warming up correlations…</div>
      ) : (
        <svg ref={svgRef} className="w-full" />
      )}
    </div>
  );
}
