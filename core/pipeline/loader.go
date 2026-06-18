package pipeline

import (
	"log/slog"
	"os"
	"path/filepath"
	"sort"

	"gopkg.in/yaml.v3"
)

// Pipeline 定义 Plugin 的执行顺序和组合关系。
type Pipeline struct {
	Name        string  `yaml:"name"`
	Description string  `yaml:"description"`
	Version     string  `yaml:"version"`
	Trigger     Trigger `yaml:"trigger"`
	Steps       []Step  `yaml:"steps"`
}

type Trigger struct {
	Every int `yaml:"every"` // 每 N 轮触发一次，0 表示每轮都触发
}

type Step struct {
	Plugin      string     `yaml:"plugin"`
	Description string     `yaml:"description"`
	After       StringList `yaml:"after"`
	Condition   string     `yaml:"condition"`
	TimeoutMs   int        `yaml:"timeout_ms"`
	OnError     string     `yaml:"on_error"` // skip（默认）| stop
}

// StringList 同时接受 YAML 字符串和字符串列表。
type StringList []string

func (s *StringList) UnmarshalYAML(value *yaml.Node) error {
	// 单个字符串
	if value.Kind == yaml.ScalarNode {
		*s = StringList{value.Value}
		return nil
	}
	// 字符串列表
	var list []string
	if err := value.Decode(&list); err != nil {
		return err
	}
	*s = list
	return nil
}

// ShouldRun 判断本轮是否应该执行这个 Pipeline。
func (p *Pipeline) ShouldRun(tick int64) bool {
	if p.Trigger.Every <= 1 {
		return true
	}
	return tick%int64(p.Trigger.Every) == 0
}

// Loader 每次从磁盘加载 Pipeline，不缓存，支持热更新。
type Loader struct {
	pipelinesDir string
	logger       *slog.Logger
}

func NewLoader(liveDir string, logger *slog.Logger) *Loader {
	return &Loader{
		pipelinesDir: filepath.Join(liveDir, "pipelines"),
		logger:       logger,
	}
}

// LoadAll 加载 pipelines/ 目录下所有 .yaml 文件，按文件名排序。
func (l *Loader) LoadAll() ([]*Pipeline, error) {
	entries, err := os.ReadDir(l.pipelinesDir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil, nil
		}
		return nil, err
	}

	var pipelines []*Pipeline
	var files []string
	for _, e := range entries {
		if !e.IsDir() && (filepath.Ext(e.Name()) == ".yaml" || filepath.Ext(e.Name()) == ".yml") {
			files = append(files, e.Name())
		}
	}
	sort.Strings(files) // 按文件名字母序执行

	for _, f := range files {
		pl, err := l.loadOne(filepath.Join(l.pipelinesDir, f))
		if err != nil {
			l.logger.Error("加载 Pipeline 失败", "file", f, "error", err)
			continue
		}
		pipelines = append(pipelines, pl)
	}

	return pipelines, nil
}

func (l *Loader) loadOne(path string) (*Pipeline, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var pl Pipeline
	if err := yaml.Unmarshal(data, &pl); err != nil {
		return nil, err
	}
	if pl.Name == "" {
		pl.Name = filepath.Base(path)
	}
	return &pl, nil
}
