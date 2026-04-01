function priorityColor(priority: number): string {
  const colors: Record<number, string> = {
    1: '#EF4444',
    2: '#3B82F6',
    3: '#F59E0B',
    4: '#6B7280',
    5: '#6B7280',
  };
  return colors[priority] || '#6B7280';
}

interface StatusDotProps {
  status: string;
  priority?: number;
  pulse?: boolean;
}

export function StatusDot({ status, priority, pulse = false }: StatusDotProps) {
  const color = priority !== undefined ? priorityColor(priority) : '#10B981';

  return (
    <div className="relative flex items-center justify-center w-2 h-2">
      <div
        className="w-2 h-2 rounded-full"
        style={{ backgroundColor: color }}
      />
      {pulse && (
        <div
          className="absolute inset-0 w-2 h-2 rounded-full animate-ping"
          style={{ backgroundColor: color }}
        />
      )}
    </div>
  );
}
