'use client';

import { useState } from 'react';
import { X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { TimeAgo } from '@/components/shared/TimeAgo';
import { severityColor } from '@/lib/utils';
import type { Insight } from '@/lib/types';

// Strip LLM artifacts from insight content:
// 1. Any leading heading containing "briefing"
// 2. Qwen thinking process preamble ("Thinking Process: ..." up to first real content)
function stripBriefingHeading(text: string): string {
  let cleaned = text;
  // Remove ## Morning Briefing style headings
  cleaned = cleaned.replace(/^#{1,3}\s+.*briefing.*\n?/im, '');
  // Remove "Thinking Process:" blocks up to first real paragraph
  cleaned = cleaned.replace(/^thinking process:[\s\S]*?(?=\n\n[^#\s*-]|\n[A-Z][^*\n])/i, '');
  // Strip lone "**" artifacts
  cleaned = cleaned.replace(/^\*\*\s*$/gm, '');
  return cleaned.trim();
}

interface InsightsFeedProps {
  insights: Insight[];
}

export function InsightsFeed({ insights: initialInsights }: InsightsFeedProps) {
  const [insights, setInsights] = useState(initialInsights);

  const handleDismiss = (id: number) => {
    setInsights(insights.filter((insight) => insight.id !== id));
    // TODO: Call API to update insight status
    // api.updateInsight(id, { status: 'dismissed' });
  };

  const getSeverityIcon = (severity: string) => {
    switch (severity) {
      case 'critical':
        return '🚨';
      case 'warning':
        return '⚠️';
      case 'info':
      default:
        return 'ℹ️';
    }
  };

  return (
    <div className="border border-[#27272A] bg-[#111113] rounded-xl p-6">
      <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
        <span>💡</span> Insights
      </h2>

      {insights.length === 0 ? (
        <p className="text-[#71717A] text-sm">No insights yet — Generate some?</p>
      ) : (
        <div className="space-y-3 max-h-[600px] overflow-y-auto pr-2">
          {insights.map((insight) => {
            const color = severityColor(insight.severity);

            return (
              <div
                key={insight.id}
                className="p-3 rounded-lg border border-[#27272A] hover:border-[#3F3F46] transition-colors group"
                style={{ borderLeftWidth: '3px', borderLeftColor: color }}
              >
                <div className="flex items-start gap-3">
                  <span className="text-lg flex-shrink-0 mt-0.5">
                    {getSeverityIcon(insight.severity)}
                  </span>

                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-[#A1A1AA] leading-relaxed prose prose-invert prose-sm max-w-none
                      [&_h1]:text-base [&_h1]:font-semibold [&_h1]:text-[#FAFAFA] [&_h1]:mb-1 [&_h1]:mt-0
                      [&_h2]:text-sm [&_h2]:font-semibold [&_h2]:text-[#FAFAFA] [&_h2]:mb-1 [&_h2]:mt-2
                      [&_h3]:text-sm [&_h3]:font-semibold [&_h3]:text-[#FAFAFA] [&_h3]:mb-1 [&_h3]:mt-2
                      [&_p]:text-[#A1A1AA] [&_p]:mb-1 [&_p]:mt-0
                      [&_ul]:list-disc [&_ul]:list-inside [&_ul]:mb-1 [&_ul]:space-y-0.5
                      [&_ol]:list-decimal [&_ol]:list-inside [&_ol]:mb-1
                      [&_li]:text-[#A1A1AA]
                      [&_strong]:text-[#FAFAFA] [&_strong]:font-semibold
                      [&_em]:italic [&_em]:text-[#A1A1AA]
                      [&_code]:bg-[#1A1A1E] [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-xs [&_code]:font-mono [&_code]:text-[#FAFAFA]">
                      <ReactMarkdown>
                        {stripBriefingHeading(insight.content)}
                      </ReactMarkdown>
                    </div>
                    <div className="flex items-center gap-2 mt-2">
                      <span
                        className="text-xs font-medium uppercase tracking-wide"
                        style={{ color }}
                      >
                        {insight.severity}
                      </span>
                      <span className="text-[#71717A]">•</span>
                      <TimeAgo date={insight.created_at} />
                    </div>
                  </div>

                  <button
                    onClick={() => handleDismiss(insight.id)}
                    className="opacity-0 group-hover:opacity-100 p-1 hover:bg-[#1A1A1E] rounded transition-all flex-shrink-0"
                    title="Dismiss insight"
                  >
                    <X size={14} className="text-[#71717A]" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
