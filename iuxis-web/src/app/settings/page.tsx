'use client';

import { useState, useEffect } from 'react';
import { Settings, Brain, Github, Sliders, CheckCircle, AlertCircle, Loader2, FolderOpen } from 'lucide-react';
import { api } from '@/lib/api';

type SaveState = 'idle' | 'saving' | 'saved' | 'error';

function SettingSection({ title, icon: Icon, children }: { title: string; icon: any; children: React.ReactNode }) {
  return (
    <div className="border border-[#27272A] bg-[#111113] rounded-xl p-6">
      <div className="flex items-center gap-2.5 mb-5 pb-4 border-b border-[#27272A]">
        <Icon size={18} className="text-[#3B82F6]" />
        <h2 className="text-sm font-semibold text-[#FAFAFA] uppercase tracking-wider">{title}</h2>
      </div>
      <div className="space-y-5">{children}</div>
    </div>
  );
}

function SettingRow({ label, description, children }: { label: string; description?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-8">
      <div className="flex-1">
        <div className="text-sm font-medium text-[#FAFAFA]">{label}</div>
        {description && <div className="text-xs text-[#71717A] mt-0.5">{description}</div>}
      </div>
      <div className="flex-shrink-0">{children}</div>
    </div>
  );
}

function TextInput({ value, onChange, placeholder, type = 'text', mono = false }: {
  value: string; onChange: (v: string) => void; placeholder?: string; type?: string; mono?: boolean;
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      className={`w-64 px-3 py-2 bg-[#1A1A1E] border border-[#27272A] rounded-lg text-sm text-[#FAFAFA] placeholder:text-[#3F3F46] focus:outline-none focus:border-[#3B82F6] focus:ring-1 focus:ring-[#3B82F6]/20 transition-all ${mono ? 'font-mono' : ''}`}
    />
  );
}

function Toggle({ enabled, onChange }: { enabled: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!enabled)}
      className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${enabled ? 'bg-[#3B82F6]' : 'bg-[#27272A]'}`}
    >
      <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${enabled ? 'translate-x-4.5' : 'translate-x-0.5'}`} />
    </button>
  );
}

function SelectInput({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: { value: string; label: string }[] }) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      className="w-64 px-3 py-2 bg-[#1A1A1E] border border-[#27272A] rounded-lg text-sm text-[#FAFAFA] focus:outline-none focus:border-[#3B82F6] focus:ring-1 focus:ring-[#3B82F6]/20"
    >
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

