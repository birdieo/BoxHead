import math
import pygame
import random

class Weapon:
    def __init__(self, name, damage, fire_rate, bullet_speed, icon_color=(255,255,0), special_type=None, max_ammo=100):
        self.name = name
        self.damage = damage
        self.fire_rate = fire_rate  # milliseconds between shots
        self.bullet_speed = bullet_speed
        self.icon_color = icon_color
        self.special_type = special_type  # None, 'wall', 'mine'
        self.max_ammo = max_ammo

# Predefined weapons (icons will be colored rectangles for now)
WEAPON_LIST = [
    Weapon("Pistol", damage=25, fire_rate=250, bullet_speed=10, icon_color=(255,255,0), max_ammo=100), # Weakest
    Weapon("Weapon 3", damage=25, fire_rate=100, bullet_speed=15, icon_color=(255,0,255), max_ammo=150), # Same damage as Pistol
    Weapon("Wall Spawner", damage=0, fire_rate=1000, bullet_speed=0, icon_color=(150,75,0), special_type='wall', max_ammo=10),
    Weapon("Mine Placer", damage=150, fire_rate=1000, bullet_speed=0, icon_color=(255,0,0), special_type='mine', max_ammo=5), # More damage than Shotgun total
    Weapon("Shotgun", damage=40, fire_rate=750, bullet_speed=12, icon_color=(255,165,0), max_ammo=50), # 40 damage per bullet, 3 bullets = 120 total
]

def get_random_weapon():
    other_weapons = [w for w in WEAPON_LIST if w.name != "Pistol"]
    return random.choice(other_weapons) if other_weapons else WEAPON_LIST[0]

def get_weapon_by_name(name):
    for w in WEAPON_LIST:
        if w.name == name:
            return w
    return WEAPON_LIST[0]

class Player:
    def __init__(self, x, y, player_id):
        self.x = x
        self.y = y
        self.player_id = player_id
        self.angle = 0
        self.health = 500
        self.armor = 0  # New armor attribute
        self.max_armor = 400  # Maximum armor (4 * 100)
        self.speed = 5
        self.size = 30
        self.color = (0, 255, 0)
        self.bullets = []
        self.last_shot = 0
        basic_weapon = get_weapon_by_name("Pistol")
        self.weapons = [basic_weapon]
        self.selected_weapon_index = 0
        self.dead = False
        self.respawn_timer = 0
        self.ammo = {basic_weapon.name: basic_weapon.max_ammo}

    @property
    def current_weapon(self):
        return self.weapons[self.selected_weapon_index]

    def add_weapon(self, weapon):
        # Dodaj broń tylko jeśli jej jeszcze nie ma
        if all(w.name != weapon.name for w in self.weapons):
            self.weapons.append(weapon)
        # Niezależnie od tego, czy broń jest nowa, uzupełnij amunicję
        self.ammo[weapon.name] = weapon.max_ammo

    def switch_weapon(self, index):
        if 0 <= index < len(self.weapons):
            self.selected_weapon_index = index

    def move(self, dx, dy):
        self.x += dx * self.speed
        self.y += dy * self.speed

    def rotate(self, target_x, target_y):
        self.angle = math.degrees(math.atan2(target_y - self.y, target_x - self.x))

    def shoot(self, current_time):
        weapon = self.current_weapon
        if current_time - self.last_shot > weapon.fire_rate and self.ammo.get(weapon.name, 0) > 0:
            self.last_shot = current_time
            
            # Consume ammo for all weapon types
            self.ammo[weapon.name] -= 1
            
            if weapon.special_type is None:
                return Bullet(self.x, self.y, self.angle, self.player_id, weapon)
            elif weapon.special_type == 'wall' or weapon.special_type == 'mine':
                return None
        return None

    def kill(self):
        self.dead = True
        self.respawn_timer = 5  # 5 sekund

    def respawn(self):
        self.dead = False
        self.health = 500
        self.armor = 0  # Reset armor on respawn
        self.x, self.y = 400, 300
        self.respawn_timer = 0
        basic_weapon = get_weapon_by_name("Pistol")
        self.weapons = [basic_weapon]
        self.selected_weapon_index = 0
        self.ammo = {basic_weapon.name: basic_weapon.max_ammo}

    def add_armor(self, value):
        self.armor = min(self.max_armor, self.armor + value)

    def add_health(self, value):
        self.health = min(500, self.health + value)  # Max health is 500

    def take_damage(self, damage):
        # First absorb damage with armor
        if self.armor > 0:
            armor_damage = min(self.armor, damage)
            self.armor -= armor_damage
            damage -= armor_damage
        
        # Remaining damage goes to health
        if damage > 0:
            self.health -= damage
            if self.health <= 0 and not self.dead:
                self.kill()

    def draw(self, screen, camera_offset=(0,0)):
        cx, cy = camera_offset
        # Draw player body
        pygame.draw.circle(screen, self.color, (int(self.x-cx), int(self.y-cy)), self.size)
        # Draw direction indicator
        end_x = self.x + math.cos(math.radians(self.angle)) * self.size
        end_y = self.y + math.sin(math.radians(self.angle)) * self.size
        pygame.draw.line(screen, (255, 0, 0), (self.x-cx, self.y-cy), (end_x-cx, end_y-cy), 3)

