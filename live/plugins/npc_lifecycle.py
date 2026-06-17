import json
import sys
import random
from typing import Dict, List, Any, Optional

class NPCLifecyclePlugin:
    """
    NPC生命周期管理插件
    处理出生、死亡、年龄增长、健康体力自然变化
    """
    
    def __init__(self):
        # 年龄相关配置
        self.max_age = 80  # 最大年龄
        self.childbearing_age_range = (18, 40)  # 生育年龄范围
        self.old_age_threshold = 60  # 老年阈值
        
        # 健康/体力变化配置
        self.base_health_change = {
            "spring": -0.5,  # 春季健康变化
            "summer": -1.0,  # 夏季健康变化（炎热）
            "autumn": -0.3,  # 秋季健康变化
            "winter": -2.0   # 冬季健康变化（寒冷）
        }
        
        self.base_stamina_change = {
            "spring": -1.0,
            "summer": -2.0,  # 夏季体力消耗大
            "autumn": -0.5,
            "winter": -3.0   # 冬季生存困难
        }
        
        # 出生率配置（每1000人每年的出生数）
        self.base_birth_rate = 25
        # 死亡率配置（每1000人每年的死亡数）
        self.base_death_rate = 15
        
    def run(self, context: Dict) -> Dict:
        """
        主运行函数
        
        Args:
            context: 包含世界状态的上下文
            
        Returns:
            包含变化和日志的字典
        """
        data = context.get("data", {})
        changes = []
        logs = []
        
        # 获取必要数据
        npcs = data.get("npcs", [])
        current_tick = data.get("world", {}).get("current_tick", 0)
        current_season = data.get("world", {}).get("current_season", "spring")
        
        if not npcs:
            return {"changes": changes, "logs": logs}
        
        # 计算时间流逝（假设1tick=1天）
        days_per_year = 360
        years_passed = current_tick / days_per_year if current_tick > days_per_year else 0
        
        # 1. 处理年龄增长（每年一次）
        if current_tick % days_per_year == 0 and current_tick > 0:
            age_changes, age_logs = self._process_aging(npcs, current_tick)
            changes.extend(age_changes)
            logs.extend(age_logs)
        
        # 2. 处理健康体力自然变化（每天）
        health_stamina_changes, health_stamina_logs = self._process_health_stamina(
            npcs, current_season
        )
        changes.extend(health_stamina_changes)
        logs.extend(health_stamina_logs)
        
        # 3. 处理死亡（每天检查）
        death_changes, death_logs, remaining_npcs = self._process_deaths(
            npcs, current_season, current_tick
        )
        changes.extend(death_changes)
        logs.extend(death_logs)
        
        # 4. 处理出生（每季度一次）
        if current_tick % (days_per_year // 4) == 0:
            birth_changes, birth_logs = self._process_births(
                remaining_npcs, current_season, current_tick
            )
            changes.extend(birth_changes)
            logs.extend(birth_logs)
        
        # 5. 生成生命周期事件
        if logs:
            event_changes = self._create_lifecycle_events(logs, current_tick)
            changes.extend(event_changes)
        
        return {"changes": changes, "logs": logs}
    
    def _process_aging(self, npcs: List[Dict], current_tick: int) -> tuple:
        """处理年龄增长"""
        changes = []
        logs = []
        
        for npc in npcs:
            npc_id = npc.get("id")
            current_age = npc.get("age", 0)
            
            # 年龄增长1岁
            new_age = current_age + 1
            
            changes.append({
                "path": f"npcs.{npc_id}.age",
                "op": "set",
                "value": new_age
            })
            
            # 记录生日日志
            if new_age % 10 == 0:  # 每10岁记录一次
                logs.append(f"NPC {npc.get('name')} 庆祝 {new_age} 岁生日")
            elif new_age == 18:
                logs.append(f"NPC {npc.get('name')} 成年")
            elif new_age == self.old_age_threshold:
                logs.append(f"NPC {npc.get('name')} 进入老年")
        
        return changes, logs
    
    def _process_health_stamina(self, npcs: List[Dict], season: str) -> tuple:
        """处理健康和体力自然变化"""
        changes = []
        logs = []
        
        base_health_change = self.base_health_change.get(season, -0.5)
        base_stamina_change = self.base_stamina_change.get(season, -1.0)
        
        for npc in npcs:
            npc_id = npc.get("id")
            current_health = npc.get("health", 100)
            current_stamina = npc.get("stamina", 100)
            age = npc.get("age", 25)
            
            # 计算年龄影响
            age_factor = 1.0
            if age > self.old_age_threshold:
                age_factor = 1.5  # 老年人健康下降更快
            elif age < 18:
                age_factor = 0.8  # 年轻人恢复力强
            
            # 计算职业影响
            profession = npc.get("profession", "laborer")
            profession_factor = self._get_profession_health_factor(profession)
            
            # 计算最终变化
            health_change = base_health_change * age_factor * profession_factor
            stamina_change = base_stamina_change * age_factor * profession_factor
            
            # 应用变化（确保在合理范围内）
            new_health = max(0, min(100, current_health + health_change))
            new_stamina = max(0, min(100, current_stamina + stamina_change))
            
            if new_health != current_health:
                changes.append({
                    "path": f"npcs.{npc_id}.health",
                    "op": "set",
                    "value": new_health
                })
            
            if new_stamina != current_stamina:
                changes.append({
                    "path": f"npcs.{npc_id}.stamina",
                    "op": "set",
                    "value": new_stamina
                })
            
            # 记录严重变化
            if health_change < -5:
                logs.append(f"NPC {npc.get('name')} 在{season}季节健康状况显著下降")
            elif stamina_change < -10:
                logs.append(f"NPC {npc.get('name')} 在{season}季节体力消耗过大")
        
        return changes, logs
    
    def _process_deaths(self, npcs: List[Dict], season: str, current_tick: int) -> tuple:
        """处理死亡"""
        changes = []
        logs = []
        remaining_npcs = []
        
        for npc in npcs:
            npc_id = npc.get("id")
            age = npc.get("age", 25)
            health = npc.get("health", 100)
            
            # 计算死亡概率
            death_probability = self._calculate_death_probability(age, health, season)
            
            # 随机决定是否死亡
            if random.random() < death_probability:
                # 记录死亡
                changes.append({
                    "path": f"npcs.{npc_id}",
                    "op": "remove",
                    "value": None
                })
                
                # 生成死亡原因
                cause = self._generate_death_cause(age, health, season)
                death_log = f"NPC {npc.get('name')} ({age}岁) 因{cause}死亡"
                logs.append(death_log)
            else:
                remaining_npcs.append(npc)
        
        return changes, logs, remaining_npcs
    
    def _process_births(self, npcs: List[Dict], season: str, current_tick: int) -> tuple:
        """处理出生"""
        changes = []
        logs = []
        
        # 按部落分组
        tribes = {}
        for npc in npcs:
            tribe_id = npc.get("tribe_id")
            if tribe_id not in tribes:
                tribes[tribe_id] = []
            tribes[tribe_id].append(npc)
        
        # 为每个部落计算出生数量
        for tribe_id, tribe_npcs in tribes.items():
            # 计算育龄人口
            childbearing_population = [
                npc for npc in tribe_npcs 
                if self.childbearing_age_range[0] <= npc.get("age", 0) <= self.childbearing_age_range[1]
                and npc.get("gender") == "female"  # 简化：只有女性可以生育
            ]
            
            if not childbearing_population:
                continue
            
            # 计算出生数量（考虑季节影响）
            season_factor = {
                "spring": 1.2,  # 春季出生率高
                "summer": 1.0,
                "autumn": 0.9,
                "winter": 0.7   # 冬季出生率低
            }.get(season, 1.0)
            
            birth_rate = self.base_birth_rate * season_factor / 1000  # 转换为概率
            expected_births = int(len(childbearing_population) * birth_rate)
            
            # 确保至少有一定概率出生
            if expected_births == 0 and random.random() < birth_rate:
                expected_births = 1
            
            # 生成新生儿
            for _ in range(expected_births):
                if childbearing_population:
                    mother = random.choice(childbearing_population)
                    
                    # 创建新生儿
                    newborn_id = f"npc_{current_tick}_{random.randint(1000, 9999)}"
                    newborn = self._create_newborn(newborn_id, mother, tribe_id)
                    
                    changes.append({
                        "path": f"npcs.{newborn_id}",
                        "op": "add",
                        "value": newborn
                    })
                    
                    birth_log = f"新生儿 {newborn['name']} 在{mother.get('tribe_name', '未知部落')}出生，母亲是{mother.get('name')}"
                    logs.append(birth_log)
        
        return changes, logs
    
    def _create_lifecycle_events(self, logs: List[str], current_tick: int) -> List[Dict]:
        """创建生命周期事件"""
        changes = []
        
        for log in logs:
            if "死亡" in log or "出生" in log or "庆祝" in log:
                event_id = f"event_lifecycle_{current_tick}_{random.randint(1000, 9999)}"
                event = {
                    "id": event_id,
                    "type": "lifecycle",
                    "description": log,
                    "tick": current_tick,
                    "severity": "high" if "死亡" in log else "medium" if "出生" in log else "low"
                }
                
                changes.append({
                    "path": f"events.{event_id}",
                    "op": "add",
                    "value": event
                })
        
        return changes
    
    def _get_profession_health_factor(self, profession: str) -> float:
        """获取职业对健康的影响因子"""
        factors = {
            "farmer": 1.1,      # 农民，户外活动健康
            "hunter": 0.9,      # 猎人，危险但锻炼
            "warrior": 0.8,     # 战士，高风险
            "healer": 1.2,      # 治疗师，懂得保养
            "scholar": 1.0,     # 学者，中等
            "laborer": 0.95,    # 劳工，体力消耗大
            "merchant": 1.05,   # 商人，中等
            "leader": 1.1       # 领袖，生活较好
        }
        return factors.get(profession, 1.0)
    
    def _calculate_death_probability(self, age: int, health: float, season: str) -> float:
        """计算死亡概率"""
        # 基础概率
        base_prob = self.base_death_rate / 1000 / 360  # 转换为每日概率
        
        # 年龄影响
        age_factor = 1.0
        if age < 5:  # 婴幼儿
            age_factor = 3.0
        elif age > self.old_age_threshold:
            age_factor = 2.0 + (age - self.old_age_threshold) * 0.1
        
        # 健康影响
        health_factor = 1.0
        if health < 30:
            health_factor = 3.0
        elif health < 50:
            health_factor = 1.5
        
        # 季节影响
        season_factor = {
            "spring": 1.0,
            "summer": 1.2,  # 夏季疾病多
            "autumn": 1.0,
            "winter": 1.5   # 冬季生存困难
        }.get(season, 1.0)
        
        return base_prob * age_factor * health_factor * season_factor
    
    def _generate_death_cause(self, age: int, health: float, season: str) -> str:
        """生成死亡原因"""
        causes = []
        
        # 年龄相关原因
        if age < 5:
            causes.extend(["先天疾病", "营养不良", "幼儿疾病"])
        elif age > self.old_age_threshold:
            causes.extend(["年老体衰", "器官衰竭", "自然死亡"])
        
        # 健康相关原因
        if health < 20:
            causes.extend(["重病", "重伤不治", "虚弱致死"])
        
        # 季节相关原因
        if season == "winter":
            causes.extend(["冻死", "冬季疾病", "食物短缺"])
        elif season == "summer":
            causes.extend(["中暑", "夏季瘟疫", "脱水"])
        
        # 通用原因
        causes.extend(["意外事故", "未知疾病", "自然原因"])
        
        return random.choice(causes)
    
    def _create_newborn(self, newborn_id: str, mother: Dict, tribe_id: str) -> Dict:
        """创建新生儿"""
        # 生成姓名（简化：使用母亲姓氏 + 随机名）
        mother_name = mother.get("name", "").split()
        surname = mother_name[-1] if mother_name else f"of Tribe {tribe_id}"
        
        first_names = {
            "male": ["John", "William", "James", "Robert", "Michael", "David"],
            "female": ["Mary", "Elizabeth", "Sarah", "Anne", "Emma", "Alice"]
        }
        
        gender = random.choice(["male", "female"])
        first_name = random.choice(first_names.get(gender, ["Unknown"]))
        full_name = f"{first_name} {surname}"
        
        return {
            "id": newborn_id,
            "name": full_name,
            "age": 0,
            "gender": gender,
            "profession": "child",
            "health": 100,
            "stamina": 100,
            "money": 0,
            "tribe_id": tribe_id,
            "tribe_name": mother.get("tribe_name", f"Tribe {tribe_id}"),
            "location": mother.get("location", [0, 0]),
            "parent_id": mother.get("id")
        }


def main():
    """主函数：从标准输入读取，处理，输出到标准输出"""
    try:
        # 读取输入
        input_data = sys.stdin.read()
        context = json.loads(input_data)
        
        # 创建插件并运行
        plugin = NPCLifecyclePlugin()
        result = plugin.run(context)
        
        # 输出结果
        output = json.dumps(result, ensure_ascii=False)
        sys.stdout.write(output)
        
    except Exception as e:
        # 错误处理
        error_result = {
            "changes": [],
            "logs": [f"插件执行错误: {str(e)}"]
        }
        sys.stdout.write(json.dumps(error_result, ensure_ascii=False))


if __name__ == "__main__":
    main()