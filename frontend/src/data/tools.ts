import type { Tool } from '../types';

// Default built-in tools
export const defaultTools: Tool[] = [
  { name: 'web_search', icon: '🔍', description: 'Search the web with multi-engine routing', usageCount: 0, status: 'idle' },
  { name: 'read_file', icon: '📄', description: 'Read contents of a file', usageCount: 0, status: 'idle' },
  { name: 'write_file', icon: '✏️', description: 'Write content to a file', usageCount: 0, status: 'idle' },
  { name: 'exec', icon: '⚡', description: 'Execute a shell command', usageCount: 0, status: 'idle' },
  { name: 'search_memory', icon: '🧠', description: 'Semantic search over vector memory', usageCount: 0, status: 'idle' },
  { name: 'schedule', icon: '📅', description: 'Create a scheduled task (cron or one-shot)', usageCount: 0, status: 'idle' },
  { name: 'create_tool', icon: '🔧', description: 'Create a new runtime Python tool', usageCount: 0, status: 'idle' },
  { name: 'self_check', icon: '🩺', description: 'Run system diagnostics and health check', usageCount: 0, status: 'idle' },
  { name: 'send_message', icon: '💬', description: 'Send a notification message', usageCount: 0, status: 'idle' },
];

// Fetch tools - returns default built-in tools only
export async function fetchMcpServers(): Promise<Tool[]> {
  return defaultTools;
}