class Bullet:
    def __init__(self, x, y, angle, player_id, weapon=None):
        self.x = x
        self.y = y
        self.angle = angle
        self.player_id = player_id
        self.size = 5
        self.lifetime = 60  # frames
        if weapon:
            self.speed = weapon.bullet_speed
            self.damage = weapon.damage
            self.color = weapon.icon_color
        else:
            self.speed = 10
            self.damage = 25
            self.color = (255, 255, 0)

    def update(self):
        self.x += math.cos(math.radians(self.angle)) * self.speed
        self.y += math.sin(math.radians(self.angle)) * self.speed
        self.lifetime -= 1

    def draw(self, screen, camera_offset=(0,0)):
        cx, cy = camera_offset
        pygame.draw.circle(screen, self.color, (int(self.x-cx), int(self.y-cy)), self.size)

class Enemy:
    def __init__(self, x, y, enemy_type=1):
        self.x = x
        self.y = y
        self.type = enemy_type
        # Base speeds: Type 1: 15.0, Type 2: 10.0, Type 3: 7.0 (from last change)
        # Multiply by 5
        if self.type == 1:
            self.health = 100
            self.speed = 75.0 # 15.0 * 5
            self.size = 20
            self.color = (0, 255, 0)  # Zielony
            self.damage = 2
            self._initial_health = 100 # Do obliczania paska zdrowia
            self._is_shooter = False
            self._last_shot = 0
            self._fire_rate = 0
            self._bullet_damage = 0
            self._bullet_speed = 0
            
        elif self.type == 2:
            self.health = 200
            self.speed = 50.0 # 10.0 * 5
            self.size = 28
            self.color = (0, 128, 255)  # Niebieski
            self.damage = 5
            self._initial_health = 200
            self._is_shooter = False
            self._last_shot = 0
            self._fire_rate = 0
            self._bullet_damage = 0
            self._bullet_speed = 0

        elif self.type == 3:
            self.health = 400
            self.speed = 35.0 # 7.0 * 5
            self.size = 36
            self.color = (255, 0, 0)  # Czerwony
            self.damage = 12
            self._initial_health = 400
            self._is_shooter = False
            self._last_shot = 0
            self._fire_rate = 0
            self._bullet_damage = 0
            self._bullet_speed = 0

        elif self.type == 4: # Nowy typ: Strzelający wróg
             self.health = 150
             self.speed = 30.0 # Nieco wolniejszy niż biegacze
             self.size = 25
             self.color = (128, 0, 128) # Fioletowy
             self.damage = 5 # Obrażenia w kontakcie (jeśli dojdzie)
             self._initial_health = 150
             self._is_shooter = True # Ten wróg strzela
             self._last_shot = 0
             self._fire_rate = 1000 # Millisekundy między strzałami (np. 1 strzał na sekundę)
             self._bullet_damage = 15 # Obrażenia pocisku
             self._bullet_speed = 8 # Prędkość pocisku

        # Pola do patrolowania
        self._patrol_target = (self.x, self.y) # Cel patrolowania
        self._patrol_timer = 0 # Czas do zmiany celu
        self._patrol_duration = 2 # Sekundy na jeden kierunek patrolowania
        self.look_angle = 0 # Kąt, w którym patrzy wróg (synchronizowany)

    def move_towards(self, target_x, target_y):
        angle = math.atan2(target_y - self.y, target_x - self.x)
        dx = math.cos(angle)
        dy = math.sin(angle)
        return dx, dy

    def get_patrol_vector(self, dt):
        self._patrol_timer += dt
        if self._patrol_timer >= self._patrol_duration:
            self._patrol_timer = 0
            self._patrol_target = (
                self.x + random.randint(-200, 200),
                self.y + random.randint(-200, 200)
            )
        
        angle = math.atan2(self._patrol_target[1] - self.y, self._patrol_target[0] - self.x)
        return math.cos(angle), math.sin(angle)

    def draw(self, screen, camera_offset=(0,0)):
        cx, cy = camera_offset
        # Draw enemy body
        pygame.draw.circle(screen, self.color, (int(self.x-cx), int(self.y-cy)), self.size)
        
        # Draw health bar
        health_width = 40
        health_height = 5
        health_x = int(self.x - health_width/2 - cx)
        health_y = int(self.y - self.size - 10 - cy)
        
        # Background (red)
        pygame.draw.rect(screen, (255,0,0), (health_x, health_y, health_width, health_height))
        # Foreground (green)
        current_health_width = (self.health / self._initial_health) * health_width
        pygame.draw.rect(screen, (0,255,0), (health_x, health_y, current_health_width, health_height))
        
        # Draw direction indicator
        end_x = self.x + math.cos(math.radians(self.look_angle)) * self.size
        end_y = self.y + math.sin(math.radians(self.look_angle)) * self.size
        pygame.draw.line(screen, (255, 255, 255), (self.x-cx, self.y-cy), (end_x-cx, end_y-cy), 2)

