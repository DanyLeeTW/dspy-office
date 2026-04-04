import type { MemoryItem } from '../types';

const layerConfig = {
  session: { label: 'Session', icon: '💬', color: 'text-accent', bg: 'bg-accent/10', border: 'border-accent/20' },
  compressed: { label: 'Compressed', icon: '🗜️', color: 'text-amber-400', bg: 'bg-amber-400/10', border: 'border-amber-400/20' },
  retrieved: { label: 'Retrieved', icon: '🔮', color: 'text-purple-400', bg: 'bg-purple-400/10', border: 'border-purple-400/20' },
};

interface Props {
  memories: MemoryItem[];
}

export function MemoryPanel({ memories }: Props) {
  const grouped = {
    session: memories.filter(m => m.layer === 'session'),
    compressed: memories.filter(m => m.layer === 'compressed'),
    retrieved: memories.filter(m => m.layer === 'retrieved'),
  };

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <span className="text-sm">🧠</span>
        <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">Three-Layer Memory</h3>
      </div>
      <div className="space-y-3">
        {(Object.entries(grouped) as [keyof typeof layerConfig, MemoryItem[]][]).map(([layer, items]) => {
          const config = layerConfig[layer];
          return (
            <div key={layer} className={`rounded-lg border ${config.border} ${config.bg} p-2.5`}>
              <div className="flex items-center gap-1.5 mb-2">
                <span className="text-xs">{config.icon}</span>
                <span className={`text-[10px] font-semibold uppercase tracking-wider ${config.color}`}>
                  {config.label}
                </span>
                <span className="text-[10px] text-text-muted">({items.length})</span>
              </div>
              {items.length === 0 ? (
                <div className="text-[10px] text-text-muted italic px-1">No items yet</div>
              ) : (
                <div className="space-y-1">
                  {items.map((item, i) => (
                    <div key={i} className="flex items-start gap-1.5 animate-slide-in">
                      <div className={`w-1 h-1 rounded-full mt-1.5 flex-shrink-0 ${config.color.replace('text-', 'bg-')}`} />
                      <div className="flex-1 min-w-0">
                        <div className="text-[11px] text-text-secondary leading-tight" title={item.content}>
                          {item.content.length > 50 ? item.content.slice(0, 50) + '…' : item.content}
                        </div>
                        {item.relevance !== undefined && (
                          <div className="text-[9px] text-text-muted mt-0.5">
                            relevance: {(item.relevance * 100).toFixed(0)}%
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
