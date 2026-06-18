#!/usr/bin/env python3
"""npc_social_interaction: 每日随机选取NPC进行社交互动，提升活动度"""
import sys
import json
import random

def run(context: dict) -> dict:
    """
    每日随机选取一定比例的NPC进行社交互动
    互动类型包括：交谈、合作劳动、争吵
    基于NPC关系值和情绪状态决定互动类型和结果
    """
    try:
        data = context.get("data", {})
        npcs = data.get("npcs", [])
        world = data.get("world", {})
        
        changes = []
        logs = []
        
        # 过滤有效的NPC（有id且不是死亡状态）
        valid_npcs = []
        for npc in npcs:
            if not isinstance(npc, dict):
                continue
            npc_id = npc.get("id", "")
            if not npc_id:
                continue
            # 检查是否死亡或无法活动
            health = npc.get("health", 100)
            if health <= 0:
                continue
            valid_npcs.append(npc)
        
        if len(valid_npcs) < 2:
            logs.append("可用NPC数量不足，无法进行社交互动")
            return {"changes": changes, "logs": logs}
        
        # 计算每日参与互动的NPC比例（20%-40%）
        participation_rate = random.uniform(0.2, 0.4)
        num_to_select = max(2, int(len(valid_npcs) * participation_rate))
        
        # 随机选择参与互动的NPC
        selected_npcs = random.sample(valid_npcs, min(num_to_select, len(valid_npcs)))
        
        # 为每个选中的NPC寻找互动对象
        for npc in selected_npcs:
            npc_id = npc.get("id", "")
            npc_name = npc.get("name", f"NPC_{npc_id}")
            
            # 排除自己后寻找其他NPC作为互动对象
            other_npcs = [n for n in valid_npcs if n.get("id") != npc_id]
            if not other_npcs:
                continue
            
            # 选择互动对象
            target_npc = random.choice(other_npcs)
            target_id = target_npc.get("id", "")
            target_name = target_npc.get("name", f"NPC_{target_id}")
            
            # 获取双方关系值（如果不存在则初始化为0）
            relationships = npc.get("relationships", {})
            current_relation = relationships.get(target_id, 0)
            
            # 获取双方情绪状态
            npc_mood = npc.get("mood", 50)
            target_mood = target_npc.get("mood", 50)
            
            # 根据关系值和情绪决定互动类型
            interaction_type = ""
            relation_change = 0
            mood_change_npc = 0
            mood_change_target = 0
            activity_change = 0
            
            # 规则1：如果关系值很低（< -20），可能发生争吵
            # 规则2：如果关系值很高（> 30），可能合作劳动
            # 规则3：其他情况进行交谈
            if current_relation < -20 and random.random() < 0.7:
                # 争吵
                interaction_type = "争吵"
                relation_change = random.randint(-5, -2)
                mood_change_npc = random.randint(-10, -5)
                mood_change_target = random.randint(-10, -5)
                activity_change = random.randint(1, 3)
                logs.append(f"{npc_name} 与 {target_name} 发生争吵")
                
            elif current_relation > 30 and random.random() < 0.6:
                # 合作劳动
                interaction_type = "合作劳动"
                relation_change = random.randint(1, 3)
                mood_change_npc = random.randint(2, 8)
                mood_change_target = random.randint(2, 8)
                activity_change = random.randint(3, 5)
                logs.append(f"{npc_name} 与 {target_name} 合作劳动")
                
            else:
                # 交谈
                interaction_type = "交谈"
                # 关系变化基于当前情绪：双方情绪都好则关系提升，否则可能下降
                mood_factor = (npc_mood - 50) / 100 + (target_mood - 50) / 100
                if mood_factor > 0:
                    relation_change = random.randint(1, 4)
                else:
                    relation_change = random.randint(-2, 1)
                
                # 情绪变化：交谈通常能改善情绪
                mood_change_npc = random.randint(-3, 5)
                mood_change_target = random.randint(-3, 5)
                activity_change = random.randint(1, 3)
                logs.append(f"{npc_name} 与 {target_name} 交谈")
            
            # 应用关系变化
            new_relation = current_relation + relation_change
            # 限制关系值在合理范围内
            new_relation = max(-100, min(100, new_relation))
            
            # 更新发起方对目标的关系
            changes.append({
                "path": f"npcs[id={npc_id}].relationships.{target_id}",
                "op": "set",
                "value": new_relation
            })
            
            # 更新目标对发起方的关系（对称变化，但可能有微小差异）
            target_relationships = target_npc.get("relationships", {})
            target_current_relation = target_relationships.get(npc_id, 0)
            target_new_relation = target_current_relation + relation_change + random.randint(-1, 1)
            target_new_relation = max(-100, min(100, target_new_relation))
            
            changes.append({
                "path": f"npcs[id={target_id}].relationships.{npc_id}",
                "op": "set",
                "value": target_new_relation
            })
            
            # 更新情绪值
            new_npc_mood = npc_mood + mood_change_npc
            new_npc_mood = max(0, min(100, new_npc_mood))
            
            new_target_mood = target_mood + mood_change_target
            new_target_mood = max(0, min(100, new_target_mood))
            
            changes.append({
                "path": f"npcs[id={npc_id}].mood",
                "op": "set",
                "value": new_npc_mood
            })
            
            changes.append({
                "path": f"npcs[id={target_id}].mood",
                "op": "set",
                "value": new_target_mood
            })
            
            # 更新活动度（activity）
            npc_activity = npc.get("activity", 0)
            target_activity = target_npc.get("activity", 0)
            
            new_npc_activity = npc_activity + activity_change
            new_target_activity = target_activity + activity_change
            
            changes.append({
                "path": f"npcs[id={npc_id}].activity",
                "op": "set",
                "value": new_npc_activity
            })
            
            changes.append({
                "path": f"npcs[id={target_id}].activity",
                "op": "set",
                "value": new_target_activity
            })
            
            # 记录互动事件到世界状态
            event = {
                "type": "social_interaction",
                "interaction_type": interaction_type,
                "participants": [npc_id, target_id],
                "relation_change": relation_change,
                "mood_changes": {
                    npc_id: mood_change_npc,
                    target_id: mood_change_target
                },
                "activity_change": activity_change,
                "timestamp": world.get("current_day", 0)
            }
            
            # 获取现有事件列表
            world_events = world.get("events", [])
            world_events.append(event)
            
            # 只保留最近100个事件
            if len(world_events) > 100:
                world_events = world_events[-100:]
            
            changes.append({
                "path": "world.events",
                "op": "set",
                "value": world_events
            })
        
        # 添加总结日志
        if selected_npcs:
            logs.append(f"今日社交互动：{len(selected_npcs)}名NPC参与了{len(selected_npcs)}次互动")
        
        return {"changes": changes, "logs": logs[:10]}
        
    except Exception as e:
        # 捕获所有异常，避免插件崩溃
        error_msg = f"社交互动插件错误: {str(e)}"
        return {"changes": [], "logs": [error_msg]}

if __name__ == "__main__":
    try:
        input_data = json.loads(sys.stdin.read())
        context = input_data.get("context", {})
        result = run(context)
        print(json.dumps(result))
    except Exception as e:
        error_result = {
            "changes": [],
            "logs": [f"插件执行失败: {str(e)}"]
        }
        print(json.dumps(error_result))