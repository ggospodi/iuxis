import { useState, useEffect } from 'react';
import { api } from '@/lib/api';
import type { Channel } from '@/lib/types';

interface Props {
  value: number;
  onChange: (channelId: number) => void;
}

export function ChannelSelector({ value, onChange }: Props) {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getChannels()
      .then(data => {
        setChannels(data.channels);
        setLoading(false);
      })
      .catch(err => {
        console.error('Failed to fetch channels:', err);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="h-9 bg-[#1A1A1E] border border-[#27272A] rounded-lg animate-pulse" />
    );
  }

  return (
    <select
      value={value}
      onChange={(e) => onChange(Number(e.target.value))}
      className="w-full px-3 py-2 bg-[#1A1A1E] border border-[#27272A] rounded-lg text-sm text-[#FAFAFA] focus:outline-none focus:border-[#3B82F6] focus:ring-2 focus:ring-[#3B82F6]/20 transition-all"
    >
      {channels.map(channel => (
        <option key={channel.id} value={channel.id} className="bg-[#1A1A1E] text-[#FAFAFA]">
          {channel.name}{channel.project_name ? ` (${channel.project_name})` : ''}
        </option>
      ))}
    </select>
  );
}