class Wall:
    def __init__(self, x, y, width, height, is_player_wall=False, health=100):
        self.rect = pygame.Rect(x, y, width, height)
        self.is_player_wall = is_player_wall
        self.health = health
        self.max_health = health

    def draw(self, screen, camera_offset=(0,0)):
        cx, cy = camera_offset
        rect = pygame.Rect(self.rect.x - cx, self.rect.y - cy, self.rect.width, self.rect.height)
        color = (150,75,0) if self.is_player_wall else (128,128,128)
        pygame.draw.rect(screen, color, rect)
        if self.is_player_wall:
            health_percent = self.health / self.max_health
            health_height = self.rect.height * health_percent
            health_rect = pygame.Rect(rect.x, rect.bottom - health_height, rect.width, health_height)
            pygame.draw.rect(screen, (0,255,0), health_rect)

class LootBox:
    def __init__(self, x, y, weapon=None):
        self.x = x
        self.y = y
        self.size = 15
        self.weapon = weapon if weapon else get_random_weapon()
        self.color = self.weapon.icon_color

    def draw(self, screen, camera_offset=(0,0)):
        cx, cy = camera_offset
        rect = pygame.Rect(int(self.x-self.size-cx), int(self.y-self.size-cy), self.size*2, self.size*2)
        pygame.draw.rect(screen, self.color, rect)
        # Draw border
        pygame.draw.rect(screen, (255,255,255), rect, 2)

class Mine:
    def __init__(self, x, y, owner_id, damage=50):
        self.x = x
        self.y = y
        self.size = 10
        self.owner_id = owner_id
        self.damage = damage
        self.active = False
        self.activation_delay = 1.0  # seconds
        self.activation_timer = 0.0

    def draw(self, screen, camera_offset=(0,0)):
        cx, cy = camera_offset
        color = (255,0,0) if self.active else (128,128,128)
        pygame.draw.circle(screen, color, (int(self.x-cx), int(self.y-cy)), self.size)
        # Draw border
        pygame.draw.circle(screen, (0,0,0), (int(self.x-cx), int(self.y-cy)), self.size, 2)

class Pickup:
    def __init__(self, x, y, pickup_type='health', value=50):
        self.x = x
        self.y = y
        self.pickup_type = pickup_type
        self.value = value
        self.size = 10
        if pickup_type == 'health':
            self.color = (0, 255, 0)  # Green for health
        elif pickup_type == 'armor':
            self.color = (0, 128, 255)  # Blue for armor
        else:
            self.color = (255, 255, 255)  # White for unknown

    def draw(self, screen, camera_offset=(0,0)):
        cx, cy = camera_offset
        pygame.draw.circle(screen, self.color, (int(self.x-cx), int(self.y-cy)), self.size)
        # Draw cross inside
        line_size = self.size - 2
        pygame.draw.line(screen, (255,255,255), 
                        (int(self.x-cx-line_size), int(self.y-cy)), 
                        (int(self.x-cx+line_size), int(self.y-cy)), 2)
        pygame.draw.line(screen, (255,255,255), 
                        (int(self.x-cx), int(self.y-cy-line_size)), 
                        (int(self.x-cx), int(self.y-cy+line_size)), 2)
