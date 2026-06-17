package main

import (
	"context"
	"flag"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/evo-core/core/pipeline"
	"github.com/evo-core/core/plugin"
	"github.com/evo-core/core/scheduler"
	"github.com/evo-core/core/state"
	"github.com/evo-core/core/trigger"
)

func main() {
	liveDir := flag.String("live", "../live", "live 目录路径")
	workspaceDir := flag.String("workspace", "../workspace", "workspace 目录路径")
	dbPath := flag.String("db", "../data/state.db", "DuckDB 数据库路径")
	tickInterval := flag.Duration("tick", 5*time.Second, "每轮循环间隔")
	flag.Parse()

	logger := slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{
		Level: slog.LevelInfo,
	}))
	slog.SetDefault(logger)

	// 初始化各组件
	store, err := state.New(*dbPath)
	if err != nil {
		slog.Error("StateStore 初始化失败", "error", err)
		os.Exit(1)
	}
	defer store.Close()

	pluginRunner := plugin.NewRunner(*liveDir, logger)
	pipelineLoader := pipeline.NewLoader(*liveDir, logger)
	evoTrigger := trigger.New(*workspaceDir, logger)

	// 内核主循环
	kernel := &Kernel{
		store:    store,
		runner:   pluginRunner,
		loader:   pipelineLoader,
		trigger:  evoTrigger,
		liveDir:  *liveDir,
		logger:   logger,
	}

	sched := scheduler.New(*tickInterval, kernel.RunOneTick, logger)

	// 优雅退出
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	slog.Info("evo-core 启动", "live", *liveDir, "tick", *tickInterval)

	go sched.Start(ctx)

	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit

	slog.Info("正在关闭...")
	cancel()
	time.Sleep(500 * time.Millisecond)
}

// Kernel 是执行内核，负责每轮循环的调度。
// 它不知道业务逻辑，只知道：加载 Pipeline、执行 Plugin、保存状态、通知进化层。
type Kernel struct {
	store   *state.Store
	runner  *plugin.Runner
	loader  *pipeline.Loader
	trigger *trigger.Trigger
	liveDir string
	logger  *slog.Logger
}

func (k *Kernel) RunOneTick(ctx context.Context) {
	tick := k.store.NextTick()
	slog.Info("开始执行", "tick", tick)

	// 加载当前世界状态
	worldState, err := k.store.LoadState()
	if err != nil {
		slog.Error("加载状态失败", "tick", tick, "error", err)
		return
	}

	// 加载并执行所有 Pipeline
	pipelines, err := k.loader.LoadAll()
	if err != nil {
		slog.Error("加载 Pipeline 失败", "tick", tick, "error", err)
		return
	}

	for _, pl := range pipelines {
		if !pl.ShouldRun(tick) {
			continue
		}
		changes, err := k.runner.ExecutePipeline(ctx, pl, worldState)
		if err != nil {
			slog.Error("Pipeline 执行失败", "pipeline", pl.Name, "error", err)
			continue
		}
		worldState = worldState.Apply(changes)
	}

	// 保存状态
	if err := k.store.SaveState(tick, worldState); err != nil {
		slog.Error("保存状态失败", "tick", tick, "error", err)
		return
	}

	// 通知进化层（写快照到 workspace/observations/）
	k.trigger.Notify(tick, worldState)

	slog.Info("执行完成", "tick", tick)
}
