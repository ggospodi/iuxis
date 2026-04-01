'use client';

import { useRef, useEffect, useState, useMemo } from 'react';
import * as d3 from 'd3';
import type { KnowledgeGraphData, GraphNode, GraphEdge, Project } from '@/lib/types';
import { X } from 'lucide-react';

interface Props {
  graphData: KnowledgeGraphData;
  projects: Project[];
}

const CATEGORY_COLORS: Record<string, string> = {
  FACT: '#3B82F6',
  DECISION: '#8B5CF6',
  RISK: '#EF4444',
  TIMELINE: '#F97316',
  COMPLIANCE: '#EC4899',
  METRIC: '#10B981',
  CONTEXT: '#F59E0B',
};

const RELATIONSHIP_STYLES: Record<string, { color: string; dasharray?: string }> = {
  causes: { color: '#EF4444' },
  blocks: { color: '#EF4444', dasharray: '5,5' },
  enables: { color: '#10B981' },
  depends_on: { color: '#3B82F6' },
  contradicts: { color: '#F97316', dasharray: '5,5' },
  supersedes: { color: '#6B7280', dasharray: '2,2' },
  references: { color: '#6B7280', dasharray: '2,2' },
  supports: { color: '#14B8A6' },
};

export function KnowledgeGraph({ graphData, projects }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [selectedProject, setSelectedProject] = useState<string>('');
  const [selectedRelTypes, setSelectedRelTypes] = useState<Set<string>>(new Set());

  // Get unique relationship types from graphData
  const relationshipTypes = useMemo(() => {
    const types = new Set<string>();
    graphData.edges.forEach(edge => types.add(edge.relationship_type));
    return Array.from(types).sort();
  }, [graphData.edges]);

  // Filter nodes and edges based on selected filters
  const { filteredNodes, filteredEdges } = useMemo(() => {
    let nodes = graphData.nodes;
    let edges = graphData.edges;

    // Filter by project
    if (selectedProject) {
      const projectId = parseInt(selectedProject);
      nodes = nodes.filter(n => n.project_id === projectId);
      const nodeIds = new Set(nodes.map(n => n.id));
      edges = edges.filter(e => nodeIds.has(e.from_id) && nodeIds.has(e.to_id));
    }

    // Filter by relationship type
    if (selectedRelTypes.size > 0) {
      edges = edges.filter(e => selectedRelTypes.has(e.relationship_type));
      const connectedNodeIds = new Set<number>();
      edges.forEach(e => {
        connectedNodeIds.add(e.from_id);
        connectedNodeIds.add(e.to_id);
      });
      nodes = nodes.filter(n => connectedNodeIds.has(n.id));
    }

    // Take top 30 by importance
    const sortedNodes = [...nodes].sort((a, b) =>
      (b.importance || 0) - (a.importance || 0)
    ).slice(0, 30);

    const topNodeIds = new Set(sortedNodes.map(n => n.id));
    const topEdges = edges.filter(e => topNodeIds.has(e.from_id) && topNodeIds.has(e.to_id));

    return { filteredNodes: sortedNodes, filteredEdges: topEdges };
  }, [graphData, selectedProject, selectedRelTypes]);

  // Get edges for selected node
  const selectedNodeEdges = useMemo(() => {
    if (!selectedNode) return [];
    return graphData.edges.filter(
      e => e.from_id === selectedNode.id || e.to_id === selectedNode.id
    );
  }, [selectedNode, graphData.edges]);

  useEffect(() => {
    if (!svgRef.current || filteredNodes.length === 0) return;

    const svg = d3.select(svgRef.current);
    const width = svgRef.current.clientWidth;
    const height = svgRef.current.clientHeight;

    // Clear previous content
    svg.selectAll('*').remove();

    // Create container group for zoom/pan
    const container = svg.append('g');

    // Define arrowhead markers for each relationship type
    const defs = svg.append('defs');
    Object.entries(RELATIONSHIP_STYLES).forEach(([type, style]) => {
      defs.append('marker')
        .attr('id', `arrowhead-${type}`)
        .attr('viewBox', '0 -5 10 10')
        .attr('refX', 20)
        .attr('refY', 0)
        .attr('markerWidth', 6)
        .attr('markerHeight', 6)
        .attr('orient', 'auto')
        .append('path')
        .attr('d', 'M0,-5L10,0L0,5')
        .attr('fill', style.color);
    });

    // Map edges to D3 format
    const d3Edges = filteredEdges.map(e => ({
      source: e.from_id,
      target: e.to_id,
      relationship_type: e.relationship_type,
    }));

    // Create force simulation
    const simulation = d3.forceSimulation(filteredNodes as any)
      .force('link', d3.forceLink(d3Edges)
        .id((d: any) => d.id)
        .distance(100))
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(30));

    // Draw edges
    const link = container.append('g')
      .selectAll('line')
      .data(d3Edges)
      .join('line')
      .attr('stroke', (d: any) => RELATIONSHIP_STYLES[d.relationship_type]?.color || '#6B7280')
      .attr('stroke-width', 1.5)
      .attr('stroke-dasharray', (d: any) => RELATIONSHIP_STYLES[d.relationship_type]?.dasharray || 'none')
      .attr('marker-end', (d: any) => `url(#arrowhead-${d.relationship_type})`);

    // Draw nodes
    const node = container.append('g')
      .selectAll('g')
      .data(filteredNodes)
      .join('g')
      .call(d3.drag<any, any>()
        .on('start', dragstarted)
        .on('drag', dragged)
        .on('end', dragended) as any);

    // Node circles
    node.append('circle')
      .attr('r', d => Math.max(6, Math.min(18, (d.importance || 0) * 12)))
      .attr('fill', d => CATEGORY_COLORS[d.category.toUpperCase()] || '#6B7280')
      .attr('stroke', '#09090B')
      .attr('stroke-width', 2)
      .attr('cursor', 'pointer')
      .on('click', (_event: any, d: GraphNode) => {
        setSelectedNode(d);
      });

    // Node labels
    node.append('text')
      .text(d => d.content.length > 40 ? d.content.slice(0, 40) + '...' : d.content)
      .attr('x', 0)
      .attr('y', d => Math.max(6, Math.min(18, (d.importance || 0) * 12)) + 14)
      .attr('text-anchor', 'middle')
      .attr('fill', '#FAFAFA')
      .attr('font-size', '10px')
      .attr('pointer-events', 'none');

    // Tooltip
    const tooltip = d3.select('body').append('div')
      .style('position', 'absolute')
      .style('padding', '8px 12px')
      .style('background', '#1A1A1E')
      .style('border', '1px solid #27272A')
      .style('border-radius', '8px')
      .style('color', '#FAFAFA')
      .style('font-size', '12px')
      .style('pointer-events', 'none')
      .style('opacity', 0)
      .style('z-index', 1000);

    node.on('mouseenter', (_event: any, d: GraphNode) => {
      tooltip
        .style('opacity', 1)
        .html(`
          <div style="max-width: 300px;">
            <div style="font-weight: 600; margin-bottom: 4px;">${d.content}</div>
            <div style="color: #71717A; font-size: 11px;">
              ${d.project_name || 'No project'} • ${d.category}
            </div>
          </div>
        `);
    })
    .on('mousemove', (event: MouseEvent) => {
      tooltip
        .style('left', (event.pageX + 10) + 'px')
        .style('top', (event.pageY + 10) + 'px');
    })
    .on('mouseleave', () => {
      tooltip.style('opacity', 0);
    });

    // Update positions on simulation tick
    simulation.on('tick', () => {
      link
        .attr('x1', (d: any) => d.source.x)
        .attr('y1', (d: any) => d.source.y)
        .attr('x2', (d: any) => d.target.x)
        .attr('y2', (d: any) => d.target.y);

      node.attr('transform', (d: any) => `translate(${d.x},${d.y})`);
    });

    // Drag handlers
    function dragstarted(event: any) {
      if (!event.active) simulation.alphaTarget(0.3).restart();
      event.subject.fx = event.subject.x;
      event.subject.fy = event.subject.y;
    }

    function dragged(event: any) {
      event.subject.fx = event.x;
      event.subject.fy = event.y;
    }

    function dragended(event: any) {
      if (!event.active) simulation.alphaTarget(0);
      event.subject.fx = null;
      event.subject.fy = null;
    }

    // Zoom behavior — store in ref so resetZoom can access it
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.5, 3])
      .on('zoom', (event) => {
        container.attr('transform', event.transform);
      });

    zoomRef.current = zoom;
    svg.call(zoom as any);

    // Cleanup
    return () => {
      tooltip.remove();
      simulation.stop();
    };
  }, [filteredNodes, filteredEdges]);

  const resetZoom = () => {
    if (svgRef.current && zoomRef.current) {
      d3.select(svgRef.current)
        .transition()
        .duration(750)
        .call(zoomRef.current.transform, d3.zoomIdentity);
    }
  };

  const toggleRelType = (type: string) => {
    const newSet = new Set(selectedRelTypes);
    if (newSet.has(type)) {
      newSet.delete(type);
    } else {
      newSet.add(type);
    }
    setSelectedRelTypes(newSet);
  };

  return (
    <div className="relative h-[800px] border border-[#27272A] bg-[#09090B] rounded-xl overflow-hidden">
      {/* Filter bar */}
      <div className="absolute top-0 left-0 right-0 p-4 bg-[#111113]/95 border-b border-[#27272A] z-10 flex gap-3 flex-wrap items-center">
        <select
          value={selectedProject}
          onChange={(e) => setSelectedProject(e.target.value)}
          className="px-3 py-2 bg-[#1A1A1E] border border-[#27272A] rounded-lg text-sm text-[#FAFAFA] focus:outline-none focus:border-[#3B82F6]"
        >
          <option value="">All Projects</option>
          {projects.map(p => (
            <option key={p.id} value={String(p.id)}>{p.name}</option>
          ))}
        </select>

        <div className="flex gap-2 flex-wrap">
          {relationshipTypes.map(type => {
            const style = RELATIONSHIP_STYLES[type] || { color: '#6B7280' };
            const isActive = selectedRelTypes.has(type);
            return (
              <button
                key={type}
                onClick={() => toggleRelType(type)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  isActive
                    ? 'text-white'
                    : 'text-[#71717A] hover:text-[#A1A1AA]'
                }`}
                style={{
                  backgroundColor: isActive ? style.color : 'transparent',
                  border: `1px solid ${isActive ? style.color : '#27272A'}`,
                }}
              >
                {type}
              </button>
            );
          })}
        </div>

        {(selectedProject || selectedRelTypes.size > 0) && (
          <button
            onClick={() => {
              setSelectedProject('');
              setSelectedRelTypes(new Set());
            }}
            className="px-3 py-2 text-xs text-[#71717A] hover:text-[#FAFAFA] border border-[#27272A] rounded-lg transition-colors"
          >
            Clear filters
          </button>
        )}

        <span className="ml-auto text-xs text-[#71717A]">
          {filteredNodes.length} nodes, {filteredEdges.length} edges
        </span>
      </div>

      {/* Reset zoom button */}
      <button
        onClick={resetZoom}
        className="absolute top-20 right-4 z-10 px-3 py-2 bg-[#1A1A1E] border border-[#27272A] rounded-lg text-xs text-[#FAFAFA] hover:bg-[#27272A] transition-colors"
      >
        Reset Zoom
      </button>

      {/* Graph SVG */}
      <svg
        ref={svgRef}
        className="w-full h-full"
        style={{ background: '#09090B' }}
      />

      {/* Side panel for selected node */}
      {selectedNode && (
        <div className="absolute top-0 right-0 w-[300px] h-full bg-[#111113] border-l border-[#27272A] p-4 overflow-y-auto z-20">
          <div className="flex items-start justify-between mb-4">
            <h3 className="text-sm font-semibold text-[#FAFAFA]">Node Details</h3>
            <button
              onClick={() => setSelectedNode(null)}
              className="text-[#71717A] hover:text-[#FAFAFA] transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="space-y-4">
            <div>
              <div className="text-xs text-[#71717A] mb-1">Content</div>
              <div className="text-sm text-[#FAFAFA]">{selectedNode.content}</div>
            </div>

            <div>
              <div className="text-xs text-[#71717A] mb-1">Category</div>
              <span
                className="inline-block px-2 py-1 rounded text-xs font-semibold text-white"
                style={{ backgroundColor: CATEGORY_COLORS[selectedNode.category.toUpperCase()] || '#6B7280' }}
              >
                {selectedNode.category}
              </span>
            </div>

            <div>
              <div className="text-xs text-[#71717A] mb-1">Project</div>
              <div className="text-sm text-[#FAFAFA]">{selectedNode.project_name || 'No project'}</div>
            </div>

            {selectedNode.importance !== null && (
              <div>
                <div className="text-xs text-[#71717A] mb-1">Importance</div>
                <div className="text-sm text-[#FAFAFA]">{selectedNode.importance.toFixed(2)}</div>
              </div>
            )}

            <div>
              <div className="text-xs text-[#71717A] mb-2">Relationships ({selectedNodeEdges.length})</div>
              <div className="space-y-2">
                {selectedNodeEdges.length === 0 ? (
                  <div className="text-xs text-[#3F3F46]">No relationships</div>
                ) : (
                  selectedNodeEdges.map((edge, idx) => {
                    const isOutgoing = edge.from_id === selectedNode.id;
                    const relatedNodeId = isOutgoing ? edge.to_id : edge.from_id;
                    const relatedNode = graphData.nodes.find(n => n.id === relatedNodeId);
                    const style = RELATIONSHIP_STYLES[edge.relationship_type] || { color: '#6B7280' };

                    return (
                      <div key={idx} className="text-xs border border-[#27272A] rounded p-2">
                        <div className="flex items-center gap-2 mb-1">
                          <span style={{ color: style.color }}>
                            {isOutgoing ? '→' : '←'}
                          </span>
                          <span className="font-medium" style={{ color: style.color }}>
                            {edge.relationship_type}
                          </span>
                        </div>
                        <div className="text-[#A1A1AA] line-clamp-2">
                          {relatedNode?.content || `Node #${relatedNodeId}`}
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
