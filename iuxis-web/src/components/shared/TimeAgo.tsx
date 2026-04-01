import { timeAgo } from '@/lib/utils';

interface TimeAgoProps {
  date: string;
  className?: string;
}

export function TimeAgo({ date, className = '' }: TimeAgoProps) {
  return (
    <span className={`text-xs text-[#71717A] ${className}`}>
      {timeAgo(date)}
    </span>
  );
}
