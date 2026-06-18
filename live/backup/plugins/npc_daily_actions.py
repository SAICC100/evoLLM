import json
import sys
from typing import Dict, List, Any

# 常量定义
ACTIONS = ["hunting", "farming", "patrol", "trade", "rest"]
OCCUPATION_ACTION_WEIGHTS = {
    "warrior": {"hunting": 0.4, "patrol": 0.4, "rest": 0.2},
    "farmer": {"farming": 0.6, "hunting": 0.2, "rest": 0.2},
    "merchant": {"trade": 0.6, "patrol": 0.2, "rest": 0.2},
    "elder": {"rest": 0.5, "trade": 0.3, "patrol": 0.2},
    "craftsman": {"trade": 0.5, "farming": 0.3, "rest": 0.2}
}
HEALTH_ACTION_WEIGHTS = {
    "healthy": {"hunting": 0.3, "farming": 0.3, "patrol": 0.2, "trade": 0.1, "rest": 0.1},
    "injured": {"rest": 0.6, "trade": 0.2, "farming": 0.1, "patrol": 0.1, "hunting": 0.0},
    "sick": {"rest": 0.8, "trade": 0.1, "farming": 0.1, "patrol": 0.0, "hunting": 0.0}
}
SEASON_MODIFIERS = {
    "spring": {"farming": 1.3, "hunting": 1.1, "patrol": 1.0, "trade": 1.0, "rest": 0.9},
    "summer": {"farming": 1.2, "hunting": 1.0, "patrol": 0.9, "trade": 1.1, "rest": 0.9},
    "autumn": {"farming": 1.1, "hunting": 1.3, "patrol": 1.0, "trade": 1.2, "rest": 0.9},
    "winter": {"farming": 0.5, "hunting": 0.8, "patrol": 0.7, "trade": 0.9, "rest": 1.3}
}
TRIBE_NAMES = {
    "1": "铁爪",
    "2": "银月", 
    "3": "石心"
}
ACTION_RESULTS = {
    "hunting": {"energy_delta": -20, "gold_delta": 15, "success_rate": 0.7},
    "farming": {"energy_delta": -15, "gold_delta": 10, "success_rate": 0.8},
    "patrol": {"energy_delta": -25, "gold_delta": 5, "success_rate": 0.9},
    "trade": {"energy_delta": -10, "gold_delta": 20, "success_rate": 0.6},
    "rest": {"energy_delta": 30, "gold_delta": -5, "success_rate": 1.0}
}

def select_action(occupation: str, health: str, season: str) -> str:
    """根据职业、健康状态和季节选择行动"""
    try:
        # 基础权重
        base_weights = {action: 0.0 for action in ACTIONS}
        
        # 职业权重
        if occupation in OCCUPATION_ACTION_WEIGHTS:
            for action, weight in OCCUPATION_ACTION_WEIGHTS[occupation].items():
                base_weights[action] += weight * 0.6
        
        # 健康状态权重
        if health in HEALTH_ACTION_WEIGHTS:
            for action, weight in HEALTH_ACTION_WEIGHTS[health].items():
                base_weights[action] += weight * 0.4
        
        # 季节调整
        if season in SEASON_MODIFIERS:
            for action, modifier in SEASON_MODIFIERS[season].items():
                if action in base_weights:
                    base_weights[action] *= modifier
        
        # 归一化
        total = sum(base_weights.values())
        if total > 0:
            normalized = {k: v/total for k, v in base_weights.items()}
        else:
            normalized = {action: 1.0/len(ACTIONS) for action in ACTIONS}
        
        # 根据权重随机选择（这里使用确定性选择：选择权重最高的）
        selected = max(normalized.items(), key=lambda x: x[1])[0]
        return selected
        
    except Exception as e:
        return "rest"  # 默认休息

