package scheduler

import (
	"context"
	"log/slog"
	"time"
)

type TickFunc func(ctx context.Context)

// Scheduler 按固定间隔触发每轮循环。
// 上一轮未完成时，跳过本轮，不堆积。
type Scheduler struct {
	interval time.Duration
	tickFn   TickFunc
	logger   *slog.Logger
}

func New(interval time.Duration, fn TickFunc, logger *slog.Logger) *Scheduler {
	return &Scheduler{interval: interval, tickFn: fn, logger: logger}
}

func (s *Scheduler) Start(ctx context.Context) {
	ticker := time.NewTicker(s.interval)
	defer ticker.Stop()

	busy := make(chan struct{}, 1)

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			select {
			case busy <- struct{}{}:
				go func() {
					defer func() { <-busy }()
					s.tickFn(ctx)
				}()
			default:
				s.logger.Warn("上一轮还在执行，跳过本轮")
			}
		}
	}
}
