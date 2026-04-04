import { useState, useRef } from 'react';

const exampleGoals = [
  'Research the latest AI papers and summarize findings',
  'Set up a daily health check and notify me if anything fails',
  'Create a Python script that monitors my GitHub repos for new issues',
  'Analyze my system logs and find any security concerns',
];

interface Attachment {
  token: string;   // shown in input, e.g. "@report.pdf"
  content: string; // expanded on submit
}

interface Props {
  onSubmit: (goal: string) => void;
  isRunning: boolean;
  onReset: () => void;
}

export function GoalInput({ onSubmit, isRunning, onReset }: Props) {
  const [goal, setGoal] = useState('');
  const [isParsing, setIsParsing] = useState(false);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleSubmit = () => {
    if (!goal.trim() && attachments.length === 0) return;
    if (isRunning) return;

    let fullGoal = goal;
    for (const att of attachments) {
      fullGoal = fullGoal.replace(att.token, `--- ${att.token.slice(1)} ---\n${att.content}`);
    }

    onSubmit(fullGoal.trim());
    setAttachments([]);
  };

  const handlePaste = async () => {
    try {
      const text = await navigator.clipboard.readText();
      setGoal(prev => prev ? `${prev}\n${text}` : text);
    } catch {
      // Clipboard access denied
    }
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsParsing(true);
    try {
      let content: string;

      if (file.name.toLowerCase().endsWith('.pdf')) {
        const formData = new FormData();
        formData.append('file', file);
        const response = await fetch('/api/parse/pdf', { method: 'POST', body: formData });
        const result = await response.json();
        if (!result.success) throw new Error(result.error);
        content = result.text;
      } else {
        content = await file.text();
      }

      const token = `@${file.name}`;
      setAttachments(prev => [...prev, { token, content }]);
      setGoal(prev => prev ? `${prev} ${token}` : token);
    } catch (err) {
      console.error('[DEBUG] Failed to read file:', err);
    } finally {
      setIsParsing(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  return (
    <div className="mb-6">
      <div className="flex items-center gap-3 mb-3">
        <div className="w-2 h-2 rounded-full bg-accent animate-pulse-glow" />
        <h2 className="text-sm font-semibold text-text-secondary uppercase tracking-wider">Agent Goal</h2>
      </div>
      <div className="flex gap-2">
        <input
          type="text"
          value={goal}
          onChange={(e) => {
            const next = e.target.value;
            setAttachments(prev => prev.filter(a => next.includes(a.token)));
            setGoal(next);
          }}
          onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
          placeholder="What should the agent do?"
          disabled={isRunning}
          className="flex-1 bg-surface-overlay border border-border-subtle rounded-lg px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors disabled:opacity-50"
        />
        {!isRunning && (
          <>
            <button
              onClick={handlePaste}
              className="px-3 py-3 bg-surface-overlay text-text-muted border border-border-subtle rounded-lg hover:text-text-secondary hover:border-accent/30 transition-colors"
              title="Paste from clipboard"
            >
              📋
            </button>
            <label
              className={`px-3 py-3 border rounded-lg transition-colors cursor-pointer ${
                isParsing
                  ? 'bg-accent/20 text-accent border-accent/30'
                  : 'bg-surface-overlay text-text-muted border-border-subtle hover:text-text-secondary hover:border-accent/30'
              }`}
              title={isParsing ? 'Parsing...' : 'Attach file'}
            >
              {isParsing ? '⏳' : '📎'}
              <input
                ref={fileInputRef}
                type="file"
                onChange={handleFileSelect}
                className="hidden"
                disabled={isParsing}
              />
            </label>
          </>
        )}
        {isRunning ? (
          <button
            onClick={onReset}
            className="px-6 py-3 bg-status-error/20 text-status-error border border-status-error/30 rounded-lg font-medium hover:bg-status-error/30 transition-colors"
          >
            Stop
          </button>
        ) : (
          <button
            onClick={handleSubmit}
            disabled={!goal.trim() && attachments.length === 0}
            className="px-6 py-3 bg-accent/20 text-accent border border-accent/30 rounded-lg font-medium hover:bg-accent/30 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
            Run
          </button>
        )}
      </div>

      {!isRunning && attachments.length === 0 && (
        <div className="flex flex-wrap gap-2 mt-3">
          {exampleGoals.map((eg) => (
            <button
              key={eg}
              onClick={() => setGoal(eg)}
              className="text-xs px-3 py-1.5 bg-surface-overlay border border-border-subtle rounded-full text-text-muted hover:text-text-secondary hover:border-accent/30 transition-colors"
            >
              {eg.length > 50 ? eg.slice(0, 50) + '…' : eg}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
