package trigger

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"time"

	"github.com/evo-core/core/state"
)

// Trigger 在每轮循环结束后写快照到 workspace/observations/，通知进化层。
type Trigger struct {
	observationsDir string
	logger          *slog.Logger
}

func New(workspaceDir string, logger *slog.Logger) *Trigger {
	return &Trigger{
		observationsDir: filepath.Join(workspaceDir, "observations"),
		logger:          logger,
	}
}

// Notify 写本轮快照，进化层的 Observer 会监听这个目录。
func (t *Trigger) Notify(tick int64, ws *state.WorldState) {
	if err := os.MkdirAll(t.observationsDir, 0755); err != nil {
		t.logger.Error("创建 observations 目录失败", "error", err)
		return
	}

	snapshot := map[string]any{
		"tick":      tick,
		"timestamp": time.Now().Format(time.RFC3339),
		"state":     ws.ToContext(),
	}

	data, err := json.MarshalIndent(snapshot, "", "  ")
	if err != nil {
		t.logger.Error("序列化快照失败", "error", err)
		return
	}

	filename := fmt.Sprintf("tick_%06d.json", tick)
	path := filepath.Join(t.observationsDir, filename)
	if err := os.WriteFile(path, data, 0644); err != nil {
		t.logger.Error("写快照失败", "path", path, "error", err)
		return
	}

	t.logger.Debug("快照已写入", "path", path)
}
