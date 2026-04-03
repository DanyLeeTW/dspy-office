/**
 * ============================================================================
 * useAgentRunner - Agent 執行引擎核心 Hook
 * ============================================================================
 *
 * 【系統定位】
 * 這是 7/24 Office 系統的「心臟」，負責協調 UI 層與數據層的交互。
 *
 * 【執行模式】
 * - **Real LLM Mode**: 當 `VITE_OPENAI_API_KEY` 已配置時，使用真實 LLM
 * - **Mock Mode**: 當 API Key 未配置時，使用預定義軌跡模擬執行
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

import { useState, useCallback, useRef } from 'react';
import type { AgentStep, MemoryItem, Tool } from '../types';
import { traces, genericTrace } from '../data/traces';
import { defaultTools } from '../data/tools';

// ============================================================================
// 私有工具函數 - Mock 模式使用
// ============================================================================

/**
 * matchTrace - 根據用戶目標匹配最相關的執行軌跡
 * 僅在 Mock 模式下使用
 */
function matchTrace(goal: string) {
  const lower = goal.toLowerCase();
  let best = genericTrace;
  let bestScore = 0;

  for (const trace of traces) {
    const score = trace.keywords.filter(kw => lower.includes(kw)).length;
    if (score > bestScore) {
      bestScore = score;
      best = trace;
    }
  }
  return best;
}

/**
 * deepCloneSteps - 深拷貝步驟數組
 * 僅在 Mock 模式下使用
 */
function deepCloneSteps(steps: AgentStep[]): AgentStep[] {
  return steps.map(s => ({
    ...s,
    toolCall: s.toolCall ? { ...s.toolCall } : undefined,
  }));
}

// ============================================================================
// 主 Hook 實現
// ============================================================================

export function useAgentRunner() {
  // ---------------------------------------------------------------------------
  // 狀態定義
  // ---------------------------------------------------------------------------

  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [tools, setTools] = useState<Tool[]>(defaultTools.map(t => ({ ...t })));
  const [isRunning, setIsRunning] = useState(false);
  const [currentGoal, setCurrentGoal] = useState('');
  const [error, setError] = useState<string | null>(null);

  /**
   * 中斷控制器 - 使用 AbortController 管理異步請求
   * 比 useRef 更可靠，能真正取消網絡請求
   */
  const abortControllerRef = useRef<AbortController | null>(null);

  // ---------------------------------------------------------------------------
  // reset - 重置所有狀態到初始值
  // ---------------------------------------------------------------------------

  const reset = useCallback(() => {
    // 取消任何進行中的請求
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }

    setSteps([]);
    setMemories([]);
    setTools(defaultTools.map(t => ({ ...t })));
    setIsRunning(false);
    setCurrentGoal('');
    setError(null);
  }, []);

  // ---------------------------------------------------------------------------
  // run - 執行 Agent 的核心邏輯
  // ---------------------------------------------------------------------------

  const run = useCallback((goal: string) => {
    // 取消之前的請求
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    // 創建新的 AbortController
    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    // 初始化 UI 狀態
    setCurrentGoal(goal);
    setIsRunning(true);
    setSteps([]);
    setMemories([]);
    setTools(defaultTools.map(t => ({ ...t })));
    setError(null);

    // ========================================
    // Mock Mode - 使用預定義軌跡
    // ========================================
    const trace = matchTrace(goal);
    const clonedSteps = deepCloneSteps(trace.steps);
    const traceMemories = trace.memories.map(m => ({ ...m }));

    let memoryIndex = 0;
    const memoryThresholds = [0, 0.3, 0.5, 0.7];
    const abortRef = { current: false };

    // 更新 abortRef 當 signal 觸發時
    signal.addEventListener('abort', () => {
      abortRef.current = true;
    });

    const processStep = (index: number) => {
      if (abortRef.current || index >= clonedSteps.length) {
        setIsRunning(false);
        return;
      }

      const step = clonedSteps[index];
      step.status = 'running';
      if (step.toolCall) step.toolCall.status = 'running';

      if (step.toolCall) {
        setTools(prev => prev.map(t =>
          t.name === step.toolCall!.tool ? { ...t, status: 'active' as const } : t
        ));
      }

      setSteps(clonedSteps.slice(0, index + 1).map(s => ({ ...s, toolCall: s.toolCall ? { ...s.toolCall } : undefined })));

      const progress = index / clonedSteps.length;
      while (memoryIndex < traceMemories.length &&
             memoryIndex < memoryThresholds.length &&
             progress >= memoryThresholds[memoryIndex]) {
        memoryIndex++;
      }

      if (memoryIndex <= traceMemories.length) {
        setMemories(traceMemories.slice(0, Math.max(1, memoryIndex)));
      }

      const delay = step.type === 'thinking' ? 1500
                  : step.type === 'tool_call' ? 1200
                  : step.type === 'decompose' ? 1000
                  : 600;

      setTimeout(() => {
        if (abortRef.current) return;

        step.status = 'complete';
        if (step.toolCall) step.toolCall.status = 'complete';

        if (step.toolCall) {
          setTools(prev => prev.map(t =>
            t.name === step.toolCall!.tool
              ? { ...t, status: 'idle' as const, usageCount: t.usageCount + 1 }
              : t
          ));
        }

        setSteps(clonedSteps.slice(0, index + 1).map(s => ({ ...s, toolCall: s.toolCall ? { ...s.toolCall } : undefined })));

        setTimeout(() => processStep(index + 1), 200);
      }, delay);
    };

    setTimeout(() => processStep(0), 500);
  }, []);

  // ---------------------------------------------------------------------------
  // 返回公開 API
  // ---------------------------------------------------------------------------

  return {
    steps,
    memories,
    tools,
    isRunning,
    currentGoal,
    error,
    run,
    reset,
  };
}
