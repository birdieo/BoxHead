import socket
import threading
import time
import random
import math
import pygame
from common.game_objects import Player, Enemy, Bullet, Wall, LootBox, get_random_weapon, Mine, Pickup
from common.network import NetworkProtocol, GameState

class GameServer:
    def __init__(self, host='0.0.0.0', port=5555):
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind((host, port))
        self.server.listen(3)  # Allow up to 3 players
        self.game_state = GameState()
        self.clients = {}
        self.running = True
        self.last_enemy_spawn = 0
        self.enemy_spawn_delay = 3  # seconds
        self.player_inputs = {}  # Store latest input for each player
        self.last_shot_times = {}  # For special weapons
        self.game_over = False
        self.wave = 1
        self.wave_in_progress = False
        self.wave_cooldown = 0
        self.zombies_to_spawn = 0

        # Initialize scores in game state
        self.game_state.scores = {}

        # Create some walls (simple maze)
        self.game_state.walls = [
            # Border walls
            Wall(0, 0, 800, 20),
            Wall(0, 580, 800, 20),
            Wall(0, 0, 20, 600),
            Wall(780, 0, 20, 600),

            # Maze walls
            Wall(100, 100, 600, 20),
            Wall(100, 200, 20, 300),
            Wall(200, 200, 400, 20),
            Wall(580, 200, 20, 200),
            Wall(200, 380, 400, 20),
            Wall(100, 480, 600, 20),
            Wall(300, 300, 20, 100),
            Wall(480, 300, 20, 100),
        ]
        self.game_state.lootboxes = []
        self.game_state.mines = []

        print(f"Server started on {host}:{port}")
        print("Waiting for players to connect...")

    def handle_client(self, client_socket, address):
        player_id = len(self.clients)
        player = Player(400, 300, player_id)  # Spawn in center
        self.game_state.players[player_id] = player
        self.clients[player_id] = client_socket
        self.player_inputs[player_id] = {'dx': 0, 'dy': 0, 'angle': 0, 'shoot': False, 'mouse_x': 0, 'mouse_y': 0}
        self.last_shot_times[player_id] = 0

        try:
            while self.running:
                message = NetworkProtocol.receive_message(client_socket)
                if message is None:
                    break
                if message['type'] == 'player_input':
                    if self.game_state.players[player_id].dead:
                        continue
                    data = message['data']
                    self.player_inputs[player_id] = data
                elif message['type'] == 'switch_weapon':
                    idx = message['data']['selected_weapon_index']
                    player = self.game_state.players.get(player_id)
                    if player and 0 <= idx < len(player.weapons):
                        player.selected_weapon_index = idx
                        NetworkProtocol.send_message(client_socket, {
                            'type': 'switch_weapon_ack',
                            'data': {'selected_weapon_index': idx}
                        })
                elif message['type'] == 'restart_game':
                    for p in self.game_state.players.values():
                        p.respawn()
                    self.game_over = False
                    self.wave = 1
                    self.wave_cooldown = 0
                    self.wave_in_progress = False
                    self.zombies_to_spawn = 0
                    self.game_state.scores = {}  # Reset scores on game restart
        except Exception as e:
            print(f"Error handling client {address}: {e}")
        finally:
            if player_id in self.game_state.players:
                del self.game_state.players[player_id]
            if player_id in self.clients:
                del self.clients[player_id]
            if player_id in self.player_inputs:
                del self.player_inputs[player_id]
            if player_id in self.last_shot_times:
                del self.last_shot_times[player_id]
            client_socket.close()

    def update_game_state(self):
        while self.running:
            # --- Fale zombie ---
            if not self.wave_in_progress and self.wave_cooldown <= 0:
                self.wave_in_progress = True
                self.zombies_to_spawn = 5 + self.wave
                self.spawned_this_wave = 0
            if self.wave_in_progress and self.zombies_to_spawn > 0:
                if len(self.game_state.enemies) < 10:
                    spawn_successful = False
                    attempts = 0
                    while not spawn_successful and attempts < 50:
                        x = random.randint(50, 750)
                        y = random.randint(50, 550)
                        enemy_type = random.randint(1, 4) # Include type 4
                        enemy_size = Enemy(x, y, enemy_type).size # Stwórz tymczasowego wroga, aby poznać rozmiar
                        enemy_rect = pygame.Rect(x - enemy_size, y - enemy_size, enemy_size*2, enemy_size*2)
                        
                        collides_with_wall = False
                        for wall in self.game_state.walls:
                            if wall.rect.colliderect(enemy_rect):
                                collides_with_wall = True
                                break
                                
                        if not collides_with_wall:
                            self.game_state.enemies.append(Enemy(x, y, enemy_type))
                            self.zombies_to_spawn -= 1
                            spawn_successful = True
                        
                        attempts += 1
                        
                    if not spawn_successful:
                         print("Warning: Could not find a valid spawn location for enemy after 50 attempts.")
            if self.wave_in_progress and self.zombies_to_spawn == 0 and len(self.game_state.enemies) == 0:
                self.wave_in_progress = False
                self.wave_cooldown = 5
                self.wave += 1
            if not self.wave_in_progress and self.wave_cooldown > 0:
                self.wave_cooldown -= 1/60
                if self.wave_cooldown < 0:
                    self.wave_cooldown = 0
            self.game_state.wave = self.wave
            self.game_state.wave_cooldown = self.wave_cooldown

            all_dead = True
            for player in self.game_state.players.values():
                if player.dead:
                    if player.respawn_timer > 0:
                        player.respawn_timer -= 1/60
                        if player.respawn_timer <= 0:
                            player.respawn()
                    continue
                all_dead = False
            if all_dead and len(self.game_state.players) > 0:
                self.game_over = True
            else:
                self.game_over = False
            self.game_state.game_over = self.game_over

            # Update player positions based on input
            for pid, player in self.game_state.players.items():
                if player.dead:
                    continue
                input_data = self.player_inputs.get(pid, {'dx': 0, 'dy': 0, 'angle': 0, 'shoot': False, 'mouse_x': player.x, 'mouse_y': player.y})
                dx = input_data['dx']
                dy = input_data['dy']
                angle = input_data['angle']
                shoot = input_data['shoot']
                mouse_x = input_data.get('mouse_x', player.x)
                mouse_y = input_data.get('mouse_y', player.y)

                # Normalize diagonal movement
                if dx != 0 and dy != 0:
                    dx *= 0.7071
                    dy *= 0.7071

                # Ruch gracza z kolizją ścian
                new_x = player.x + dx * player.speed
                new_y = player.y + dy * player.speed
                player_rect = pygame.Rect(new_x - player.size, new_y - player.size, player.size*2, player.size*2)
                collision = False
                for wall in self.game_state.walls:
                    if wall.rect.colliderect(player_rect):
                        collision = True
                        break
                if not collision:
                    player.x = new_x
                    player.y = new_y
                player.angle = angle

                # Special weapon logic
                weapon = getattr(player, 'current_weapon', None)
                now = time.time() * 1000
                if shoot and weapon:
                    if weapon.special_type == 'wall':
                        if now - self.last_shot_times.get(pid, 0) > weapon.fire_rate and player.ammo.get(weapon.name, 0) > 0:
                            self.last_shot_times[pid] = now
                            wall_w, wall_h = 40, 40
                            self.game_state.walls.append(Wall(mouse_x - wall_w//2, mouse_y - wall_h//2, wall_w, wall_h, is_player_wall=True))
                            player.ammo[weapon.name] -= 1 # Consume ammo for wall spawner

                    elif weapon.special_type == 'mine':
                        if now - self.last_shot_times.get(pid, 0) > weapon.fire_rate and player.ammo.get(weapon.name, 0) > 0:
                            self.last_shot_times[pid] = now
                            self.game_state.mines.append(Mine(player.x, player.y, pid, weapon.damage))
                            player.ammo[weapon.name] -= 1 # Consume ammo for mine placer

                    elif weapon.name == "Shotgun": # Handle Shotgun
                         if now - self.last_shot_times.get(pid, 0) > weapon.fire_rate and player.ammo.get(weapon.name, 0) > 0:
                             self.last_shot_times[pid] = now
                             player.ammo[weapon.name] -= 1 # Consume ammo
                             # Create multiple bullets with spread
                             spread_angle = 15 # Degrees total spread
                             num_bullets = 3
                             for i in range(num_bullets):
                                 angle_offset = (i - (num_bullets - 1) / 2) * (spread_angle / num_bullets)
                                 bullet_angle = player.angle + angle_offset
                                 # Use a different color for shotgun bullets to distinguish them
                                 shotgun_bullet = Bullet(player.x, player.y, bullet_angle, player.player_id, weapon)
                                 shotgun_bullet.color = (255, 165, 0) # Orange color for shotgun bullets
                                 self.game_state.bullets.append(shotgun_bullet)

                    else: # Handle regular bullets (Pistol, Weapon 2, Weapon 3)
                        if now - self.last_shot_times.get(pid, 0) > weapon.fire_rate and player.ammo.get(weapon.name, 0) > 0: # Check ammo for regular guns too
                            self.last_shot_times[pid] = now
                            player.ammo[weapon.name] -= 1 # Consume ammo
                            bullet = Bullet(player.x, player.y, player.angle, player.player_id, weapon)
                            self.game_state.bullets.append(bullet)

            # Update bullets
            for bullet in self.game_state.bullets[:]:
                bullet.update()
                if bullet.lifetime <= 0:
                    self.game_state.bullets.remove(bullet)
                    continue

                # Check bullet collisions with walls
                for wall in self.game_state.walls[:]:
                    if wall.rect.collidepoint(bullet.x, bullet.y):
                        wall.health -= bullet.damage
                        if wall.health <= 0:
                            self.game_state.walls.remove(wall)
                        if bullet in self.game_state.bullets:
                            self.game_state.bullets.remove(bullet)
                        break

                # Check bullet collisions with enemies
                for enemy in self.game_state.enemies[:]:
                    # Pociski graczy (player_id >= 0) kolidują z wrogami
                    if bullet.player_id >= 0 and ((bullet.x - enemy.x) ** 2 + (bullet.y - enemy.y) ** 2) ** 0.5 < enemy.size:
                        # Damage the enemy
                        enemy.health -= bullet.damage if hasattr(bullet, 'damage') else 25
                        if enemy.health <= 0:
                            # Award points based on enemy type
                            points = {
                                1: 100,  # Basic zombie
                                2: 200,  # Stronger zombie
                                3: 500,  # Boss zombie
                                4: 300   # Shooter zombie
                            }.get(enemy.type, 100)
                            
                            # Initialize score for player if not exists
                            if bullet.player_id not in self.game_state.scores:
                                self.game_state.scores[bullet.player_id] = 0
                            
                            # Add points to player's score
                            self.game_state.scores[bullet.player_id] += points
                            
                            # Chance to drop health or armor (30% total: 20% health, 10% armor)
                            drop_roll = random.random()
                            if drop_roll < 0.2:  # 20% chance for health
                                self.game_state.pickups.append(Pickup(enemy.x, enemy.y, 'health', 50))
                            elif drop_roll < 0.3:  # 10% chance for armor
                                self.game_state.pickups.append(Pickup(enemy.x, enemy.y, 'armor', 100))
                            else:  # 70% chance for weapon
                                self.game_state.lootboxes.append(LootBox(enemy.x, enemy.y))
                            
                            self.game_state.enemies.remove(enemy)
                        # Remove the bullet
                        if bullet in self.game_state.bullets:
                            self.game_state.bullets.remove(bullet)
                            break

                # Check bullet collisions with players
                for player in self.game_state.players.values():
                    # Pociski wrogów (player_id == -1) kolidują z graczami
                    # Pociski graczy (player_id >= 0) nie kolidują z własnymi graczami (sprawdzane przez player.player_id != bullet.player_id)
                    if bullet.player_id == -1 or (bullet.player_id >= 0 and player.player_id != bullet.player_id):
                        if not player.dead:
                            if ((bullet.x - player.x) ** 2 + (bullet.y - player.y) ** 2) ** 0.5 < player.size:
                                # Gracz otrzymał obrażenia od pocisku wroga lub innego gracza
                                player.health -= bullet.damage # Użyj obrażeń pocisku
                                if player.health <= 0 and not player.dead:
                                    player.kill()
                                if bullet in self.game_state.bullets:
                                    self.game_state.bullets.remove(bullet)
                                break # Pocisk trafił w gracza, usuń pocisk

            # Player picks up items
            for player in self.game_state.players.values():
                if player.dead:
                    continue
                
                # Check for pickup collisions
                for pickup in self.game_state.pickups[:]:
                    if ((player.x - pickup.x) ** 2 + (player.y - pickup.y) ** 2) ** 0.5 < player.size + pickup.size:
                        if pickup.pickup_type == 'health':
                            player.add_health(pickup.value)
                        else:  # armor
                            player.add_armor(pickup.value)
                        self.game_state.pickups.remove(pickup)

                # Check for lootbox collisions
                for lootbox in self.game_state.lootboxes[:]:
                    if ((player.x - lootbox.x) ** 2 + (player.y - lootbox.y) ** 2) ** 0.5 < player.size + lootbox.size:
                        player.add_weapon(lootbox.weapon)
                        self.game_state.lootboxes.remove(lootbox)

            # Update mines and check for explosions
            for mine in self.game_state.mines[:]:
                if not mine.active:
                    continue
                
                exploded = False
                for enemy in self.game_state.enemies[:]:
                    if ((mine.x - enemy.x) ** 2 + (mine.y - enemy.y) ** 2) ** 0.5 < mine.size + enemy.size:
                        # Mine explodes on contact
                        exploded = True
                        break # Explode only once per enemy contact

                if exploded:
                    # Apply blast damage to all enemies within radius
                    blast_radius = 100 # Adjust as needed
                    for enemy in self.game_state.enemies[:]:
                        if ((mine.x - enemy.x) ** 2 + (mine.y - enemy.y) ** 2) ** 0.5 < blast_radius:
                             enemy.health -= mine.damage # Use mine's damage for blast
                             if enemy.health <= 0:
                                # Award points for mine kills
                                points = {
                                    1: 150,  # Extra points for mine kills
                                    2: 300,
                                    3: 750,
                                    4: 450
                                }.get(enemy.type, 150)
                                
                                # Initialize score for player if not exists
                                if mine.owner_id not in self.game_state.scores:
                                    self.game_state.scores[mine.owner_id] = 0
                                
                                # Add points to player's score
                                self.game_state.scores[mine.owner_id] += points
                                
                                self.game_state.lootboxes.append(LootBox(enemy.x, enemy.y)) # Drop loot on blast kill
                                self.game_state.enemies.remove(enemy) # Usuń wroga po zabiciu przez minę
                    mine.active = False # Deactivate mine after explosion
            # Remove inactive mines
            self.game_state.mines = [m for m in self.game_state.mines if m.active]

            # Update enemy movement and actions
            dt = 1/60 # Czas ramki w sekundach
            now = time.time() * 1000 # Aktualny czas w milisekundach
            for enemy in self.game_state.enemies[:]: # Iterate over a copy in case enemies are removed
                alive_players = [p for p in self.game_state.players.values() if not p.dead]
                target_player = None
                
                # Docelowy wektor ruchu i kąt (w stopniach)
                target_dx = target_dy = 0
                target_angle_deg = enemy.look_angle

                if alive_players:
                    # Szukaj najbliższego żywego gracza
                    target_player = min(alive_players, key=lambda p: ((p.x - enemy.x) ** 2 + (p.y - enemy.y) ** 2) ** 0.5)
                    # Jeśli to strzelający wróg i jest w zasięgu strzału (np. 300 pikseli), zatrzymaj się i strzel zamiast podchodzić
                    if enemy._is_shooter and ((enemy.x - target_player.x) ** 2 + (enemy.y - target_player.y) ** 2) ** 0.5 < 300:
                         target_dx, target_dy = (0, 0) # Zatrzymaj ruch
                         target_angle_deg = math.degrees(math.atan2(target_player.y - enemy.y, target_player.x - enemy.x)) # Patrz na gracza
                         # Logika strzelania dla wroga
                         if now - enemy._last_shot > enemy._fire_rate:
                              enemy._last_shot = now
                              # Stwórz pocisk wroga
                              enemy_bullet = Bullet(enemy.x, enemy.y, target_angle_deg, -1) # -1 player_id for enemy bullet
                              enemy_bullet.damage = enemy._bullet_damage
                              enemy_bullet.speed = enemy._bullet_speed
                              enemy_bullet.color = (255, 0, 0) # Czerwone pociski wroga
                              self.game_state.bullets.append(enemy_bullet)
                    else:
                         # Jeśli nie strzelający wróg, lub poza zasięgiem, biegnij do gracza
                         angle = math.atan2(target_player.y - enemy.y, target_player.x - enemy.x)
                         target_dx = math.cos(angle) * enemy.speed
                         target_dy = math.sin(angle) * enemy.speed
                         target_angle_deg = math.degrees(angle)
                else:
                    # Jeśli nie ma żywych graczy, patroluj
                    dx, dy = enemy.get_patrol_vector(dt)
                    target_dx = dx * enemy.speed
                    target_dy = dy * enemy.speed
                    target_angle_deg = math.degrees(math.atan2(dy, dx))

                enemy.look_angle = target_angle_deg # Ustaw kąt patrzenia dla synchronizacji

                # Wektor ruchu na tę klatkę
                move_vector = (target_dx * dt, target_dy * dt)

                # Podział ruchu na X i Y i sprawdź kolizje oddzielnie
                original_x, original_y = enemy.x, enemy.y
                moved_x = False
                moved_y = False

                # Próba ruchu w X
                attempt_x = enemy.x + move_vector[0]
                # Sprawdź kolizję z przyszłą pozycją w X
                enemy_rect_x = pygame.Rect(attempt_x - enemy.size, enemy.y - enemy.size, enemy.size*2, enemy.size*2)
                collision_x = False
                hit_wall_x = None
                for wall in self.game_state.walls:
                    if wall.rect.colliderect(enemy_rect_x):
                        collision_x = True
                        hit_wall_x = wall # Zapamiętaj uderzoną ścianę
                        break

                if collision_x:
                    enemy.x = original_x # Cofnij ruch w X jeśli była kolizja
                    # Jeśli kolizja w X, zadaj obrażenia ścianie i spróbuj ruchu w Y (wzdłuż ściany)
                    if hit_wall_x and hasattr(enemy, 'damage') and enemy.damage > 0:
                         hit_wall_x.health -= enemy.damage # Zadaj obrażenia ścianie

                    if target_player: # Tylko jeśli ścigamy gracza
                         # Określ kierunek ruchu wzdłuż ściany (prostopadle do target_angle)
                         wall_follow_angle_rad = math.radians(target_angle_deg) + math.pi / 2 * (1 if random.random() > 0.5 else -1) # Losowo w lewo lub w prawo
                         # Sprawdź, który kierunek (wall_follow_angle_rad lub wall_follow_angle_rad + pi) jest bliżej celu Y
                         angle_towards_player_y = math.atan2(target_player.y - enemy.y, target_player.x - enemy.x) # Kąt do gracza

                         angle1_diff = abs((wall_follow_angle_rad - angle_towards_player_y + math.pi) % (2 * math.pi) - math.pi)
                         angle2_diff = abs((wall_follow_angle_rad + math.pi - angle_towards_player_y + math.pi) % (2 * math.pi) - math.pi)

                         best_wall_follow_angle_rad = wall_follow_angle_rad if angle1_diff < angle2_diff else wall_follow_angle_rad + math.pi
                         
                         wall_follow_distance = enemy.speed * dt # Pełny krok wzdłuż ściany
                         attempt_y_wall_follow = original_y + math.sin(best_wall_follow_angle_rad) * wall_follow_distance
                         
                         enemy_rect_y_wall_follow = pygame.Rect(enemy.x - enemy.size, attempt_y_wall_follow - enemy.size, enemy.size*2, enemy.size*2)
                         collides_with_wall_follow = False
                         for wall_follow in self.game_state.walls:
                              if wall_follow.rect.colliderect(enemy_rect_y_wall_follow):
                                   collides_with_wall_follow = True
                                   break
                         if not collides_with_wall_follow:
                              enemy.y = attempt_y_wall_follow
                              moved_y = True # Mark as moved in Y due to wall following

                else:
                     enemy.x = attempt_x # Zastosuj ruch w X jeśli nie było kolizji
                     moved_x = True
                
                # Próba ruchu w Y (tylko jeśli nie było kolizji w X lub jeśli kolizja w X nie zablokowała całkowicie ruchu w Y)
                # Jeśli ruch w Y nie był spowodowany kolizją w X
                if not moved_y:
                    attempt_y = enemy.y + move_vector[1]
                    # Sprawdź kolizję z przyszłą pozycją w Y
                    enemy_rect_y = pygame.Rect(enemy.x - enemy.size, attempt_y - enemy.size, enemy.size*2, enemy.size*2)
                    collision_y = False
                    hit_wall_y = None
                    for wall in self.game_state.walls:
                         if wall.rect.colliderect(enemy_rect_y):
                             collision_y = True
                             hit_wall_y = wall # Zapamiętaj uderzoną ścianę
                             break

                    if collision_y:
                         enemy.y = original_y # Cofnij ruch w Y jeśli była kolizja
                         # Jeśli kolizja w Y, zadaj obrażenia ścianie i spróbuj ruchu w X (wzdłuż ściany)
                         if hit_wall_y and hasattr(enemy, 'damage') and enemy.damage > 0:
                              hit_wall_y.health -= enemy.damage # Zadaj obrażenia ścianie

                         if target_player: # Tylko jeśli ścigamy gracza
                              # Określ kierunek ruchu wzdłuż ściany (prostopadle do target_angle)
                              wall_follow_angle_rad = math.radians(target_angle_deg) + math.pi / 2 * (1 if random.random() > 0.5 else -1) # Losowo w lewo lub w prawo
                              # Sprawdź, który kierunek (wall_follow_angle_rad lub wall_follow_angle_rad + pi) jest bliżej celu X
                              angle_towards_player_x = math.atan2(target_player.y - enemy.y, target_player.x - enemy.x) # Kąt do gracza
                              # Dla X patrzymy na cosinus kąta (ruch w poziomie)
                              cos1 = math.cos(wall_follow_angle_rad)
                              cos2 = math.cos(wall_follow_angle_rad + math.pi)
                              cos_target = math.cos(math.radians(target_angle_deg)) # Użyj kąta ruchu, nie tylko X

                              # Wybierz kierunek wzdłuż ściany, który ma cosinus najbliższy cosinusowi ruchu
                              best_wall_follow_angle_rad = wall_follow_angle_rad if abs(cos1 - cos_target) < abs(cos2 - cos_target) else wall_follow_angle_rad + math.pi

                              wall_follow_distance = enemy.speed * dt # Pełny krok wzdłuż ściany
                              attempt_x_wall_follow = original_x + math.cos(best_wall_follow_angle_rad) * wall_follow_distance

                              enemy_rect_x_wall_follow = pygame.Rect(attempt_x_wall_follow - enemy.size, enemy.y - enemy.size, enemy.size*2, enemy.size*2)
                              collides_with_wall_follow = False
                              for wall_follow in self.game_state.walls:
                                  if wall_follow.rect.colliderect(enemy_rect_x_wall_follow):
                                       collides_with_wall_follow = True
                                       break
                              if not collides_with_wall_follow:
                                   enemy.x = attempt_x_wall_follow
                                   moved_x = True # Mark as moved in X due to wall following
                                   break
                    else:
                         enemy.y = attempt_y # Zastosuj ruch w Y jeśli nie było kolizji
                         moved_y = True

                # Kolizja zombie z graczem (zadawanie obrażeń)
                if target_player and ((enemy.x - target_player.x) ** 2 + (enemy.y - target_player.y) ** 2) ** 0.5 < enemy.size + target_player.size:
                    target_player.health -= enemy.damage
                    if target_player.health <= 0 and not target_player.dead:
                        target_player.kill()

            # Usuń zniszczone ściany po przetworzeniu wszystkich wrogów
            self.game_state.walls = [wall for wall in self.game_state.walls if wall.health > 0]

            time.sleep(1/60)  # 60 FPS

    def broadcast_game_state(self):
        while self.running:
            for client in self.clients.values():
                try:
                    NetworkProtocol.send_message(client, {
                        'type': 'game_state',
                        'data': self.game_state.to_dict()
                    })
                except:
                    pass
            time.sleep(1/30)  # 30 FPS for network updates

    def run(self):
        # Start game state update thread
        update_thread = threading.Thread(target=self.update_game_state)
        update_thread.start()

        # Start broadcast thread
        broadcast_thread = threading.Thread(target=self.broadcast_game_state)
        broadcast_thread.start()

        try:
            while self.running:
                client_socket, address = self.server.accept()
                print(f"New connection from {address}")
                client_thread = threading.Thread(target=self.handle_client,
                                              args=(client_socket, address))
                client_thread.start()
        except KeyboardInterrupt:
            self.running = False
            self.server.close()

if __name__ == "__main__":
    server = GameServer()
    server.run() 