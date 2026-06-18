package state

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	_ "github.com/marcboeker/go-duckdb"
)

// Store 负责世界状态的持久化读写。
type Store struct {
	db     *sql.DB
	dbPath string
}

func New(dbPath string) (*Store, error) {
	if err := os.MkdirAll(filepath.Dir(dbPath), 0755); err != nil {
		return nil, err
	}
	db, err := sql.Open("duckdb", dbPath)
	if err != nil {
		return nil, fmt.Errorf("打开 DuckDB 失败: %w", err)
	}
	s := &Store{db: db, dbPath: dbPath}
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
			id         INTEGER PRIMARY KEY DEFAULT 1,
			tick       BIGINT NOT NULL DEFAULT 0,
			state_json TEXT NOT NULL DEFAULT '{}',
			updated_at TIMESTAMP DEFAULT now()
		);
		CREATE SEQUENCE IF NOT EXISTS tick_seq START 1;
		INSERT INTO ticks (id, tick, state_json) VALUES (1, 0, '{}')
			ON CONFLICT (id) DO NOTHING;
	`)
	return err
}

// IsHealthy 检查 DB 是否可用。
func (s *Store) IsHealthy() bool {
	var n int
	err := s.db.QueryRow("SELECT 1").Scan(&n)
	return err == nil
}

// Reinit 重新初始化 DB 连接（DB 损坏时调用）。
func (s *Store) Reinit() error {
	_ = s.db.Close()
	db, err := sql.Open("duckdb", s.dbPath)
	if err != nil {
		return err
	}
	s.db = db
	return s.initSchema()
}

// NextTick 返回下一个 tick 编号。
func (s *Store) NextTick() int64 {
	var tick int64
	_ = s.db.QueryRow("SELECT nextval('tick_seq')").Scan(&tick)
	return tick
}

// LoadState 加载当前世界状态。
func (s *Store) LoadState() (*WorldState, error) {
	var stateJSON string
	err := s.db.QueryRow("SELECT state_json FROM ticks WHERE id = 1").Scan(&stateJSON)
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

// SaveState 覆盖写入当前世界状态（单行 upsert）。
// 地图数据体积巨大且很少变化，存储前从 state 中剥离，单独写文件。
func (s *Store) SaveState(tick int64, ws *WorldState) error {
	ws.Tick = tick

	// 剥离地图数据，避免每轮都写巨大的地图 JSON 到 DuckDB
	saveData := make(map[string]any, len(ws.Data))
	for k, v := range ws.Data {
		saveData[k] = v
	}
	if world, ok := saveData["world"].(map[string]any); ok {
		if _, hasMap := world["map"]; hasMap {
			// 地图单独写文件（仅在地图变化时写，用 tick=0 文件代表初始地图）
			mapPath := strings.TrimSuffix(s.dbPath, ".db") + ".map.json"
			if tick == 1 {
				if mapData, err := json.Marshal(world["map"]); err == nil {
					_ = os.WriteFile(mapPath, mapData, 0644)
				}
			}
			// 从 DB 存储中移除地图
			worldNoMap := make(map[string]any)
			for wk, wv := range world {
				if wk != "map" {
					worldNoMap[wk] = wv
				}
			}
			saveData["world"] = worldNoMap
		}
	}

	ws.Data = saveData
	data, err := json.Marshal(ws)
	if err != nil {
		return err
	}
	_, err = s.db.Exec(
		"UPDATE ticks SET tick = ?, state_json = ?, updated_at = now() WHERE id = 1",
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

// listIdxRe 匹配 "key[id=value]" 格式，用于在 list 中按 id 查找元素
var listIdxRe = regexp.MustCompile(`^(\w+)\[(\w+)=([^\]]+)\]$`)

func applyChange(data map[string]any, c Change) {
	parts := splitPath(c.Path)
	if len(parts) == 0 {
		return
	}

	// 逐层走到倒数第二层
	cur := data
	for i, p := range parts {
		isLast := i == len(parts)-1

		// 检查是否是 list 索引格式：listKey[idField=idValue].field
		if m := listIdxRe.FindStringSubmatch(p); m != nil {
			listKey, idField, idVal := m[1], m[2], m[3]
			list, ok := cur[listKey].([]any)
			if !ok {
				return
			}
			if isLast {
				// 替换整个元素
				for j, item := range list {
					if elem, ok := item.(map[string]any); ok {
						if fmt.Sprintf("%v", elem[idField]) == idVal {
							list[j] = c.Value
							cur[listKey] = list
							return
						}
					}
				}
				return
			}
			// 找到目标元素，继续往下走
			for _, item := range list {
				if elem, ok := item.(map[string]any); ok {
					if fmt.Sprintf("%v", elem[idField]) == idVal {
						if i == len(parts)-2 {
							applyAtKey(elem, parts[len(parts)-1], c.Op, c.Value)
							return
						}
						cur = elem
					}
				}
			}
			return
		}

		if isLast {
			applyAtKey(cur, p, c.Op, c.Value)
			return
		}

		// 普通嵌套 map
		if next, ok := cur[p]; ok {
			if nextMap, ok := next.(map[string]any); ok {
				cur = nextMap
			} else {
				newMap := map[string]any{}
				cur[p] = newMap
				cur = newMap
			}
		} else {
			newMap := map[string]any{}
			cur[p] = newMap
			cur = newMap
		}
	}
}

func applyAtKey(data map[string]any, key string, op string, value any) {
	switch op {
	case "set":
		data[key] = value
	case "add":
		if v, ok := data[key]; ok {
			switch val := v.(type) {
			case float64:
				if delta, ok := toFloat(value); ok {
					data[key] = val + delta
				}
			case int64:
				if delta, ok := toFloat(value); ok {
					data[key] = val + int64(delta)
				}
			default:
				_ = val
				data[key] = value
			}
		} else {
			data[key] = value
		}
	case "append":
		if list, ok := data[key].([]any); ok {
			data[key] = append(list, value)
		} else {
			data[key] = []any{value}
		}
	case "remove":
		delete(data, key)
	}
}

func splitPath(path string) []string {
	var parts []string
	for _, p := range strings.Split(path, ".") {
		if p != "" {
			parts = append(parts, p)
		}
	}
	return parts
}

func toFloat(v any) (float64, bool) {
	switch val := v.(type) {
	case float64:
		return val, true
	case int:
		return float64(val), true
	case int64:
		return float64(val), true
	}
	return 0, false
}

func shallowCopy(m map[string]any) map[string]any {
	out := make(map[string]any, len(m))
	for k, v := range m {
		out[k] = v
	}
	return out
}
