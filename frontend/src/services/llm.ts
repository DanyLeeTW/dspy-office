import type { AgentStep, ToolCall } from '../types';

// Returns '' in dev (proxy handles /api/*), or the explicit base URL in production
const getApiBaseUrl = () => import.meta.env.VITE_API_BASE_URL || '';

// Check if API is configured
export function isApiKeyConfigured(): boolean {
  return true; // Backend handles API key
}

// Callbacks for agent runner
interface AgentCallbacks {
  onStep: (step: AgentStep) => void;
  onToolCall: (toolCall: ToolCall) => void;
  onComplete: (data?: { memoryContext?: string }) => void;
  onError: (error: Error) => void;
}

// Unique ID counter to avoid duplicate keys
let stepCounter = 0;
const generateStepId = (type: string) => `step-${Date.now()}-${++stepCounter}-${type}`;

/**
 * Run agent by calling backend API
 */
export async function runAgent(
  goal: string,
  callbacks: AgentCallbacks,
  memoryContext?: string,
  signal?: AbortSignal
): Promise<void> {
  const baseUrl = getApiBaseUrl();

  try {
    // Emit thinking step
    const thinkingStepId = generateStepId('thinking');
    callbacks.onStep({
      id: thinkingStepId,
      type: 'thinking',
      content: `Analyzing goal: "${goal}"`,
      status: 'running'
    });

    // Call backend API
    const response = await fetch(`${baseUrl}/api/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        message: goal,
        context: memoryContext,
      }),
      signal,
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status} ${response.statusText}`);
    }

    // Complete thinking step
    callbacks.onStep({
      id: generateStepId('thinking-complete'),
      type: 'thinking',
      content: `Analyzing goal: "${goal}" - Complete`,
      status: 'complete'
    });

    const text = await response.text();
    if (!text) throw new Error('Empty response from server');
    const data = JSON.parse(text);

    // Emit tool call steps if available
    if (data.tool_calls && Array.isArray(data.tool_calls)) {
      for (const tc of data.tool_calls) {
        // Skip 'finish' tool which is internal
        if (tc.tool === 'finish') continue;

        callbacks.onToolCall({
          tool: tc.tool,
          args: tc.args || {},
          result: tc.result,
          status: 'complete'
        });

        callbacks.onStep({
          id: generateStepId('tool_call'),
          type: 'tool_call',
          content: tc.thought || tc.result || `Executed ${tc.tool}`,
          toolCall: {
            tool: tc.tool,
            args: tc.args || {},
            result: tc.result,
            status: 'complete'
          },
          status: 'complete'
        });
      }
    }

    // Emit result step
    callbacks.onStep({
      id: generateStepId('result'),
      type: 'result',
      content: data.response || data.content || data.message || JSON.stringify(data),
      status: 'complete'
    });

    callbacks.onComplete({
      memoryContext: data.memory_context
    });
  } catch (error) {
    if (signal?.aborted) return;

    const errorMessage = error instanceof Error ? error.message : 'Unknown error';

    callbacks.onStep({
      id: generateStepId('error'),
      type: 'result',
      content: `Error: ${errorMessage}`,
      status: 'error'
    });

    callbacks.onError(error instanceof Error ? error : new Error(errorMessage));
  }
}
