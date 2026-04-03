import { useState } from 'react';

const exampleGoals = [
  'Research the latest AI papers and summarize findings',
  'Set up a daily health check and notify me if anything fails',
  'Create a Python script that monitors my GitHub repos for new issues',
  'Analyze my system logs and find any security concerns',
];

interface Props {
  onSubmit: (goal: string) => void;
  isRunning: boolean;
  onReset: () => void;
}

export function GoalInput({ onSubmit, isRunning, onReset }: Props) {
  const [goal, setGoal] = useState('');

  const handleSubmit = () => {
    if (goal.trim() && !isRunning) {
      onSubmit(goal.trim());
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
          onChange={(e) => setGoal(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
          placeholder="What should the agent do?"
          disabled={isRunning}
          className="flex-1 bg-surface-overlay border border-border-subtle rounded-lg px-4 py-3 text-text-primary placeholder-text-muted focus:outline-none focus:border-accent transition-colors disabled:opacity-50"
        />
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
            disabled={!goal.trim()}
            className="px-6 py-3 bg-accent/20 text-accent border border-accent/30 rounded-lg font-medium hover:bg-accent/30 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
            Run
          </button>
        )}
      </div>
      {!isRunning && (
        <div className="flex flex-wrap gap-2 mt-3">
          {exampleGoals.map((eg) => (
            <button
              key={eg}
              onClick={() => { setGoal(eg); }}
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