export default function SettingsPage() {
  // LLM
  const [lmStudioUrl, setLmStudioUrl] = useState('http://127.0.0.1:1234');
  const [ollamaUrl, setOllamaUrl] = useState('http://127.0.0.1:11434');
  const [primaryModel, setPrimaryModel] = useState('lmstudio');
  const [modelName, setModelName] = useState('qwen3.5-35b-a3b');

  // GitHub
  const [githubPat, setGithubPat] = useState('');
  const [githubEnabled, setGithubEnabled] = useState(false);
  const [githubOrg, setGithubOrg] = useState('');
  const [backfillDays, setBackfillDays] = useState('60');

  // System
  const [briefingTime, setBriefingTime] = useState('08:00');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [refreshInterval, setRefreshInterval] = useState('300');
  const [maxProjects, setMaxProjects] = useState('12');

  // Save state
  const [saveState, setSaveState] = useState<SaveState>('idle');
  const [testState, setTestState] = useState<SaveState>('idle');
  const [isLoading, setIsLoading] = useState(true);

  // Load settings on mount
  useEffect(() => {
    const loadSettings = async () => {
      try {
        const settings = await api.getSettings();
        console.log('Loaded settings:', settings);

        // LLM settings
        setPrimaryModel(settings.llm_backend || 'ollama');
        setModelName(settings.llm_model || 'qwen2.5:32b');
        setLmStudioUrl(settings.lmstudio_url || 'http://127.0.0.1:1234');
        setOllamaUrl(settings.ollama_url || 'http://127.0.0.1:11434');

        // GitHub settings
        setGithubEnabled(settings.github_enabled === 'true');
        setGithubOrg(settings.github_org || '');
        setBackfillDays(settings.backfill_days || '60');

        // System settings
        setBriefingTime(settings.briefing_time || '08:00');
        setAutoRefresh(settings.auto_refresh === 'true');
        setRefreshInterval(settings.refresh_interval || '300');
        setMaxProjects(settings.max_projects || '12');

        setIsLoading(false);
      } catch (err) {
        console.error('Failed to load settings:', err);
        setIsLoading(false);
      }
    };

    loadSettings();
  }, []);

  const handleSave = async () => {
    setSaveState('saving');

    try {
      // Save GitHub PAT if provided
      if (githubPat) {
        try {
          await fetch('http://localhost:8000/api/github/test', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token: githubPat }),
          });
        } catch (err) {
          console.error('Failed to save GitHub token:', err);
        }
      }

      // Save all settings
      await api.updateSettings({
        llm_backend: primaryModel,
        llm_model: modelName,
        lmstudio_url: lmStudioUrl,
        ollama_url: ollamaUrl,
        github_enabled: String(githubEnabled),
        github_org: githubOrg,
        backfill_days: backfillDays,
        briefing_time: briefingTime,
        auto_refresh: String(autoRefresh),
        refresh_interval: refreshInterval,
        max_projects: maxProjects,
      });

      setSaveState('saved');
      setTimeout(() => setSaveState('idle'), 2500);
    } catch (err) {
      console.error('Failed to save settings:', err);
      setSaveState('error');
      setTimeout(() => setSaveState('idle'), 2500);
    }
  };

  const testLLMConnection = async () => {
    // placeholder — would ping the endpoint
    alert('Connection test coming soon');
  };

  const testGitHubConnection = async () => {
    if (!githubPat) {
      alert('Please enter a GitHub Personal Access Token');
      return;
    }

    setTestState('saving');
    try {
      const response = await fetch('http://localhost:8000/api/github/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: githubPat }),
      });

      if (response.ok) {
        const data = await response.json();
        setTestState('saved');
        alert(`Connected successfully as ${data.username || data.name}`);
        setTimeout(() => setTestState('idle'), 2500);
      } else {
        const data = await response.json();
        setTestState('error');
        alert(`Connection failed: ${data.detail || 'Unknown error'}`);
        setTimeout(() => setTestState('idle'), 2500);
      }
    } catch (err) {
      setTestState('error');
      alert(`Connection failed: ${err}`);
      setTimeout(() => setTestState('idle'), 2500);
    }
  };

  return (
    <div className="p-6 max-w-[900px] mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Settings className="w-6 h-6 text-[#3B82F6]" />
          <h1 className="text-2xl font-bold">Settings</h1>
        </div>
        <button
          onClick={handleSave}
          disabled={saveState === 'saving'}
          className="flex items-center gap-2 px-4 py-2 bg-[#3B82F6] hover:bg-[#2563EB] disabled:opacity-60 text-white text-sm font-medium rounded-lg transition-colors"
        >
          {saveState === 'saving' && <Loader2 size={14} className="animate-spin" />}
          {saveState === 'saved' && <CheckCircle size={14} />}
          {saveState === 'error' && <AlertCircle size={14} />}
          {saveState === 'idle' && 'Save Changes'}
          {saveState === 'saving' && 'Saving...'}
          {saveState === 'saved' && 'Saved'}
          {saveState === 'error' && 'Error'}
        </button>
      </div>

      {/* LLM Configuration */}
      <SettingSection title="LLM Configuration" icon={Brain}>
        <SettingRow
          label="Primary LLM Provider"
          description="Which inference server Iuxis sends requests to"
        >
          <SelectInput
            value={primaryModel}
            onChange={setPrimaryModel}
            options={[
              { value: 'lmstudio', label: 'LM Studio' },
              { value: 'ollama', label: 'Ollama' },
            ]}
          />
        </SettingRow>

        <SettingRow
          label="LM Studio Endpoint"
          description="OpenAI-compatible server URL"
        >
          <div className="flex gap-2">
            <TextInput value={lmStudioUrl} onChange={setLmStudioUrl} placeholder="http://127.0.0.1:1234" mono />
            <button
              onClick={testLLMConnection}
              className="px-3 py-2 text-xs text-[#71717A] hover:text-[#FAFAFA] border border-[#27272A] hover:border-[#3B82F6] rounded-lg transition-colors whitespace-nowrap"
            >
              Test
            </button>
          </div>
        </SettingRow>

        <SettingRow
          label="Ollama Endpoint"
          description="Fallback inference server URL"
        >
          <TextInput value={ollamaUrl} onChange={setOllamaUrl} placeholder="http://127.0.0.1:11434" mono />
        </SettingRow>

        <SettingRow
          label="Active Model"
          description="Model name loaded in your inference server"
        >
          <TextInput value={modelName} onChange={setModelName} placeholder="qwen3.5-35b-a3b" mono />
        </SettingRow>
      </SettingSection>

      {/* GitHub Scanner */}
      <SettingSection title="GitHub Scanner" icon={Github}>
        <SettingRow
          label="Enable GitHub Scanner"
          description="Automatically scan repos for commits, PRs, and activity"
        >
          <Toggle enabled={githubEnabled} onChange={setGithubEnabled} />
        </SettingRow>

        <SettingRow
          label="Personal Access Token"
          description="GitHub PAT with repo:read scope — never leaves your machine"
        >
          <div className="flex gap-2">
            <TextInput
              value={githubPat}
              onChange={setGithubPat}
              placeholder="ghp_••••••••••••••••••••"
              type="password"
              mono
            />
            <button
              onClick={testGitHubConnection}
              disabled={testState === 'saving'}
              className="px-3 py-2 text-xs text-[#71717A] hover:text-[#FAFAFA] border border-[#27272A] hover:border-[#3B82F6] rounded-lg transition-colors whitespace-nowrap disabled:opacity-60 flex items-center gap-1.5"
            >
              {testState === 'saving' && <Loader2 size={12} className="animate-spin" />}
              {testState === 'saved' && <CheckCircle size={12} />}
              {testState === 'error' && <AlertCircle size={12} />}
              {testState === 'idle' && 'Test'}
              {testState === 'saving' && 'Testing'}
              {testState === 'saved' && 'OK'}
              {testState === 'error' && 'Failed'}
            </button>
          </div>
        </SettingRow>

        <SettingRow
          label="Organization / Username"
          description="GitHub org or personal account to scan"
        >
          <TextInput value={githubOrg} onChange={setGithubOrg} placeholder="your-org-or-username" />
        </SettingRow>

        <SettingRow
          label="Backfill Period"
          description="How many days of history to import on first run"
        >
          <SelectInput
            value={backfillDays}
            onChange={setBackfillDays}
            options={[
              { value: '7', label: '7 days' },
              { value: '30', label: '30 days' },
              { value: '60', label: '60 days' },
              { value: '90', label: '90 days' },
            ]}
          />
        </SettingRow>
      </SettingSection>

      {/* System Preferences */}
      <SettingSection title="System Preferences" icon={Sliders}>
        <SettingRow
          label="Inbox Folder"
          description="Drop files here to automatically ingest them into Iuxis"
        >
          <div className="flex items-center gap-2">
            <input
              type="text"
              value="~/iuxis-inbox/"
              readOnly
              className="w-64 px-3 py-2 bg-[#0A0A0F] border border-[#27272A] rounded-lg text-sm text-[#71717A] font-mono cursor-not-allowed"
            />
            <button
              onClick={() => api.openInbox()}
              className="flex items-center gap-1.5 px-3 py-2 text-xs text-[#FAFAFA] bg-[#1A1A1E] hover:bg-[#27272A] border border-[#27272A] hover:border-[#3B82F6] rounded-lg transition-colors whitespace-nowrap"
            >
              <FolderOpen size={14} />
              Open Folder
            </button>
          </div>
        </SettingRow>

        <SettingRow
          label="Morning Briefing Time"
          description="When to auto-generate your daily briefing"
        >
          <TextInput value={briefingTime} onChange={setBriefingTime} type="time" />
        </SettingRow>

        <SettingRow
          label="Auto-refresh Dashboard"
          description="Refresh project data in the background"
        >
          <Toggle enabled={autoRefresh} onChange={setAutoRefresh} />
        </SettingRow>

        <SettingRow
          label="Refresh Interval"
          description="How often to poll for new data (seconds)"
        >
          <SelectInput
            value={refreshInterval}
            onChange={setRefreshInterval}
            options={[
              { value: '60', label: '1 minute' },
              { value: '300', label: '5 minutes' },
              { value: '600', label: '10 minutes' },
              { value: '1800', label: '30 minutes' },
            ]}
          />
        </SettingRow>

        <SettingRow
          label="Sidebar Project Limit"
          description="Max projects shown in the sidebar list"
        >
          <SelectInput
            value={maxProjects}
            onChange={setMaxProjects}
            options={[
              { value: '8', label: '8 projects' },
              { value: '12', label: '12 projects' },
              { value: '16', label: '16 projects' },
              { value: '20', label: '20 projects' },
            ]}
          />
        </SettingRow>
      </SettingSection>

      {/* Version */}
      <div className="text-xs text-[#3F3F46] text-center pb-2">
        Iuxis v0.7.0 — local-first, private by design
      </div>
    </div>
  );
}
