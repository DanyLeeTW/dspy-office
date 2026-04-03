import type { AgentStep } from '../types';
import { useEffect, useRef } from 'react';

function StatusDot({ status }: { status: AgentStep['status'] }) {
  const colors: Record<string, string> = {
    pending: 'bg-status-pending',
    running: 'bg-status-running animate-pulse-glow',
    complete: 'bg-status-complete',
    error: 'bg-status-error',
  };
  return <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${colors[status]}`} />;
}

function StepIcon({ type }: { type: AgentStep['type'] }) {
  const icons: Record<string, string> = {
    thinking: '💭',
    tool_call: '⚙️',
    result: '📋',
    decompose: '🔀',
  };
  return <span className="text-sm">{icons[type]}</span>;
}

interface Props {
  steps: AgentStep[];
  currentGoal: string;
}

export function Scratchpad({ steps, currentGoal }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [steps]);

  if (!currentGoal && steps.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-text-muted">
        <div className="text-center">
          <div className="text-4xl mb-4">🤖</div>
          <p className="text-lg">Enter a goal to start the agent</p>
          <p className="text-sm mt-2">Watch as it decomposes tasks and executes tool calls in real-time</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto pr-2">
      {currentGoal && (
        <div className="mb-4 p-3 bg-accent/5 border border-accent/20 rounded-lg animate-slide-in">
          <div className="text-xs text-accent font-semibold uppercase tracking-wider mb-1">Goal</div>
          <div className="text-text-primary">{currentGoal}</div>
        </div>
      )}
      <div className="space-y-2">
        {steps.map((step) => (
          <div key={step.id} className="animate-slide-in">
            {step.type === 'thinking' && (
              <div className="flex items-start gap-3 p-3 bg-surface-overlay/50 rounded-lg border border-border-subtle/50">
                <StatusDot status={step.status} />
                <StepIcon type={step.type} />
                <div className="flex-1 min-w-0">
                  <div className="text-xs text-text-muted uppercase tracking-wider mb-1">Thinking</div>
                  <div className="text-sm text-text-secondary italic">{step.content}</div>
                </div>
              </div>
            )}
            {step.type === 'decompose' && (
              <div className="flex items-start gap-3 p-3 bg-accent/5 rounded-lg border border-accent/10">
                <StatusDot status={step.status} />
                <StepIcon type={step.type} />
                <div className="flex-1 min-w-0">
                  <div className="text-xs text-accent uppercase tracking-wider mb-1">Task Decomposition</div>
                  <pre className="text-sm text-text-primary whitespace-pre-wrap mono">{step.content}</pre>
                </div>
              </div>
            )}
            {step.type === 'tool_call' && step.toolCall && (
              <div className="flex items-start gap-3 p-3 bg-surface-overlay rounded-lg border border-border-subtle">
                <StatusDot status={step.status} />
                <StepIcon type={step.type} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs font-semibold text-accent mono">{step.toolCall.tool}()</span>
                    <span className={`text-xs px-1.5 py-0.5 rounded ${
                      step.toolCall.status === 'running' ? 'bg-status-running/20 text-status-running' :
                      step.toolCall.status === 'complete' ? 'bg-status-complete/20 text-status-complete' :
                      'bg-surface-raised text-text-muted'
                    }`}>
                      {step.toolCall.status}
                    </span>
                  </div>
                  <div className="text-xs text-text-muted mb-1">{step.content}</div>
                  <div className="bg-surface/80 rounded p-2 mt-1">
                    <pre className="text-xs text-text-secondary mono whitespace-pre-wrap">
                      {Object.entries(step.toolCall.args).map(([k, v]) => `${k}: ${v}`).join('\n')}
                    </pre>
                  </div>
                </div>
              </div>
            )}
            {step.type === 'result' && (
              <div className="flex items-start gap-3 p-3 ml-6 rounded-lg">
                <StatusDot status={step.status} />
                <StepIcon type={step.type} />
                <div className="flex-1 min-w-0">
                  <pre className="text-sm text-text-secondary mono whitespace-pre-wrap">{step.content}</pre>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
      <div ref={bottomRef} />
    </div>
  );
}
