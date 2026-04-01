'use client';

import { useState, useRef, useEffect } from 'react';
import { motion } from 'framer-motion';
import { MessageSquare, PanelRightClose, PanelRightOpen } from 'lucide-react';
import { useChat } from '@/lib/hooks';
import { ChatMessage } from './ChatMessage';
import { ChatInput } from './ChatInput';
import { ChannelSelector } from './ChannelSelector';
import { ThinkingIndicator } from './ThinkingIndicator';

export function ChatPanel() {
  const [isOpen, setIsOpen] = useState(true);
  const [channelId, setChannelId] = useState(1);
  const [width, setWidth] = useState(380);
  const [isResizing, setIsResizing] = useState(false);
  const { messages, sendMessage, isThinking, isConnected } = useChat(channelId);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
    }
  }, [messages, isThinking]);

  // Resize logic
  const handleMouseDown = (e: React.MouseEvent) => {
    setIsResizing(true);
    e.preventDefault();
  };

  useEffect(() => {
    if (!isResizing) return;

    const handleMouseMove = (e: MouseEvent) => {
      const newWidth = window.innerWidth - e.clientX;
      setWidth(Math.max(320, Math.min(600, newWidth)));
    };

    const handleMouseUp = () => setIsResizing(false);

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isResizing]);

  return (
    <motion.aside
      initial={false}
      animate={{ width: isOpen ? width : 48 }}
      transition={{ duration: 0.2, ease: 'easeInOut' }}
      className="relative border-l border-[#27272A] bg-[#111113] flex flex-col"
      style={{ userSelect: isResizing ? 'none' : 'auto' }}
    >
      {/* Resize handle */}
      {isOpen && (
        <div
          onMouseDown={handleMouseDown}
          className="absolute left-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-[#3B82F6]/50 transition-colors z-10"
        />
      )}

      {/* Header */}
      <div className="p-4 border-b border-[#27272A] flex-shrink-0">
        {isOpen ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-[#FAFAFA] flex items-center gap-2">
                <MessageSquare size={16} />
                Chat
              </h2>
              <button
                onClick={() => setIsOpen(false)}
                className="p-1.5 hover:bg-[#1A1A1E] rounded transition-colors text-[#71717A] hover:text-[#FAFAFA]"
                aria-label="Collapse chat panel"
              >
                <PanelRightClose size={16} />
              </button>
            </div>
            <ChannelSelector value={channelId} onChange={setChannelId} />
            {!isConnected && (
              <div className="text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20 rounded px-2 py-1">
                Reconnecting...
              </div>
            )}
          </div>
        ) : (
          <button
            onClick={() => setIsOpen(true)}
            className="w-full p-2 hover:bg-[#1A1A1E] rounded transition-colors text-[#71717A] hover:text-[#FAFAFA]"
            aria-label="Expand chat panel"
          >
            <PanelRightOpen size={20} className="mx-auto" />
          </button>
        )}
      </div>

      {/* Content - only show when open */}
      {isOpen && (
        <>
          {/* Messages */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-3">
            {messages.length === 0 ? (
              <div className="text-center text-[#71717A] text-sm py-8">
                Start a conversation...
              </div>
            ) : (
              messages.map(msg => <ChatMessage key={msg.id} message={msg} projectId={undefined} />)
            )}
            {isThinking && <ThinkingIndicator />}
          </div>

          {/* Input */}
          <div className="p-4 border-t border-[#27272A] flex-shrink-0">
            <ChatInput onSend={sendMessage} disabled={!isConnected} />
          </div>
        </>
      )}
    </motion.aside>
  );
}
