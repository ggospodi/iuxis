import './globals.css';
import { Sidebar } from '@/components/layout/Sidebar';
import { ChatPanel } from '@/components/chat/ChatPanel';

export const metadata = {
  title: 'Iuxis — AI Chief of Staff',
  description: 'Local-first AI assistant for project management',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-[#09090B] text-[#FAFAFA]">
        <div className="flex h-screen overflow-hidden">
          <Sidebar />
          <main className="flex-1 overflow-y-auto">
            {children}
          </main>
          <ChatPanel />
        </div>
      </body>
    </html>
  );
}
