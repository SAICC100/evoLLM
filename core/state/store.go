package state

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"

	_ "github.com/marcboeker/go-duckdb"
)

// Store 负责世界状态的持久化读写。
type Store struct {
	db *sql.DB
}

func New(dbPath string) (*Store, error) {
	if err := os.MkdirAll(filepath.Dir(dbPath), 0755); err != nil {
		return nil, err
	}
	db, err := sql.Open("duckdb", dbPath)
	if err != nil {
		return nil, fmt.Errorf("打开 DuckDB 失败: %w", err)
	}
	s := &Store{db: db}
	if err := s.initSchema(); err != nil {
		return nil, fmt.Errorf("初始化 schema 失败: %w", err)
	}
	return s, nil
}

func (s *Store) Close() error {
	return s.db.Close()
}

func (s *Store) initSchema() error {
	_, err := s.db.Exec(`
		CREATE TABLE IF NOT EXISTS ticks (
			tick      BIGINT PRIMARY KEY,
			state_json TEXT NOT NULL,
			created_at TIMESTAMP DEFAULT now()
		);
		CREATE SEQUENCE IF NOT EXISTS tick_seq START 1;
	`)
	return err
}

// NextTick 返回下一个 tick 编号。
func (s *Store) NextTick() int64 {
	var tick int64
	_ = s.db.QueryRow("SELECT nextval('tick_seq')").Scan(&tick)
	return tick
}

// LoadState 加载最新的世界状态，不存在时返回空状态。
func (s *Store) LoadState() (*WorldState, error) {
	var stateJSON string
	err := s.db.QueryRow(
		"SELECT state_json FROM ticks ORDER BY tick DESC LIMIT 1",
	).Scan(&stateJSON)
	if err == sql.ErrNoRows {
		return &WorldState{Data: map[string]any{}}, nil
	}
	if err != nil {
		return nil, err
	}
	var ws WorldState
	if err := json.Unmarshal([]byte(stateJSON), &ws); err != nil {
		return nil, err
	}
	return &ws, nil
}

// SaveState 持久化本轮状态快照。
func (s *Store) SaveState(tick int64, ws *WorldState) error {
	data, err := json.Marshal(ws)
	if err != nil {
		return err
	}
	_, err = s.db.Exec(
		"INSERT OR REPLACE INTO ticks (tick, state_json) VALUES (?, ?)",
		tick, string(data),
	)
	return err
}

// WorldState 是世界状态的内存表示。
type WorldState struct {
	Tick      int64          `json:"tick"`
	Timestamp time.Time      `json:"timestamp"`
	Data      map[string]any `json:"data"`
}

// ToContext 将世界状态转换为 Plugin 的 context 输入。
func (ws *WorldState) ToContext() map[string]any {
	return map[string]any{
		"tick": ws.Tick,
		"data": ws.Data,
	}
}

// Apply 将变更列表应用到状态，返回新状态（不修改原状态）。
func (ws *WorldState) Apply(changes []Change) *WorldState {
	newData := shallowCopy(ws.Data)
	for _, c := range changes {
		applyChange(newData, c)
	}
	return &WorldState{
		Tick:      ws.Tick,
		Timestamp: time.Now(),
		Data:      newData,
	}
}

// EvalCondition 对简单条件表达式求值（目前支持 json path 比较）。
func (ws *WorldState) EvalCondition(condition string) bool {
	// 简单实现：直接返回 true，复杂条件由 Plugin 自己判断
	// TODO: 实现基于 ws.Data 的条件求值
	return true
}

// Change 是 Plugin 返回的声明式变更。
type Change struct {
	Path  string `json:"path"`
	Op    string `json:"op"`    // set | add | append | remove
	Value any    `json:"value"`
}

func applyChange(data map[string]any, c Change) {
	// 简化实现：只处理顶层 key
	// TODO: 支持嵌套 path（如 "npc.health"）
	switch c.Op {
	case "set":
		data[c.Path] = c.Value
	case "add":
		if v, ok := data[c.Path]; ok {
			switch val := v.(type) {
			case float64:
				if delta, ok := c.Value.(float64); ok {
					data[c.Path] = val + delta
				}
			case int64:
				if delta, ok := c.Value.(float64); ok {
					data[c.Path] = val + int64(delta)
				}
			}
		}
	case "append":
		if list, ok := data[c.Path].([]any); ok {
			data[c.Path] = append(list, c.Value)
		} else {
			data[c.Path] = []any{c.Value}
		}
	case "remove":
		delete(data, c.Path)
	}
}

func shallowCopy(m map[string]any) map[string]any {
	out := make(map[string]any, len(m))
	for k, v := range m {
		out[k] = v
	}
	return out
}
