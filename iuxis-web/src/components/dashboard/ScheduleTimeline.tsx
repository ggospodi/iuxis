'use client';

import { useState, useEffect } from 'react';
import { RefreshCw } from 'lucide-react';
import { projectColor } from '@/lib/utils';
import { api } from '@/lib/api';
import type { ScheduleBlock } from '@/lib/types';

interface ScheduleTimelineProps {
  blocks: ScheduleBlock[];
}

export function ScheduleTimeline({ blocks: initialBlocks }: ScheduleTimelineProps) {
  const [blocks, setBlocks] = useState(initialBlocks);
  const [isGenerating, setIsGenerating] = useState(false);
  const [currentTime, setCurrentTime] = useState(new Date());

  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentTime(new Date());
    }, 60000); // Update every minute
    return () => clearInterval(interval);
  }, []);

  const handleGenerate = async () => {
    setIsGenerating(true);
    try {
      await api.generateSchedule();
      const newSchedule = await api.getTodaysSchedule();
      setBlocks(newSchedule.blocks);
    } catch (error) {
      console.error('Failed to generate schedule:', error);
    } finally {
      setIsGenerating(false);
    }
  };

  if (blocks.length === 0) {
    return (
      <div className="border border-[#27272A] bg-[#111113] rounded-xl p-6">
        <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
          <span>📅</span> Schedule
        </h2>
        <div className="flex items-center justify-between">
          <p className="text-[#A1A1AA]">No schedule today — Generate one?</p>
          <button
            onClick={handleGenerate}
            disabled={isGenerating}
            className="px-4 py-2 bg-[#3B82F6] hover:bg-[#2563EB] text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            {isGenerating ? (
              <>
                <RefreshCw size={16} className="animate-spin" />
                Generating...
              </>
            ) : (
              'Generate Schedule'
            )}
          </button>
        </div>
      </div>
    );
  }

  const startHour = 6;
  const endHour = 16;
  const totalHours = endHour - startHour;

  const getPosition = (timeStr: string) => {
    const [hours, minutes] = timeStr.split(':').map(Number);
    const totalMinutes = (hours - startHour) * 60 + minutes;
    return (totalMinutes / (totalHours * 60)) * 100;
  };

  const getWidth = (start: string, end: string) => {
    const startPos = getPosition(start);
    const endPos = getPosition(end);
    return endPos - startPos;
  };

  const currentHour = currentTime.getHours();
  const currentMinute = currentTime.getMinutes();
  const currentPosition = currentHour >= startHour && currentHour < endHour
    ? ((currentHour - startHour) * 60 + currentMinute) / (totalHours * 60) * 100
    : -1;

  return (
    <div className="border border-[#27272A] bg-[#111113] rounded-xl p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <span>📅</span> Schedule
        </h2>
        <button
          onClick={handleGenerate}
          disabled={isGenerating}
          className="p-2 hover:bg-[#1A1A1E] rounded-lg transition-colors disabled:opacity-50"
          title="Regenerate schedule"
        >
          <RefreshCw size={16} className={isGenerating ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* Timeline */}
      <div className="mb-6">
        {/* Hour markers */}
        <div className="flex justify-between text-xs text-[#71717A] mb-2">
          {Array.from({ length: totalHours + 1 }, (_, i) => (
            <span key={i} className="w-12 text-center">
              {startHour + i}:00
            </span>
          ))}
        </div>

        {/* Timeline bar */}
        <div className="relative h-12 bg-[#1A1A1E] rounded-lg">
          {blocks.map((block) => {
            const left = getPosition(block.start_time);
            const width = getWidth(block.start_time, block.end_time);
            const color = projectColor(block.project_name);

            return (
              <div
                key={block.id}
                className="absolute top-1 bottom-1 rounded px-2 flex items-center cursor-pointer hover:opacity-90 transition-opacity group"
                style={{
                  left: `${left}%`,
                  width: `${width}%`,
                  backgroundColor: color,
                }}
                title={`${block.project_name} — ${block.start_time} to ${block.end_time}`}
              >
                <span className="text-xs font-medium text-white truncate">
                  {block.project_name}
                </span>
              </div>
            );
          })}

          {/* Current time indicator */}
          {currentPosition >= 0 && (
            <div
              className="absolute top-0 bottom-0 w-0.5 bg-[#EF4444]"
              style={{ left: `${currentPosition}%` }}
            >
              <div className="absolute -top-1 -left-1 w-2 h-2 bg-[#EF4444] rounded-full animate-pulse" />
            </div>
          )}
        </div>
      </div>

      {/* List view */}
      <div className="space-y-2">
        {blocks.map((block) => (
          <div
            key={block.id}
            className="flex items-center gap-3 p-2 rounded-lg hover:bg-[#1A1A1E] transition-colors"
          >
            <div
              className="w-1 h-8 rounded-full"
              style={{ backgroundColor: projectColor(block.project_name) }}
            />
            <div className="flex-1">
              <div className="text-sm font-medium text-[#FAFAFA]">
                {block.project_name}
              </div>
              <div className="text-xs text-[#71717A]">
                {block.start_time} — {block.end_time}
              </div>
            </div>
            <span className="text-xs text-[#71717A] capitalize">
              {block.block_type}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