def process_npc_action(npc: Dict[str, Any], season: str, tribe_name: str) -> Dict[str, Any]:
    """处理单个NPC的行动"""
    try:
        # 选择行动
        action = select_action(npc.get("occupation", "farmer"), 
                              npc.get("health", "healthy"), 
                              season)
        
        # 获取行动结果
        action_info = ACTION_RESULTS.get(action, ACTION_RESULTS["rest"])
        
        # 计算实际结果（考虑成功率）
        import random
        success = random.random() < action_info["success_rate"]
        
        # 计算能量和金钱变化
        energy_delta = action_info["energy_delta"]
        gold_delta = action_info["gold_delta"] if success else gold_delta // 2
        
        # 确保能量不会超过上限或低于0
        new_energy = max(0, min(100, npc.get("energy", 50) + energy_delta))
        actual_energy_delta = new_energy - npc.get("energy", 50)
        
        # 确保金钱不会低于0
        new_gold = max(0, npc.get("gold", 0) + gold_delta)
        actual_gold_delta = new_gold - npc.get("gold", 0)
        
        # 生成事件描述
        success_text = "成功" if success else "失败"
        action_descriptions = {
            "hunting": f"{tribe_name}部落的{npc.get('name')}外出狩猎，{success_text}获得了一些猎物",
            "farming": f"{tribe_name}部落的{npc.get('name')}在田间劳作，{success_text}收获了一些作物",
            "patrol": f"{tribe_name}部落的{npc.get('name')}执行巡逻任务，{success_text}维护了部落安全",
            "trade": f"{tribe_name}部落的{npc.get('name')}进行贸易活动，{success_text}获得了一些利润",
            "rest": f"{tribe_name}部落的{npc.get('name')}在休息恢复体力"
        }
        
        event_desc = action_descriptions.get(action, f"{npc.get('name')}进行了{action}活动")
        
        return {
            "npc_id": npc.get("id"),
            "action": action,
            "energy_delta": actual_energy_delta,
            "gold_delta": actual_gold_delta,
            "event_description": event_desc,
            "success": success
        }
        
    except Exception as e:
        # 出错时返回安全的默认值
        return {
            "npc_id": npc.get("id"),
            "action": "rest",
            "energy_delta": 10,
            "gold_delta": 0,
            "event_description": f"{npc.get('name', 'NPC')}在休息中",
            "success": True
        }

def run(context: dict) -> dict:
    """主函数：处理所有NPC的每日行动"""
    changes = []
    logs = []
    
    try:
        # 从context中获取数据
        npcs = context.get("data", {}).get("npcs", [])
        season = context.get("data", {}).get("world", {}).get("season", "spring")
        tribes = context.get("data", {}).get("tribes", [])
        
        logs.append(f"开始处理 {len(npcs)} 个NPC的每日行动，当前季节：{season}")
        
        # 创建部落ID到名称的映射
        tribe_map = {}
        for tribe in tribes:
            tribe_map[str(tribe.get("id"))] = tribe.get("name", "未知部落")
        
        # 处理每个NPC
        for npc in npcs:
            try:
                tribe_id = str(npc.get("tribe_id", "1"))
                tribe_name = tribe_map.get(tribe_id, TRIBE_NAMES.get(tribe_id, "铁爪"))
                
                result = process_npc_action(npc, season, tribe_name)
                
                # 添加能量变化
                changes.append({
                    "path": f"npcs.{npc.get('id')}.energy",
                    "op": "add",
                    "value": result["energy_delta"]
                })
                
                # 添加金钱变化
                changes.append({
                    "path": f"npcs.{npc.get('id')}.gold",
                    "op": "add",
                    "value": result["gold_delta"]
                })
                
                # 添加事件记录
                changes.append({
                    "path": "world.events",
                    "op": "append",
                    "value": {
                        "type": "npc_action",
                        "description": result["event_description"],
                        "npc_id": result["npc_id"],
                        "action": result["action"],
                        "season": season,
                        "timestamp": "daily"
                    }
                })
                
                logs.append(f"NPC {npc.get('name')} 执行 {result['action']}，能量变化：{result['energy_delta']}，金钱变化：{result['gold_delta']}")
                
            except Exception as e:
                logs.append(f"处理NPC {npc.get('id', '未知')} 时出错：{str(e)}")
                continue
        
        logs.append(f"处理完成，生成 {len(changes)//3} 个NPC的行动记录")
        
    except Exception as e:
        logs.append(f"主处理过程出错：{str(e)}")
    
    return {"changes": changes, "logs": logs}

if __name__ == "__main__":
    try:
        # 从标准输入读取JSON
        input_data = json.loads(sys.stdin.read())
        
        # 执行主函数
        result = run(input_data)
        
        # 输出结果到标准输出
        print(json.dumps(result, ensure_ascii=False))
        
    except Exception as e:
        # 如果连输入输出都出错，返回基本错误信息
        error_result = {
            "changes": [],
            "logs": [f"系统错误：{str(e)}"]
        }
        print(json.dumps(error_result, ensure_ascii=False))