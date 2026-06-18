#!/usr/bin/env python3
"""npc_fertility_and_birth: NPC生育与新生儿出生系统

根据NPC年龄阶段、健康状态、配偶关系和部落资源水平计算生育概率，
触发怀孕事件并在孕期结束后生成新生儿。
"""

import sys
import json
import random
from typing import Dict, List, Any, Optional

def run(context: dict) -> dict:
    """处理NPC生育逻辑
    
    Args:
        context: 包含世界状态的上下文
        
    Returns:
        包含变更和日志的字典
    """
    data = context.get("data", {})
    npcs = data.get("npcs", [])
    tribes = data.get("tribes", [])
    world = data.get("world", {})
    
    changes: List[Dict[str, Any]] = []
    logs: List[str] = []
    
    try:
        # 获取当前季节
        current_season = world.get("current_season", "spring")
        
        # 计算部落资源水平
        tribe_resources = {}
        for tribe in tribes:
            if isinstance(tribe, dict):
                tribe_id = tribe.get("id", "")
                food = tribe.get("food", 0)
                population = tribe.get("population", 1)
                # 计算人均食物水平
                if population > 0:
                    food_per_capita = food / population
                    # 资源水平：0-1之间，1表示食物充足
                    resource_level = min(1.0, food_per_capita / 10.0)
                    tribe_resources[tribe_id] = resource_level
        
        # 处理怀孕NPC的孕期进展
        pregnant_npcs = []
        for npc in npcs:
            if not isinstance(npc, dict):
                continue
                
            npc_id = npc.get("id", "")
            pregnancy = npc.get("pregnancy", {})
            
            if pregnancy and isinstance(pregnancy, dict):
                days_left = pregnancy.get("days_left", 0)
                if days_left > 0:
                    # 孕期减少一天
                    new_days_left = days_left - 1
                    changes.append({
                        "path": f"npcs[id={npc_id}].pregnancy.days_left",
                        "op": "set",
                        "value": new_days_left
                    })
                    
                    if new_days_left <= 0:
                        # 孕期结束，准备分娩
                        pregnant_npcs.append((npc_id, npc, pregnancy))
                        logs.append(f"{npc.get('name', '?')} 孕期结束，准备分娩")
        
        # 处理分娩
        for npc_id, npc, pregnancy in pregnant_npcs:
            # 生成新生儿
            baby_id = f"npc_{random.randint(1000, 9999)}"
            spouse_id = pregnancy.get("spouse_id", "")
            tribe_id = npc.get("tribe_id", "")
            
            # 确定新生儿性别（50%概率）
            gender = "male" if random.random() < 0.5 else "female"
            
            # 新生儿属性
            baby = {
                "id": baby_id,
                "name": f"新生儿_{baby_id[-4:]}",
                "age": 0,
                "gender": gender,
                "health": 80 + random.randint(-5, 5),  # 初始健康
                "hunger": 30,
                "energy": 90,
                "tribe_id": tribe_id,
                "parent_ids": [npc_id, spouse_id] if spouse_id else [npc_id],
                "status": "child"
            }
            
            # 添加新生儿到世界
            changes.append({
                "path": "npcs",
                "op": "append",
                "value": baby
            })
            
            # 移除怀孕状态
            changes.append({
                "path": f"npcs[id={npc_id}].pregnancy",
                "op": "remove",
                "value": None
            })
            
            # 更新部落人口
            if tribe_id:
                changes.append({
                    "path": f"tribes[id={tribe_id}].population",
                    "op": "add",
                    "value": 1
                })
            
            mother_name = npc.get("name", "?")
            logs.append(f"{mother_name} 生下了新生儿 {baby['name']}")
        
        # 计算生育概率并触发新怀孕
        fertile_npcs = []
        for npc in npcs:
            if not isinstance(npc, dict):
                continue
                
            npc_id = npc.get("id", "")
            
            # 检查是否已怀孕
            if npc.get("pregnancy"):
                continue
                
            # 检查年龄阶段
            age = npc.get("age", 0)
            status = npc.get("status", "")
            
            # 只有青年和壮年可以生育
            if status not in ["young_adult", "adult"]:
                continue
                
            # 检查性别（假设只有女性可以怀孕）
            gender = npc.get("gender", "")
            if gender != "female":
                continue
                
            # 检查健康状态
            health = npc.get("health", 50)
            if health < 60:
                continue
                
            # 检查是否有配偶
            spouse_id = npc.get("spouse_id", "")
            if not spouse_id:
                continue
                
            # 找到配偶
            spouse = None
            for other_npc in npcs:
                if isinstance(other_npc, dict) and other_npc.get("id") == spouse_id:
                    spouse = other_npc
                    break
            
            if not spouse:
                continue
                
            # 检查配偶年龄和健康
            spouse_age = spouse.get("age", 0)
            spouse_health = spouse.get("health", 50)
            spouse_status = spouse.get("status", "")
            
            if spouse_status not in ["young_adult", "adult"]:
                continue
            if spouse_health < 60:
                continue
                
            # 检查部落资源水平
            tribe_id = npc.get("tribe_id", "")
            resource_level = tribe_resources.get(tribe_id, 0.5)
            
            if resource_level < 0.3:  # 资源匮乏时生育率降低
                continue
                
            fertile_npcs.append((npc_id, npc, spouse_id, tribe_id, health, resource_level))
        
        # 为符合条件的NPC计算生育概率
        for npc_id, npc, spouse_id, tribe_id, health, resource_level in fertile_npcs:
            # 基础生育概率
            base_probability = 0.02  # 每日2%基础概率
            
            # 健康影响（健康越高概率越高）
            health_factor = min(1.0, health / 100.0)
            
            # 资源影响（资源越充足概率越高）
            resource_factor = resource_level
            
            # 季节影响（春季生育率最高）
            season_factor = 1.0
            if current_season == "spring":
                season_factor = 1.5
            elif current_season == "winter":
                season_factor = 0.5
                
            # 计算最终概率
            final_probability = base_probability * health_factor * resource_factor * season_factor
            
            # 随机决定是否怀孕
            if random.random() < final_probability:
                # 设置怀孕状态
                pregnancy_duration = 280  # 模拟280天孕期
                pregnancy = {
                    "spouse_id": spouse_id,
                    "days_left": pregnancy_duration,
                    "start_day": world.get("current_day", 0)
                }
                
                changes.append({
                    "path": f"npcs[id={npc_id}].pregnancy",
                    "op": "set",
                    "value": pregnancy
                })
                
                mother_name = npc.get("name", "?")
                logs.append(f"{mother_name} 怀孕了！孕期开始")
                
                # 记录生育事件
                changes.append({
                    "path": "world.events",
                    "op": "append",
                    "value": {
                        "type": "pregnancy_started",
                        "npc_id": npc_id,
                        "spouse_id": spouse_id,
                        "day": world.get("current_day", 0)
                    }
                })
    
    except Exception as e:
        logs.append(f"生育系统错误: {str(e)}")
    
    return {"changes": changes, "logs": logs[:10]}  # 限制日志数量

if __name__ == "__main__":
    try:
        input_data = json.loads(sys.stdin.read())
        context = input_data.get("context", {})
        result = run(context)
        print(json.dumps(result))
    except Exception as e:
        error_result = {
            "changes": [],
            "logs": [f"插件执行错误: {str(e)}"]
        }
        print(json.dumps(error_result))