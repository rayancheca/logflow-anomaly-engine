import { useEffect, useRef } from "react";
import * as d3 from "d3";
import type { TimelinePoint } from "../types";

interface Props {
  timeline: TimelinePoint[];
}

export default function TimelineChart({ timeline }: Props) {
  const svgRef = useRef<SVGSVGElement | null>(null);

  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const width = svgRef.current.clientWidth || 360;
    const height = 140;
    const margin = { top: 10, right: 8, bottom: 18, left: 28 };
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    const data = timeline.length ? timeline : [];
    const x = d3.scaleLinear().domain([0, Math.max(data.length - 1, 1)]).range([0, innerW]);
    const yMax = d3.max(data, (d) => d.total) || 1;
    const y = d3.scaleLinear().domain([0, yMax * 1.15 || 1]).nice().range([innerH, 0]);

    const g = svg
      .attr("viewBox", `0 0 ${width} ${height}`)
      .append("g")
      .attr("transform", `translate(${margin.left},${margin.top})`);

    const grad = g.append("defs").append("linearGradient")
      .attr("id", "vol-grad").attr("x1", 0).attr("y1", 0).attr("x2", 0).attr("y2", 1);
    grad.append("stop").attr("offset", "0%").attr("stop-color", "#2dd4bf").attr("stop-opacity", 0.45);
    grad.append("stop").attr("offset", "100%").attr("stop-color", "#2dd4bf").attr("stop-opacity", 0);

    // grid
    g.append("g")
      .attr("class", "grid")
      .selectAll("line")
      .data(y.ticks(4))
      .join("line")
      .attr("x1", 0).attr("x2", innerW)
      .attr("y1", (d) => y(d)).attr("y2", (d) => y(d))
      .attr("stroke", "rgba(255,255,255,0.04)");

    // y axis
    g.append("g")
      .call(d3.axisLeft(y).ticks(4).tickSize(0).tickPadding(4))
      .call((sel) => sel.select(".domain").remove())
      .call((sel) => sel.selectAll("text").attr("fill", "#64748b").attr("font-size", 9));

    if (data.length < 2) return;

    const area = d3.area<TimelinePoint>()
      .x((_, i) => x(i))
      .y0(innerH)
      .y1((d) => y(d.total))
      .curve(d3.curveMonotoneX);

    const line = d3.line<TimelinePoint>()
      .x((_, i) => x(i))
      .y((d) => y(d.total))
      .curve(d3.curveMonotoneX);

    g.append("path").datum(data).attr("d", area).attr("fill", "url(#vol-grad)");
    g.append("path")
      .datum(data)
      .attr("d", line)
      .attr("fill", "none")
      .attr("stroke", "#5eead4")
      .attr("stroke-width", 1.75);

    // errors as mini bars
    const errMax = d3.max(data, (d) => d.errors) || 1;
    const yErr = d3.scaleLinear().domain([0, errMax || 1]).range([innerH, innerH * 0.6]);
    g.append("g")
      .selectAll("rect")
      .data(data)
      .join("rect")
      .attr("x", (_, i) => x(i) - 1)
      .attr("y", (d) => yErr(d.errors))
      .attr("width", 2)
      .attr("height", (d) => innerH - yErr(d.errors))
      .attr("fill", "#f43f5e")
      .attr("opacity", 0.75);
  }, [timeline]);

  return (
    <svg ref={svgRef} className="w-full h-[140px]" />
  );
}
