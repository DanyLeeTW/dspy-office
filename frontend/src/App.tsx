import { useState } from 'react';
import { GoalInput } from './components/GoalInput';
import { Scratchpad } from './components/Scratchpad';
import { ToolPanel } from './components/ToolPanel';
import { MemoryPanel } from './components/MemoryPanel';
import { useAgentRunner } from './hooks/useAgentRunner';

function App() {
  const { steps, memories, tools, isRunning, currentGoal, goalTimestamp, run, reset } = useAgentRunner();
  const [showToolCallResult, setShowToolCallResult] = useState(true);
  const totalUsage = tools.reduce((sum, t) => sum + t.usageCount, 0);
  const activeTools = tools.filter(t => t.status === 'active').length;
  const completedSteps = steps.filter(s => s.status === 'complete').length;

  return (
    <div className="h-screen flex flex-col bg-surface overflow-hidden">
      {/* Header */}
      <header className="flex-shrink-0 border-b border-border-subtle bg-surface-raised px-6 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="text-2xl">🏢</div>
            <div>
              <h1 className="text-lg font-bold text-text-primary tracking-tight">DSPy Office</h1>
              <p className="text-xs text-text-muted">Self-evolving AI Agent Dashboard</p>
            </div>
          </div>
          <div className="flex items-center gap-4 text-xs text-text-muted">
            {isRunning && (
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-accent animate-pulse-glow" />
                <span className="text-accent">Agent Running</span>
              </div>
            )}
            <div className="flex items-center gap-3 bg-surface-overlay px-3 py-1.5 rounded-lg border border-border-subtle">
              <span>Steps: <span className="text-text-primary font-medium">{completedSteps}/{steps.length}</span></span>
              <span className="text-border-subtle">|</span>
              <span>Tools: <span className="text-text-primary font-medium">{activeTools} active</span></span>
              <span className="text-border-subtle">|</span>
              <span>Calls: <span className="text-text-primary font-medium">{totalUsage}</span></span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar */}
        <aside className="w-72 flex-shrink-0 border-r border-border-subtle bg-surface-raised overflow-y-auto p-4">
          <ToolPanel tools={tools} />
          <div className="border-t border-border-subtle my-4" />
          <MemoryPanel memories={memories} />
        </aside>

        {/* Main Area */}
        <main className="flex-1 flex flex-col p-6 overflow-hidden">
          <GoalInput onSubmit={run} isRunning={isRunning} onReset={reset} />

          {/* Options Bar */}
          <div className="flex items-center gap-4 mb-3 px-1">
            <label className="flex items-center gap-2 text-xs text-text-muted cursor-pointer select-none">
              <input
                type="checkbox"
                checked={showToolCallResult}
                onChange={(e) => setShowToolCallResult(e.target.checked)}
                className="w-3.5 h-3.5 rounded border-border-subtle text-accent focus:ring-accent/50 cursor-pointer"
              />
              <span>Show Tool Results</span>
            </label>
          </div>

          <Scratchpad steps={steps} currentGoal={currentGoal} goalTimestamp={goalTimestamp} showToolCallResult={showToolCallResult} />
        </main>
      </div>
    </div>
  );
}

export default App;
