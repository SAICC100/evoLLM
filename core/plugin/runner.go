package plugin

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"os/exec"
	"path/filepath"
	"time"

	"github.com/evo-core/core/pipeline"
	"github.com/evo-core/core/state"
)

const defaultTimeoutMs = 5000

// Runner 负责通过 subprocess 执行 Plugin。
// 每个 Plugin 在独立进程中运行，崩溃不影响 Core。
type Runner struct {
	liveDir string
	logger  *slog.Logger
}

func NewRunner(liveDir string, logger *slog.Logger) *Runner {
	return &Runner{liveDir: liveDir, logger: logger}
}

// ExecutePipeline 按 Pipeline 定义顺序执行各步骤，返回所有变更的合并列表。
func (r *Runner) ExecutePipeline(ctx context.Context, pl *pipeline.Pipeline, ws *state.WorldState) ([]state.Change, error) {
	var allChanges []state.Change

	// 按依赖顺序执行步骤（简化版：顺序执行，after 字段暂作文档用）
	for _, step := range pl.Steps {
		if step.Condition != "" && !ws.EvalCondition(step.Condition) {
			r.logger.Debug("跳过步骤（条件不满足）", "step", step.Plugin, "condition", step.Condition)
			continue
		}

		changes, err := r.runPlugin(ctx, step, ws)
		if err != nil {
			r.logger.Error("Plugin 执行失败", "plugin", step.Plugin, "error", err)
			if step.OnError == "stop" {
				return allChanges, fmt.Errorf("pipeline stopped at plugin %s: %w", step.Plugin, err)
			}
			continue
		}

		allChanges = append(allChanges, changes...)
		// 每步执行后更新状态，让后续步骤能看到最新状态
		ws = ws.Apply(changes)
	}

	return allChanges, nil
}

func (r *Runner) runPlugin(ctx context.Context, step pipeline.Step, ws *state.WorldState) ([]state.Change, error) {
	pluginPath := filepath.Join(r.liveDir, "plugins", step.Plugin+".py")
	if _, err := os.Stat(pluginPath); os.IsNotExist(err) {
		return nil, fmt.Errorf("plugin 文件不存在: %s", pluginPath)
	}

	// 构建输入
	timeoutMs := step.TimeoutMs
	if timeoutMs == 0 {
		timeoutMs = defaultTimeoutMs
	}
	input := map[string]any{
		"context":    ws.ToContext(),
		"timeout_ms": timeoutMs,
	}
	inputJSON, err := json.Marshal(input)
	if err != nil {
		return nil, fmt.Errorf("序列化 context 失败: %w", err)
	}

	// 执行 Plugin 进程
	timeout := time.Duration(timeoutMs) * time.Millisecond
	execCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	cmd := exec.CommandContext(execCtx, "python3", pluginPath)
	cmd.Stdin = bytes.NewReader(inputJSON)

	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	start := time.Now()
	if err := cmd.Run(); err != nil {
		r.logger.Warn("Plugin 退出异常",
			"plugin", step.Plugin,
			"stderr", stderr.String()[:min(len(stderr.String()), 200)],
			"elapsed", time.Since(start),
		)
		// Plugin 出错不阻断流程，返回空变更
		return nil, nil
	}

	// 解析输出
	var result struct {
		Changes []state.Change `json:"changes"`
		Logs    []string       `json:"logs"`
	}
	if err := json.Unmarshal(stdout.Bytes(), &result); err != nil {
		return nil, fmt.Errorf("解析 plugin 输出失败: %w", err)
	}

	if stderr.Len() > 0 {
		r.logger.Info("Plugin stderr", "plugin", step.Plugin, "stderr", stderr.String()[:min(stderr.Len(), 500)])
	}
	for _, log := range result.Logs {
		r.logger.Info("plugin log", "plugin", step.Plugin, "msg", log)
	}

	r.logger.Info("Plugin 执行完成",
		"plugin", step.Plugin,
		"changes", len(result.Changes),
		"elapsed", time.Since(start),
	)

	return result.Changes, nil
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
