import type { AgentStep, ToolCall } from '../types';

// Check if API key is configured
export function isApiKeyConfigured(): boolean {
  return !!import.meta.env.VITE_OPENAI_API_KEY;
}

// Callbacks for agent runner
interface AgentCallbacks {
  onStep: (step: AgentStep) => void;
  onToolCall: (toolCall: ToolCall) => void;
  onComplete: () => void;
  onError: (error: Error) => void;
}

// Run agent with real LLM (when API key is configured)
export async function runAgent(
  goal: string,
  callbacks: AgentCallbacks,
  _memoryContext?: string,
  signal?: AbortSignal
): Promise<void> {
  // This is a placeholder for real LLM integration
  // In production, this would use the AI SDK to stream responses

  try {
    // Simulate thinking step
    callbacks.onStep({
      id: `step-${Date.now()}-thinking`,
      type: 'thinking',
      content: `Processing goal: "${goal}"`,
      status: 'running'
    });

    await new Promise(resolve => setTimeout(resolve, 1000));

    if (signal?.aborted) return;

    // Complete thinking
    callbacks.onStep({
      id: `step-${Date.now()}-thinking`,
      type: 'thinking',
      content: `Processing goal: "${goal}"`,
      status: 'complete'
    });

    callbacks.onComplete();
  } catch (error) {
    if (signal?.aborted) return;
    callbacks.onError(error instanceof Error ? error : new Error('Unknown error'));
  }
}
