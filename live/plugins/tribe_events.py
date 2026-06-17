import json
import sys
import random
from typing import Dict, List, Any, Tuple

class TribeEventsPlugin:
    """部落事件生成插件"""
    
    def __init__(self):
        self.event_types = {
            'internal': ['leadership_change', 'resource_discovery', 'cultural_development', 'disease_outbreak', 
                        'skill_advancement', 'population_boom', 'internal_conflict', 'religious_awakening'],
            'external': ['trade_agreement', 'border_conflict', 'diplomatic_mission', 'resource_raid',
                        'cultural_exchange', 'military_alliance', 'espionage', 'tribal_marriage']
        }
        
    def run(self, context: dict) -> dict:
        """主运行函数"""
        data = context.get("data", {})
        changes = []
        logs = []
        
        # 获取必要数据
        tribes = data.get("tribes", [])
        current_tick = data.get("world", {}).get("current_tick", 0)
        world_map = data.get("world", {}).get("map", {})
        
        if not tribes or len(tribes) < 2:
            return {"changes": changes, "logs": logs}
        
        # 每10个tick生成一次事件
        if current_tick % 10 == 0:
            # 生成部落内部事件
            internal_events = self._generate_internal_events(tribes, current_tick)
            changes.extend(internal_events["changes"])
            logs.extend(internal_events["logs"])
            
            # 生成部落间事件
            external_events = self._generate_external_events(tribes, world_map, current_tick)
            changes.extend(external_events["changes"])
            logs.extend(external_events["logs"])
        
        return {"changes": changes, "logs": logs}
    
    def _generate_internal_events(self, tribes: List[Dict], current_tick: int) -> Dict[str, List]:
        """生成部落内部事件"""
        changes = []
        logs = []
        
        for tribe in tribes:
            tribe_id = tribe.get("id")
            tribe_name = tribe.get("name", f"部落{tribe_id}")
            
            # 随机决定是否生成事件（30%概率）
            if random.random() < 0.3:
                event_type = random.choice(self.event_types['internal'])
                event_data = self._create_internal_event(tribe, event_type, current_tick)
                
                if event_data:
                    # 添加到事件列表
                    changes.append({
                        "path": "events",
                        "op": "append",
                        "value": event_data["event"]
                    })
                    
                    # 更新部落状态
                    for tribe_change in event_data.get("tribe_changes", []):
                        changes.append({
                            "path": f"tribes.{tribe_id}.{tribe_change['field']}",
                            "op": tribe_change["op"],
                            "value": tribe_change["value"]
                        })
                    
                    logs.append(f"Tick {current_tick}: {tribe_name} 发生 {event_data['event']['description']}")
        
        return {"changes": changes, "logs": logs}
    
    def _generate_external_events(self, tribes: List[Dict], world_map: Dict, current_tick: int) -> Dict[str, List]:
        """生成部落间事件"""
        changes = []
        logs = []
        
        # 随机选择两个不同的部落
        if len(tribes) >= 2:
            tribe1, tribe2 = random.sample(tribes, 2)
            tribe1_id = tribe1.get("id")
            tribe2_id = tribe2.get("id")
            tribe1_name = tribe1.get("name", f"部落{tribe1_id}")
            tribe2_name = tribe2.get("name", f"部落{tribe2_id}")
            
            # 检查部落间距离
            if self._are_tribes_adjacent(tribe1, tribe2, world_map):
                # 50%概率生成事件
                if random.random() < 0.5:
                    event_type = random.choice(self.event_types['external'])
                    event_data = self._create_external_event(tribe1, tribe2, event_type, current_tick)
                    
                    if event_data:
                        # 添加到事件列表
                        changes.append({
                            "path": "events",
                            "op": "append",
                            "value": event_data["event"]
                        })
                        
                        # 更新部落状态
                        for tribe_change in event_data.get("tribe_changes", []):
                            tribe_id = tribe_change["tribe_id"]
                            changes.append({
                                "path": f"tribes.{tribe_id}.{tribe_change['field']}",
                                "op": tribe_change["op"],
                                "value": tribe_change["value"]
                            })
                        
                        logs.append(f"Tick {current_tick}: {tribe1_name} 和 {tribe2_name} 之间发生 {event_data['event']['description']}")
        
        return {"changes": changes, "logs": logs}
    
    def _create_internal_event(self, tribe: Dict, event_type: str, current_tick: int) -> Dict[str, Any]:
        """创建具体的部落内部事件"""
        tribe_id = tribe.get("id")
        tribe_name = tribe.get("name", f"部落{tribe_id}")
        
        event_templates = {
            "leadership_change": {
                "description": f"{tribe_name}发生领导权更迭",
                "effects": [{"field": "leadership_stability", "op": "set", "value": random.randint(50, 100)}]
            },
            "resource_discovery": {
                "description": f"{tribe_name}发现了新的资源点",
                "effects": [{"field": "resources.food", "op": "add", "value": random.randint(50, 200)}]
            },
            "cultural_development": {
                "description": f"{tribe_name}文化得到发展",
                "effects": [{"field": "culture_level", "op": "add", "value": random.randint(1, 5)}]
            },
            "disease_outbreak": {
                "description": f"{tribe_name}爆发疾病",
                "effects": [
                    {"field": "population", "op": "add", "value": -random.randint(5, 20)},
                    {"field": "health_status", "op": "set", "value": "outbreak"}
                ]
            },
            "skill_advancement": {
                "description": f"{tribe_name}的工匠技艺得到提升",
                "effects": [{"field": "technology_level", "op": "add", "value": random.randint(1, 3)}]
            },
            "population_boom": {
                "description": f"{tribe_name}人口快速增长",
                "effects": [{"field": "population", "op": "add", "value": random.randint(10, 30)}]
            },
            "internal_conflict": {
                "description": f"{tribe_name}发生内部冲突",
                "effects": [
                    {"field": "stability", "op": "add", "value": -random.randint(10, 30)},
                    {"field": "population", "op": "add", "value": -random.randint(5, 15)}
                ]
            },
            "religious_awakening": {
                "description": f"{tribe_name}出现宗教觉醒",
                "effects": [
                    {"field": "spirituality", "op": "add", "value": random.randint(5, 15)},
                    {"field": "stability", "op": "add", "value": random.randint(5, 15)}
                ]
            }
        }
        
        if event_type not in event_templates:
            return {}
        
        template = event_templates[event_type]
        event = {
            "id": f"event_{current_tick}_{tribe_id}_{random.randint(1000, 9999)}",
            "type": event_type,
            "subtype": "internal",
            "tick": current_tick,
            "description": template["description"],
            "participants": [tribe_id],
            "effects": []
        }
        
        tribe_changes = []
        for effect in template["effects"]:
            tribe_changes.append({
                "tribe_id": tribe_id,
                "field": effect["field"],
                "op": effect["op"],
                "value": effect["value"]
            })
        
        return {
            "event": event,
            "tribe_changes": tribe_changes
        }
    
    def _create_external_event(self, tribe1: Dict, tribe2: Dict, event_type: str, current_tick: int) -> Dict[str, Any]:
        """创建具体的部落间事件"""
        tribe1_id = tribe1.get("id")
        tribe2_id = tribe2.get("id")
        tribe1_name = tribe1.get("name", f"部落{tribe1_id}")
        tribe2_name = tribe2.get("name", f"部落{tribe2_id}")
        
        event_templates = {
            "trade_agreement": {
                "description": f"{tribe1_name}与{tribe2_name}达成贸易协议",
                "effects": [
                    {"tribe_id": tribe1_id, "field": "resources.food", "op": "add", "value": random.randint(20, 100)},
                    {"tribe_id": tribe2_id, "field": "resources.food", "op": "add", "value": random.randint(20, 100)},
                    {"tribe_id": tribe1_id, "field": f"diplomacy.{tribe2_id}", "op": "set", "value": "trade_partner"},
                    {"tribe_id": tribe2_id, "field": f"diplomacy.{tribe1_id}", "op": "set", "value": "trade_partner"}
                ]
            },
            "border_conflict": {
                "description": f"{tribe1_name}与{tribe2_name}发生边境冲突",
                "effects": [
                    {"tribe_id": tribe1_id, "field": "population", "op": "add", "value": -random.randint(5, 15)},
                    {"tribe_id": tribe2_id, "field": "population", "op": "add", "value": -random.randint(5, 15)},
                    {"tribe_id": tribe1_id, "field": f"diplomacy.{tribe2_id}", "op": "set", "value": "hostile"},
                    {"tribe_id": tribe2_id, "field": f"diplomacy.{tribe1_id}", "op": "set", "value": "hostile"}
                ]
            },
            "diplomatic_mission": {
                "description": f"{tribe1_name}向{tribe2_name}派遣外交使团",
                "effects": [
                    {"tribe_id": tribe1_id, "field": f"diplomacy.{tribe2_id}", "op": "set", "value": "neutral"},
                    {"tribe_id": tribe2_id, "field": f"diplomacy.{tribe1_id}", "op": "set", "value": "neutral"}
                ]
            },
            "resource_raid": {
                "description": f"{tribe1_name}突袭了{tribe2_name}的资源点",
                "effects": [
                    {"tribe_id": tribe1_id, "field": "resources.food", "op": "add", "value": random.randint(30, 80)},
                    {"tribe_id": tribe2_id, "field": "resources.food", "op": "add", "value": -random.randint(30, 80)},
                    {"tribe_id": tribe1_id, "field": f"diplomacy.{tribe2_id}", "op": "set", "value": "hostile"}
                ]
            },
            "cultural_exchange": {
                "description": f"{tribe1_name}与{tribe2_name}进行文化交流",
                "effects": [
                    {"tribe_id": tribe1_id, "field": "culture_level", "op": "add", "value": random.randint(1, 3)},
                    {"tribe_id": tribe2_id, "field": "culture_level", "op": "add", "value": random.randint(1, 3)}
                ]
            },
            "military_alliance": {
                "description": f"{tribe1_name}与{tribe2_name}结成军事同盟",
                "effects": [
                    {"tribe_id": tribe1_id, "field": "military_strength", "op": "add", "value": random.randint(10, 30)},
                    {"tribe_id": tribe2_id, "field": "military_strength", "op": "add", "value": random.randint(10, 30)},
                    {"tribe_id": tribe1_id, "field": f"diplomacy.{tribe2_id}", "op": "set", "value": "ally"},
                    {"tribe_id": tribe2_id, "field": f"diplomacy.{tribe1_id}", "op": "set", "value": "ally"}
                ]
            }
        }
        
        if event_type not in event_templates:
            return {}
        
        template = event_templates[event_type]
        event = {
            "id": f"event_{current_tick}_{tribe1_id}_{tribe2_id}_{random.randint(1000, 9999)}",
            "type": event_type,
            "subtype": "external",
            "tick": current_tick,
            "description": template["description"],
            "participants": [tribe1_id, tribe2_id],
            "effects": []
        }
        
        tribe_changes = []
        for effect in template["effects"]:
            tribe_changes.append({
                "tribe_id": effect["tribe_id"],
                "field": effect["field"],
                "op": effect["op"],
                "value": effect["value"]
            })
        
        return {
            "event": event,
            "tribe_changes": tribe_changes
        }
    
    def _are_tribes_adjacent(self, tribe1: Dict, tribe2: Dict, world_map: Dict) -> bool:
        """检查两个部落是否相邻"""
        # 简化实现：随机决定是否相邻（实际应根据地图位置判断）
        return random.random() < 0.6

def run(context: dict) -> dict:
    """插件入口函数"""
    plugin = TribeEventsPlugin()
    return plugin.run(context)

if __name__ == "__main__":
    # 从标准输入读取context
    input_str = sys.stdin.read()
    try:
        context = json.loads(input_str)
        result = run(context)
        # 输出结果到标准输出
        print(json.dumps(result, ensure_ascii=False))
    except json.JSONDecodeError as e:
        print(json.dumps({"changes": [], "logs": [f"JSON解析错误: {str(e)}"]}))
    except Exception as e:
        print(json.dumps({"changes": [], "logs": [f"插件执行错误: {str(e)}"]}))