export interface Tool {
  name: string;
  icon: string;
  description: string;
  usageCount: number;
  status: 'idle' | 'active';
}

export interface ToolCall {
  tool: string;
  args: Record<string, string>;
  result?: string;
  status: 'pending' | 'running' | 'complete' | 'error';
}

export interface AgentStep {
  id: string;
  type: 'thinking' | 'tool_call' | 'result' | 'decompose';
  content: string;
  toolCall?: ToolCall;
  status: 'pending' | 'running' | 'complete' | 'error';
}

export interface MemoryItem {
  layer: 'session' | 'compressed' | 'retrieved';
  content: string;
  timestamp: number;
  relevance?: number;
}

export interface AgentTrace {
  goal: string;
  keywords: string[];
  steps: AgentStep[];
  memories: MemoryItem[];
}
