/**
 * ============================================================================
 * useAgentRunner - Agent 執行引擎核心 Hook
 * ============================================================================
 *
 * 【系統定位】
 * 這是 7/24 Office 系統的「心臟」，負責協調 UI 層與數據層的交互。
 *
 * 【唯一職責】
 * 1. 管理執行狀態機 (idle → running → complete/aborted)
 * 2. 協調三層記憶架構的更新節奏
 * 3. 驅動工具面板的視覺反饋
 *
 * 【數據一致性策略】
 * - 使用 React State 作為單一數據源 (Single Source of Truth)
 * - 所有狀態更新均透過 setter 函數，確保不可變性 (Immutability)
 */

import { useState, useCallback, useRef, useEffect } from 'react';
import type { AgentStep, MemoryItem, Tool } from '../types';
import { fetchMcpServers } from '../data/tools';
import { runAgent } from '../services/llm';

// ============================================================================
// 主 Hook 實現
// ============================================================================

export function useAgentRunner() {
  // ---------------------------------------------------------------------------
  // 狀態定義
  // ---------------------------------------------------------------------------

  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [tools, setTools] = useState<Tool[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [currentGoal, setCurrentGoal] = useState('');
  const [goalTimestamp, setGoalTimestamp] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Load MCP servers on mount
  useEffect(() => {
    fetchMcpServers().then(mcpTools => {
      setTools(mcpTools);
    });
  }, []);

  /**
   * 中斷控制器 - 使用 AbortController 管理異步請求
   */
  const abortControllerRef = useRef<AbortController | null>(null);

  // ---------------------------------------------------------------------------
  // reset - 重置所有狀態到初始值
  // ---------------------------------------------------------------------------

  const reset = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }

    setSteps([]);
    setMemories([]);
    // Reset tools to initial state (reload MCP servers)
    fetchMcpServers().then(mcpTools => {
      setTools(mcpTools);
    });
    setIsRunning(false);
    setCurrentGoal('');
    setGoalTimestamp(null);
    setError(null);
  }, []);

  // ---------------------------------------------------------------------------
  // run - 執行 Agent 的核心邏輯
  // ---------------------------------------------------------------------------

  const run = useCallback(async (goal: string) => {
    // 取消之前的請求
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    // 創建新的 AbortController
    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    // 初始化 UI 狀態
    setCurrentGoal(goal);
    setGoalTimestamp(Date.now());
    setIsRunning(true);
    setSteps([]);
    // Reset tools to idle state
    setTools(prev => prev.map(t => ({ ...t, status: 'idle' as const })));
    setError(null);

    // Add session memory for the new goal
    setMemories(prev => [...prev, {
      layer: 'session',
      content: goal,
      timestamp: Date.now()
    }]);

    // 構建記憶上下文
    const memoryContext = memories.map(m => m.content).join('\n');

    try {
      await runAgent(
        goal,
        {
          onStep: (step) => {
            setSteps(prev => [...prev, step]);
          },
          onToolCall: (toolCall) => {
            console.log('[onToolCall]', toolCall.tool, toolCall.status);
            setTools(prev => prev.map(t =>
              t.name === toolCall.tool
                ? { ...t, status: toolCall.status === 'running' ? 'active' : 'idle', usageCount: t.usageCount + 1 }
                : t
            ));
          },
          onComplete: (data?: { memoryContext?: string }) => {
            setIsRunning(false);
            // Add memory item if context was retrieved
            if (data?.memoryContext) {
              setMemories(prev => [...prev, {
                layer: 'retrieved' as const,
                content: data.memoryContext!.slice(0, 200),
                timestamp: Date.now(),
                relevance: 0.95
              }]);
            }
          },
          onError: (err) => {
            setError(err.message);
            setIsRunning(false);
          },
        },
        memoryContext,
        signal
      );
    } catch (err) {
      if (signal.aborted) return;
      setError(err instanceof Error ? err.message : 'Unknown error');
      setIsRunning(false);
    }
  }, [memories]);

  // ---------------------------------------------------------------------------
  // 返回公開 API
  // ---------------------------------------------------------------------------

  return {
    steps,
    memories,
    tools,
    isRunning,
    currentGoal,
    goalTimestamp,
    error,
    run,
    reset,
  };
}
