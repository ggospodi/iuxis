import { useState, KeyboardEvent } from 'react';
import TextareaAutosize from 'react-textarea-autosize';
import { Send } from 'lucide-react';

const COMMANDS = [
  { label: 'generate briefing', description: 'Create morning briefing' },
  { label: 'generate schedule', description: 'Create daily schedule' },
  { label: 'generate insights', description: 'Analyze cross-project patterns' },
  { label: 'knowledge stats', description: 'Show knowledge entry counts' },
  { label: 'show projects', description: 'List all projects' },
  { label: 'show tasks', description: 'List active tasks' },
  { label: 'what do you know about ', description: 'Search knowledge base' },
  { label: 'add task to ', description: 'Create a new task' },
  { label: 'ingest files for ', description: 'Trigger file ingestion' },
];

interface Props {
  onSend: (message: string) => void;
  disabled?: boolean;
}

export function ChatInput({ onSend, disabled }: Props) {
  const [value, setValue] = useState('');
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);

  // Filter commands based on input
  const filtered = COMMANDS.filter(cmd =>
    cmd.label.toLowerCase().startsWith(value.toLowerCase()) && value.length > 0
  );

  // Update suggestions visibility
  const handleChange = (newValue: string) => {
    setValue(newValue);
    setShowSuggestions(newValue.length > 0 && filtered.length > 0);
    setSelectedIndex(0);
  };

  // Handle keyboard navigation and send
  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (showSuggestions && filtered.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex(prev => Math.min(prev + 1, filtered.length - 1));
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex(prev => Math.max(prev - 1, 0));
        return;
      }
      if (e.key === 'Tab') {
        e.preventDefault();
        setValue(filtered[selectedIndex].label);
        setShowSuggestions(false);
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        setShowSuggestions(false);
        return;
      }
    }

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (value.trim()) {
        onSend(value.trim());
        setValue('');
        setShowSuggestions(false);
      }
    }
  };

  const handleSend = () => {
    if (value.trim()) {
      onSend(value.trim());
      setValue('');
      setShowSuggestions(false);
    }
  };

  return (
    <div className="relative">
      {/* Autocomplete suggestions */}
      {showSuggestions && filtered.length > 0 && (
        <div className="absolute bottom-full mb-2 w-full bg-[#111113] border border-[#27272A] rounded-lg shadow-xl overflow-hidden z-10">
          {filtered.map((cmd, idx) => (
            <button
              key={cmd.label}
              className={`w-full px-4 py-2.5 text-left transition-colors ${
                idx === selectedIndex
                  ? 'bg-[#3B82F6]/20 border-l-2 border-[#3B82F6]'
                  : 'hover:bg-[#1A1A1E] border-l-2 border-transparent'
              }`}
              onClick={() => {
                setValue(cmd.label);
                setShowSuggestions(false);
              }}
              onMouseEnter={() => setSelectedIndex(idx)}
            >
              <div className="text-sm font-medium text-[#FAFAFA]">{cmd.label}</div>
              <div className="text-xs text-[#71717A] mt-0.5">{cmd.description}</div>
            </button>
          ))}
        </div>
      )}

      {/* Input area */}
      <div className="flex items-end gap-2">
        <div className="flex-1 relative">
          <TextareaAutosize
            value={value}
            onChange={(e) => handleChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message or command..."
            disabled={disabled}
            minRows={1}
            maxRows={6}
            className="w-full px-4 py-3 bg-[#1A1A1E] border border-[#27272A] rounded-lg text-sm text-[#FAFAFA] placeholder:text-[#71717A] focus:outline-none focus:border-[#3B82F6] focus:ring-2 focus:ring-[#3B82F6]/20 transition-all resize-none disabled:opacity-50 disabled:cursor-not-allowed"
          />
        </div>
        <button
          onClick={handleSend}
          disabled={disabled || !value.trim()}
          className="p-3 bg-[#3B82F6] text-white rounded-lg hover:bg-[#2563EB] transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex-shrink-0"
          aria-label="Send message"
        >
          <Send size={18} />
        </button>
      </div>
    </div>
  );
}
