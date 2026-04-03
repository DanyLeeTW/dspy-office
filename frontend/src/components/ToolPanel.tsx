import type { Tool } from '../types';

interface Props {
  tools: Tool[];
}

export function ToolPanel({ tools }: Props) {
  return (
    <div className="mb-6">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-sm">🧰</span>
        <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">Tool Registry</h3>
        <span className="text-xs text-text-muted">({tools.length})</span>
      </div>
      <div className="space-y-1.5">
        {tools.map((tool) => (
          <div
            key={tool.name}
            className={`flex items-center gap-2.5 px-3 py-2 rounded-lg transition-all duration-300 ${
              tool.status === 'active'
                ? 'bg-accent/10 border border-accent/30'
                : 'bg-surface-overlay/50 border border-transparent hover:border-border-subtle'
            }`}
          >
            <span className="text-sm flex-shrink-0">{tool.icon}</span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className={`text-xs mono font-medium truncate ${
                  tool.status === 'active' ? 'text-accent' : 'text-text-primary'
                }`}>
                  {tool.name}
                </span>
                {tool.status === 'active' && (
                  <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse-glow flex-shrink-0" />
                )}
              </div>
              <div className="text-[10px] text-text-muted truncate">{tool.description}</div>
            </div>
            {tool.usageCount > 0 && (
              <span className="text-[10px] bg-accent/20 text-accent px-1.5 py-0.5 rounded-full flex-shrink-0">
                {tool.usageCount}×
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
