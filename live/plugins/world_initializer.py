import sys
import json
import random
from typing import Dict, List, Any, Tuple

class WorldInitializer:
    def __init__(self):
        self.terrain_types = ['forest', 'mountain', 'plain', 'river', 'wilderness']
        self.seasons = ['spring', 'summer', 'autumn', 'winter']
        self.male_names = ['Aric', 'Borin', 'Cedric', 'Doran', 'Eldric', 'Finn', 'Gareth', 'Hakon', 'Ivor', 'Jarek']
        self.female_names = ['Alia', 'Brienne', 'Cora', 'Elara', 'Faye', 'Gwen', 'Helena', 'Isolde', 'Kara', 'Lyra']
        self.surnames = ['Stonehammer', 'Ironwood', 'Stormrider', 'Shadowbane', 'Brightblade', 'Frostbeard', 'Goldenshield', 'Swiftarrow', 'Darkwater', 'Sunstrider']
        self.professions = ['farmer', 'hunter', 'warrior', 'craftsman', 'merchant', 'healer', 'scholar', 'fisherman', 'miner', 'herder']
        self.tribe_names = ['Ironwood Clan', 'Stonehammer Tribe', 'Stormrider Alliance']
        self.tribe_cultures = ['Mountain Dwellers', 'Forest Guardians', 'Plains Nomads']
        
    def generate_map(self, width: int, height: int) -> List[List[Dict]]:
        """生成随机地形地图"""
        map_grid = []
        for y in range(height):
            row = []
            for x in range(width):
                # 增加河流的概率，使其更连续
                if x > 0 and row[-1]['terrain'] == 'river' and random.random() < 0.6:
                    terrain = 'river'
                elif y > 0 and map_grid[y-1][x]['terrain'] == 'river' and random.random() < 0.6:
                    terrain = 'river'
                elif random.random() < 0.05:  # 5% 河流
                    terrain = 'river'
                else:
                    terrain = random.choice(['forest', 'mountain', 'plain', 'wilderness'])
                
                row.append({
                    'x': x,
                    'y': y,
                    'terrain': terrain,
                    'resources': self._generate_resources(terrain)
                })
            map_grid.append(row)
        return map_grid
    
    def _generate_resources(self, terrain: str) -> Dict:
        """根据地形生成资源"""
        base_resources = {
            'food': random.randint(0, 100),
            'wood': random.randint(0, 100),
            'stone': random.randint(0, 100),
            'water': random.randint(0, 100)
        }
        
        # 地形加成
        if terrain == 'forest':
            base_resources['wood'] += random.randint(50, 150)
            base_resources['food'] += random.randint(20, 80)
        elif terrain == 'mountain':
            base_resources['stone'] += random.randint(50, 150)
        elif terrain == 'plain':
            base_resources['food'] += random.randint(50, 150)
        elif terrain == 'river':
            base_resources['water'] += random.randint(100, 200)
            base_resources['food'] += random.randint(30, 100)
            
        return base_resources
    
    def generate_tribe(self, tribe_id: int, name: str, culture: str, map_width: int, map_height: int) -> Dict:
        """生成一个部落"""
        # 为每个部落分配不同的起始区域
        if tribe_id == 0:
            # 左上区域 - 适合山脉/森林
            base_x = random.randint(0, map_width // 3)
            base_y = random.randint(0, map_height // 3)
        elif tribe_id == 1:
            # 右上区域 - 适合森林/平原
            base_x = random.randint(2 * map_width // 3, map_width - 1)
            base_y = random.randint(0, map_height // 3)
        else:
            # 下部区域 - 适合平原/河流
            base_x = random.randint(map_width // 3, 2 * map_width // 3)
            base_y = random.randint(2 * map_height // 3, map_height - 1)
        
        # 确保坐标在范围内
        base_x = max(0, min(base_x, map_width - 1))
        base_y = max(0, min(base_y, map_height - 1))
        
        return {
            'id': f'tribe_{tribe_id}',
            'name': name,
            'culture': culture,
            'population': 100,
            'resources': {
                'food': random.randint(500, 1500),
                'wood': random.randint(300, 1000),
                'stone': random.randint(200, 800),
                'water': random.randint(800, 2000),
                'gold': random.randint(100, 500)
            },
            'territory': [{'x': base_x, 'y': base_y}],
            'diplomacy': {},
            'base_location': {'x': base_x, 'y': base_y}
        }
    
    def generate_npc(self, npc_id: int, tribe_id: str, base_location: Dict) -> Dict:
        """生成一个NPC"""
        is_male = random.random() > 0.5
        if is_male:
            first_name = random.choice(self.male_names)
        else:
            first_name = random.choice(self.female_names)
        
        surname = random.choice(self.surnames)
        
        # 根据部落位置生成NPC位置（在基地附近）
        offset_x = random.randint(-2, 2)
        offset_y = random.randint(-2, 2)
        
        return {
            'id': f'npc_{npc_id}',
            'name': f'{first_name} {surname}',
            'age': random.randint(18, 50),
            'gender': 'male' if is_male else 'female',
            'profession': random.choice(self.professions),
            'health': random.randint(80, 100),
            'stamina': random.randint(70, 100),
            'money': random.randint(10, 100),
            'tribe_id': tribe_id,
            'location': {
                'x': max(0, base_location['x'] + offset_x),
                'y': max(0, base_location['y'] + offset_y)
            },
            'relationships': {},
            'inventory': []
        }
    
    def generate_initial_state(self, world_config: Dict) -> Tuple[List, List, List]:
        """生成初始状态"""
        map_width = world_config.get('map_width', 50)
        map_height = world_config.get('map_height', 50)
        
        # 生成地图
        world_map = self.generate_map(map_width, map_height)
        
        # 生成部落
        tribes = []
        for i in range(3):
            tribe = self.generate_tribe(i, self.tribe_names[i], self.tribe_cultures[i], map_width, map_height)
            tribes.append(tribe)
        
        # 生成NPC（每个部落100人）
        npcs = []
        npc_counter = 0
        for tribe in tribes:
            for _ in range(100):
                npc = self.generate_npc(npc_counter, tribe['id'], tribe['base_location'])
                npcs.append(npc)
                npc_counter += 1
        
        return world_map, tribes, npcs

def run(context: dict) -> dict:
    """
    初始化世界状态
    
    Args:
        context: 包含世界配置的上下文
        
    Returns:
        包含变更和日志的字典
    """
    try:
        # 已初始化过则跳过（npcs 存在即视为已初始化）
        data = context.get("data", {})
        if data.get("npcs"):
            return {"changes": [], "logs": ["world already initialized, skipping"]}

        # 获取世界配置
        world_config = context.get('world_config', {})
        
        # 初始化生成器
        initializer = WorldInitializer()
        
        # 生成初始状态
        world_map, tribes, npcs = initializer.generate_initial_state(world_config)
        
        # 准备变更列表（用顶层 key，world 作为整体写入）
        changes = [
            {
                "path": "world",
                "op": "set",
                "value": {
                    "map": world_map,
                    "current_tick": 0,
                    "current_season": "spring"
                }
            },
            {
                "path": "tribes",
                "op": "set",
                "value": tribes
            },
            {
                "path": "npcs",
                "op": "set",
                "value": npcs
            }
        ]
        
        # 准备日志
        logs = [
            "世界初始化完成",
            f"地图大小: {len(world_map[0]) if world_map else 0} x {len(world_map)}",
            f"部落数量: {len(tribes)}",
            f"NPC总数: {len(npcs)}",
            f"初始季节: 春季",
            f"初始tick: 0"
        ]
        
        return {
            "changes": changes,
            "logs": logs
        }
        
    except Exception as e:
        return {
            "changes": [],
            "logs": [f"世界初始化失败: {str(e)}"]
        }

if __name__ == "__main__":
    # 从标准输入读取上下文
    try:
        input_data = sys.stdin.read()
        context = json.loads(input_data)
        
        # 运行插件
        result = run(context)
        
        # 输出结果到标准输出
        sys.stdout.write(json.dumps(result, ensure_ascii=False))
        
    except json.JSONDecodeError:
        sys.stderr.write("错误: 无效的JSON输入")
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"错误: {str(e)}")
        sys.exit(1)