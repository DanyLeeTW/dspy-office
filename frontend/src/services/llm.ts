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
 * Run agent using Server-Sent Events for real-time updates
 */
export async function runAgent(
  goal: string,
  callbacks: AgentCallbacks,
  memoryContext?: string,
  signal?: AbortSignal
): Promise<void> {
  const baseUrl = getApiBaseUrl();

  try {
    console.log('[Sending Request]', { goal, memoryContext });

    // Use EventSource for SSE with POST (via fetch)
    const response = await fetch(`${baseUrl}/api/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
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

    const reader = response.body?.getReader();
    if (!reader) throw new Error('No response body');

    const decoder = new TextDecoder();
    let buffer = '';
    let memoryContextResult = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      let eventType = '';
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          eventType = line.slice(7);
        } else if (line.startsWith('data: ')) {
          const data = JSON.parse(line.slice(6));
          console.log('[SSE Event]', eventType, data);

          switch (eventType) {
            case 'thinking':
              callbacks.onStep({
                id: generateStepId('thinking'),
                type: 'thinking',
                content: data.content,
                status: 'running'
              });
              break;

            case 'tool_start':
              callbacks.onToolCall({
                tool: data.tool,
                args: data.args || {},
                status: 'running'
              });
              callbacks.onStep({
                id: generateStepId('tool_call'),
                type: 'tool_call',
                content: `Calling ${data.tool}...`,
                toolCall: {
                  tool: data.tool,
                  args: data.args || {},
                  status: 'running'
                },
                status: 'running'
              });
              break;

            case 'tool_end':
              callbacks.onToolCall({
                tool: data.tool,
                args: {},
                result: data.result,
                status: 'complete'
              });
              callbacks.onStep({
                id: generateStepId('tool_result'),
                type: 'tool_call',
                content: data.result || `Completed ${data.tool}`,
                toolCall: {
                  tool: data.tool,
                  args: {},
                  result: data.result,
                  status: 'complete'
                },
                status: 'complete'
              });
              break;

            case 'response':
              memoryContextResult = data.memory_context || '';
              callbacks.onStep({
                id: generateStepId('result'),
                type: 'result',
                content: data.content,
                status: 'complete'
              });
              break;

            case 'error':
              callbacks.onStep({
                id: generateStepId('error'),
                type: 'result',
                content: `Error: ${data.message}`,
                status: 'error'
              });
              callbacks.onError(new Error(data.message));
              break;

            case 'done':
              callbacks.onComplete({
                memoryContext: memoryContextResult
              });
              break;
          }
        }
      }
    }
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
