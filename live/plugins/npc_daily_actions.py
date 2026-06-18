#!/usr/bin/env python3
"""npc_daily_actions: NPC每日行动，包含社交互动和状态影响"""
import json
import sys
import random
from typing import Dict, List, Any

# 常量定义
ACTIONS = ["hunting", "farming", "patrol", "trade", "rest"]
SOCIAL_ACTIONS = ["conversation", "cooperation", "argument", "gift_exchange", "shared_meal"]
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
SOCIAL_SEASON_MODIFIERS = {
    "spring": 1.2,  # 春天社交更活跃
    "summer": 1.1,
    "autumn": 1.0,
    "winter": 0.8   # 冬天社交减少
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
SOCIAL_EFFECTS = {
    "conversation": {"mood_delta": 1, "social_energy_delta": 2, "description": "进行了愉快的交谈"},
    "cooperation": {"mood_delta": 2, "social_energy_delta": 3, "description": "合作完成了某项工作"},
    "argument": {"mood_delta": -1, "social_energy_delta": -1, "description": "发生了一些小争执"},
    "gift_exchange": {"mood_delta": 3, "social_energy_delta": 4, "description": "交换了小礼物"},
    "shared_meal": {"mood_delta": 2, "social_energy_delta": 3, "description": "共享了食物和故事"}
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
            for action in base_weights:
                if base_weights[action] > 0 and action in SEASON_MODIFIERS[season]:
                    base_weights[action] *= SEASON_MODIFIERS[season][action]
        
        # 归一化并选择
        total = sum(base_weights.values())
        if total <= 0:
            return "rest"
        
        rand_val = random.random() * total
        cumulative = 0
        for action, weight in base_weights.items():
            cumulative += weight
            if rand_val <= cumulative:
                return action
        
        return "rest"
    except Exception:
        return "rest"

def select_social_action(season: str) -> str:
    """根据季节选择社交互动类型"""
    try:
        weights = {
            "conversation": 0.3,
            "cooperation": 0.25,
            "argument": 0.1,
            "gift_exchange": 0.2,
            "shared_meal": 0.15
        }
        
        # 季节调整
        season_mod = SOCIAL_SEASON_MODIFIERS.get(season, 1.0)
        if season == "winter":
            weights["shared_meal"] *= 1.5  # 冬天更多共享食物
        elif season == "spring":
            weights["conversation"] *= 1.3  # 春天更多交谈
        
        # 归一化
        total = sum(weights.values())
        rand_val = random.random() * total
        cumulative = 0
        for action, weight in weights.items():
            cumulative += weight
            if rand_val <= cumulative:
                return action
        
        return "conversation"
    except Exception:
        return "conversation"

def find_social_partner(npc_id: str, npc_tribe: str, npcs: List[Dict[str, Any]]) -> str:
    """为NPC寻找社交伙伴"""
    try:
        # 优先同部落的NPC
        same_tribe_npcs = [n for n in npcs if n.get("tribe") == npc_tribe and n.get("id") != npc_id]
        
        if same_tribe_npcs:
            # 有一定概率选择不同部落的NPC（促进部落间交流）
            if random.random() < 0.2 and len(npcs) > len(same_tribe_npcs) + 1:
                other_tribe_npcs = [n for n in npcs if n.get("tribe") != npc_tribe and n.get("id") != npc_id]
                if other_tribe_npcs:
                    return random.choice(other_tribe_npcs)["id"]
            
            return random.choice(same_tribe_npcs)["id"]
        
        # 如果没有同部落的，选择任意其他NPC
        other_npcs = [n for n in npcs if n.get("id") != npc_id]
        if other_npcs:
            return random.choice(other_npcs)["id"]
        
        return ""
    except Exception:
        return ""

def calculate_population_vitality(npcs: List[Dict[str, Any]]) -> int:
    """计算人口活力值"""
    try:
        vitality = 0
        
        for npc in npcs:
            if not isinstance(npc, dict):
                continue
            
            # 心情贡献
            mood = npc.get("mood", 50)
            if mood > 60:
                vitality += 1
            elif mood > 70:
                vitality += 2
            elif mood > 80:
                vitality += 3
            
            # 社交能量贡献
            social_energy = npc.get("social_energy", 0)
            if social_energy > 5:
                vitality += 1
            if social_energy > 10:
                vitality += 1
            
            # 年龄多样性贡献（年轻和年长者都有）
            age = npc.get("age", 30)
            if 18 <= age <= 30 or age >= 60:
                vitality += 1
        
        return vitality
    except Exception:
        return 0

def run(context: dict) -> dict:
    """执行NPC每日行动，包含社交互动"""
    try:
        data = context.get("data", {})
        npcs = data.get("npcs", [])
        tribes = data.get("tribes", [])
        world = data.get("world", {})
        
        season = world.get("current_season", "spring")
        changes = []
        logs = []
        
        # 确保每个NPC都有社交状态
        for npc in npcs:
            if not isinstance(npc, dict):
                continue
            
            npc_id = npc.get("id", "")
            if not npc_id:
                continue
            
            # 初始化社交状态（如果不存在）
            if "mood" not in npc:
                changes.append({
                    "path": f"npcs[id={npc_id}].mood",
                    "op": "set",
                    "value": 50
                })
            
            if "social_energy" not in npc:
                changes.append({
                    "path": f"npcs[id={npc_id}].social_energy",
                    "op": "set",
                    "value": 0
                })
        
        # 处理每个NPC的日常行动
        for npc in npcs:
            if not isinstance(npc, dict):
                continue
            
            npc_id = npc.get("id", "")
            name = npc.get("name", "无名者")
            occupation = npc.get("occupation", "farmer")
            health_status = npc.get("health_status", "healthy")
            tribe_id = npc.get("tribe", "1")
            tribe_name = TRIBE_NAMES.get(tribe_id, f"部落{tribe_id}")
            
            if not npc_id:
                continue
            
            # 1. 选择主要行动
            main_action = select_action(occupation, health_status, season)
            action_result = ACTION_RESULTS.get(main_action, ACTION_RESULTS["rest"])
            
            # 2. 执行主要行动
            success = random.random() < action_result["success_rate"]
            
            if success:
                energy_delta = action_result["energy_delta"]
                gold_delta = action_result["gold_delta"]
                
                changes.append({
                    "path": f"npcs[id={npc_id}].energy",
                    "op": "add",
                    "value": energy_delta
                })
                
                changes.append({
                    "path": f"npcs[id={npc_id}].gold",
                    "op": "add",
                    "value": gold_delta
                })
                
                # 3. 社交互动（每天都有社交机会）
                social_action = select_social_action(season)
                partner_id = find_social_partner(npc_id, tribe_id, npcs)
                
                if partner_id:
                    # 找到社交效果
                    social_effect = SOCIAL_EFFECTS.get(social_action, SOCIAL_EFFECTS["conversation"])
                    
                    # 应用社交效果给发起者
                    changes.append({
                        "path": f"npcs[id={npc_id}].mood",
                        "op": "add",
                        "value": social_effect["mood_delta"]
                    })
                    
                    changes.append({
                        "path": f"npcs[id={npc_id}].social_energy",
                        "op": "add",
                        "value": social_effect["social_energy_delta"]
                    })
                    
                    # 应用社交效果给参与者（效果减半）
                    changes.append({
                        "path": f"npcs[id={partner_id}].mood",
                        "op": "add",
                        "value": social_effect["mood_delta"] // 2 if social_effect["mood_delta"] != 0 else 0
                    })
                    
                    changes.append({
                        "path": f"npcs[id={partner_id}].social_energy",
                        "op": "add",
                        "value": social_effect["social_energy_delta"] // 2
                    })
                    
                    # 记录社交日志
                    partner_npc = next((n for n in npcs if n.get("id") == partner_id), {})
                    partner_name = partner_npc.get("name", "某人")
                    partner_tribe_id = partner_npc.get("tribe", "1")
                    partner_tribe_name = TRIBE_NAMES.get(partner_tribe_id, f"部落{partner_tribe_id}")
                    
                    social_log = f"{name}({tribe_name})与{partner_name}({partner_tribe_name})"
                    social_log += f"{social_effect['description']}"
                    
                    if social_effect["mood_delta"] > 0:
                        social_log += f"，心情+{social_effect['mood_delta']}"
                    elif social_effect["mood_delta"] < 0:
                        social_log += f"，心情{social_effect['mood_delta']}"
                    
                    logs.append(social_log)
                
                # 记录主要行动日志
                action_log = f"{name}({tribe_name})进行{main_action}"
                if gold_delta > 0:
                    action_log += f"，获得{gold_delta}金币"
                elif gold_delta < 0:
                    action_log += f"，花费{-gold_delta}金币"
                
                if energy_delta > 0:
                    action_log += f"，恢复{energy_delta}精力"
                elif energy_delta < 0:
                    action_log += f"，消耗{-energy_delta}精力"
                
                logs.append(action_log)
            else:
                # 行动失败
                logs.append(f"{name}({tribe_name})进行{main_action}失败")
        
        # 4. 更新人口活力值
        current_vitality = calculate_population_vitality(npcs)
        changes.append({
            "path": "world.population_vitality",
            "op": "set",
            "value": current_vitality
        })
        
        # 5. 添加活力变化日志
        logs.append(f"人口活力值更新为: {current_vitality}")
        
        # 限制日志数量
        if len(logs) > 10:
            logs = logs[:10]
        
        return {"changes": changes, "logs": logs}
    
    except Exception as e:
        # 捕获所有异常，避免插件崩溃
        error_msg = f"npc_daily_actions插件错误: {str(e)}"
        return {"changes": [], "logs": [error_msg]}

if __name__ == "__main__":
    try:
        input_data = json.loads(sys.stdin.read())
        context = input_data.get("context", {})
        result = run(context)
        print(json.dumps(result))
    except Exception as e:
        error_result = {"changes": [], "logs": [f"插件执行错误: {str(e)}"]}
        print(json.dumps(error_result))