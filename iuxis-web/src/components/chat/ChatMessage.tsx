import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { ChatMessage as ChatMessageType } from '@/lib/hooks';
import { ChatSaveAffordance } from './ChatSaveAffordance';

interface Props {
  message: ChatMessageType;
  projectId?: number;
}

export function ChatMessage({ message, projectId }: Props) {
  const isUser = message.role === 'user';
  const isError = message.status === 'error';
  const [saveSignalDismissed, setSaveSignalDismissed] = useState(false);

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'} mb-3 flex-col ${isUser ? 'items-end' : 'items-start'}`}>
      <div className={`max-w-[85%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed
        ${isUser
          ? 'bg-[#1E3A5F] text-blue-50 border border-[#3B82F6]/30 rounded-br-sm'
          : isError
            ? 'bg-red-500/10 text-red-200 border border-red-500/20'
            : 'bg-[#18181B] border border-[#27272A] text-[#E4E4E7] rounded-bl-sm'
        }`}
      >
        {isUser ? (
          <p>{message.content}</p>
        ) : (
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              h1: ({ children }) => <h1 className="text-xl font-bold mb-3 text-[#FAFAFA]">{children}</h1>,
              h2: ({ children }) => <h2 className="text-lg font-semibold mb-2 mt-4 text-[#FAFAFA]">{children}</h2>,
              h3: ({ children }) => <h3 className="text-base font-semibold mb-2 mt-3 text-[#FAFAFA]">{children}</h3>,
              p: ({ children }) => <p className="text-[#E4E4E7] mb-3 leading-relaxed">{children}</p>,
              ul: ({ children }) => <ul className="list-disc list-inside mb-3 space-y-1">{children}</ul>,
              ol: ({ children }) => <ol className="list-decimal list-inside mb-3 space-y-1">{children}</ol>,
              li: ({ children }) => <li className="text-[#E4E4E7]">{children}</li>,
              strong: ({ children }) => <strong className="font-semibold text-[#FAFAFA]">{children}</strong>,
              em: ({ children }) => <em className="italic text-[#FAFAFA]">{children}</em>,
              code: ({ className, children }) => {
                const isBlock = className?.includes('language-');
                return isBlock ? (
                  <pre className="bg-[#09090B] border border-[#27272A] rounded-lg p-3 my-2 overflow-x-auto">
                    <code className="font-mono text-xs text-[#A1A1AA]">{children}</code>
                  </pre>
                ) : (
                  <code className="bg-[#1A1A1E] px-1.5 py-0.5 rounded text-xs font-mono">{children}</code>
                );
              },
              a: ({ children, href }) => (
                <a href={href} className="text-[#3B82F6] hover:underline" target="_blank" rel="noopener noreferrer">
                  {children}
                </a>
              ),
              blockquote: ({ children }) => (
                <blockquote className="border-l-4 border-[#27272A] pl-4 my-3 text-[#A1A1AA] italic">
                  {children}
                </blockquote>
              ),
              table: ({ children }) => (
                <div className="overflow-x-auto my-3">
                  <table className="w-full border border-[#27272A]">{children}</table>
                </div>
              ),
              th: ({ children }) => (
                <th className="border border-[#27272A] px-3 py-2 bg-[#1A1A1E] text-left text-[#FAFAFA] font-semibold">
                  {children}
                </th>
              ),
              td: ({ children }) => (
                <td className="border border-[#27272A] px-3 py-2 text-[#E4E4E7]">
                  {children}
                </td>
              ),
            }}
          >
            {message.content}
          </ReactMarkdown>
        )}
      </div>

      {/* Save affordance - only for assistant messages with save_signal */}
      {!isUser && message.save_signal && !saveSignalDismissed && (
        <div className="max-w-[85%]">
          <ChatSaveAffordance
            saveSignal={message.save_signal}
            projectId={projectId}
            onSaved={(entryId) => {
              console.log(`Saved entry ${entryId}`)
            }}
            onDismiss={() => {
              setSaveSignalDismissed(true)
            }}
          />
        </div>
      )}
    </div>
  );
}
