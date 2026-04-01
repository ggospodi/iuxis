'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown, ChevronUp, RefreshCw } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { api } from '@/lib/api';

function stripBriefingHeading(text: unknown): string {
  const str = typeof text === 'string' ? text : JSON.stringify(text ?? '');
  return str.replace(/^#{1,3}\s+.*briefing.*\n?/im, '').trim();
}

interface BriefingCardProps {
  briefing: { briefing: string | null; exists: boolean };
  projectCount?: number;
}

export function BriefingCard({ briefing: initialBriefing, projectCount = 0 }: BriefingCardProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const [isGenerating, setIsGenerating] = useState(false);
  const [briefing, setBriefing] = useState(initialBriefing);

  const handleGenerate = async () => {
    setIsGenerating(true);
    try {
      const result = await api.generateBriefing();

      if (result?.briefing) {
        setBriefing({ briefing: String(result.briefing), exists: true });
        return;
      }

      for (let i = 0; i < 5; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        const newBriefing = await api.getLatestBriefing();
        if (newBriefing?.briefing) {
          setBriefing(newBriefing);
          return;
        }
      }

      const fallback = await api.getLatestBriefing();
      setBriefing(fallback);
    } catch (error) {
      console.error("Failed to generate Today's Focus:", error);
    } finally {
      setIsGenerating(false);
    }
  };

  useEffect(() => {
    // Only auto-generate if there are projects (avoid hallucinations on empty workspace)
    if (projectCount > 0 && (!initialBriefing?.exists || !initialBriefing?.briefing)) {
      handleGenerate();
    }
  }, [projectCount]);

  const briefingText = briefing?.briefing ? String(briefing.briefing) : null;

  return (
    <div className="border border-[#27272A] border-l-4 border-l-[#3B82F6] bg-[#111113] rounded-xl overflow-hidden">
      <div className="p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <span>🎯</span> Today's Focus
          </h2>
          <div className="flex items-center gap-2">
            <button
              onClick={handleGenerate}
              disabled={isGenerating || projectCount === 0}
              className="flex items-center gap-2 px-3 py-1.5 text-xs text-[#A1A1AA] hover:text-[#FAFAFA] hover:bg-[#1A1A1E] rounded-lg transition-colors disabled:opacity-50"
            >
              <RefreshCw size={14} className={isGenerating ? 'animate-spin' : ''} />
              {isGenerating ? 'Generating...' : 'Refresh Focus'}
            </button>
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="p-2 hover:bg-[#1A1A1E] rounded-lg transition-colors"
            >
              {isExpanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
            </button>
          </div>
        </div>

        <AnimatePresence>
          {isExpanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="overflow-hidden"
            >
              {projectCount === 0 ? (
                <div className="text-sm text-[#A1A1AA] leading-relaxed">
                  <p className="mb-2">
                    Create your first project to get started. Tell the chat:
                  </p>
                  <code className="block bg-[#1A1A1E] px-3 py-2 rounded text-sm font-mono text-[#FAFAFA]">
                    &quot;Create a project called [Your Project Name]...&quot;
                  </code>
                </div>
              ) : isGenerating && !briefingText ? (
                <div className="flex items-center gap-3 text-[#71717A] py-2">
                  <RefreshCw size={16} className="animate-spin" />
                  <span className="text-sm">Generating Today's Focus...</span>
                </div>
              ) : briefingText ? (
                <div className="prose prose-invert prose-sm max-w-none">
                  <ReactMarkdown
                    components={{
                      h1: ({ children }) => <h1 className="text-xl font-bold mb-3 text-[#FAFAFA]">{children}</h1>,
                      h2: ({ children }) => <h2 className="text-lg font-semibold mb-2 mt-4 text-[#FAFAFA]">{children}</h2>,
                      h3: ({ children }) => <h3 className="text-base font-semibold mb-2 mt-3 text-[#FAFAFA]">{children}</h3>,
                      p: ({ children }) => <p className="text-[#A1A1AA] mb-3 leading-relaxed">{children}</p>,
                      ul: ({ children }) => <ul className="list-disc list-inside mb-3 space-y-1">{children}</ul>,
                      ol: ({ children }) => <ol className="list-decimal list-inside mb-3 space-y-1">{children}</ol>,
                      li: ({ children }) => <li className="text-[#A1A1AA]">{children}</li>,
                      strong: ({ children }) => <strong className="font-semibold text-[#FAFAFA]">{children}</strong>,
                      em: ({ children }) => <em className="italic text-[#FAFAFA]">{children}</em>,
                      code: ({ children }) => (
                        <code className="bg-[#1A1A1E] px-1.5 py-0.5 rounded text-sm font-mono text-[#FAFAFA]">
                          {children}
                        </code>
                      ),
                    }}
                  >
                    {stripBriefingHeading(briefingText)}
                  </ReactMarkdown>
                </div>
              ) : (
                <p className="text-sm text-[#71717A]">Could not generate Today's Focus — try Refresh Focus.</p>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
