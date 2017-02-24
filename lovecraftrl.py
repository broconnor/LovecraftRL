import libtcodpy as libtcod
import math
import textwrap
import shelve

# Last change: Reworked random monster/item selection

# TODO: make '.' represent floors, '#' represent walls 
#			(play around with this)
#       add more variation to types of rooms (check out Crawl's vaults)
#       figure out background/floor/wall colors
#       modify FOV to support light sources other than the player
#       modify place_objects to support squads, fit theme, etc (EXP based?)
#       organize into 'gameloop.py', 'functions.py', 'classes.py', etc.
#			files
#       fix ai pathfinding to not get stuck on corners and to move around 
#			blocking objects
#       implement fleeing monsters (check out Dijkstra maps)
#       change messages to refer to 'you' instead of 'player'
#       add turn counter
#       rework item use so enemies can use them as well
#       add menu for choosing which item to pick up if many are on one tile
#       rework items to be theme-appropriate
#       add mouse support to menus (low priority)
#       organize inventory by item type
#       add support for multiple saves
#       figure out how to get '>' and '<' keys working for stairs
#		rework item randomization
#		adjust messages to have better grammar



#########################
####### CONSTANTS #######
#########################
# parameters for console window
SCREEN_WIDTH = 80
SCREEN_HEIGHT = 50
LIMIT_FPS = 20

# parameters for GUI
BAR_WIDTH = 20
PANEL_HEIGHT = 7
PANEL_Y = SCREEN_HEIGHT - PANEL_HEIGHT
MSG_X = BAR_WIDTH + 2
MSG_WIDTH = SCREEN_WIDTH - BAR_WIDTH - 2
MSG_HEIGHT = PANEL_HEIGHT - 1
INVENTORY_WIDTH = 50
LEVEL_SCREEN_WIDTH = 40
CHARACTER_SCREEN_WIDTH = 30

# parameters for map creation
MAP_WIDTH = 80
MAP_HEIGHT = 43

# parameters for map gen
ROOM_MAX_SIZE = 10
ROOM_MIN_SIZE = 6
MAX_ROOMS = 30

# parameters for FOV
FOV_ALGO = 0 # default FOV algorithm
FOV_LIGHT_WALLS = True
TORCH_RADIUS = 10

# parameters for items
HEAL_AMOUNT = 40
LIGHTNING_DAMAGE = 40
LIGHTNING_RANGE = 5
CONFUSE_NUM_TURNS = 10
CONFUSE_RANGE = 8
FIREBALL_DAMAGE = 25
FIREBALL_RADIUS = 3

# experience and level-ups
LEVEL_UP_BASE = 200
LEVEL_UP_FACTOR = 150

# colors for map tiles. later these will be based on current area
color_dark_wall = libtcod.Color(0, 0, 100)
color_light_wall = libtcod.Color(130, 110, 50)
color_dark_ground = libtcod.Color(50, 50, 150)
color_light_ground = libtcod.Color(200, 180, 50)



#########################
######## CLASSES ########
#########################
class Object:
	# generic object class for players, monsters, items, stairs, etc.
	# always represented by character on screen
	def __init__(self, x, y, char, name, color, blocks = False, 
				always_visible = False, fighter = None, ai = None, 
				item = None, equipment = None):
		self.name = name
		self.blocks = blocks
		self.x = x
		self.y = y
		self.char = char
		self.color = color
		self.always_visible = always_visible
		
		self.fighter = fighter
		if self.fighter:
			# Let the fighter component know who owns it
			self.fighter.owner = self
		
		self.ai = ai
		if self.ai:
			# Let the AI component know who owns it
			self.ai.owner = self
		
		self.item = item
		if self.item:
			# Let the Item component know who owns it
			self.item.owner = self

		self.equipment = equipment
		if self.equipment:
			# Let the equipment know who owns it
			self.equipment.owner = self
			# There must be an Item component for Equipment to work
			self.item = Item()
			self.item.owner = self

	def move(self, dx, dy):
		# move by given amount
		if not is_blocked(self.x + dx, self.y + dy):
			self.x += dx
			self.y += dy

	def draw(self):
		# set color and then draw the character that represents this object at its position
		if (libtcod.map_is_in_fov(fov_map, self.x, self.y) or
			(self.always_visible and map[self.x][self.y].explored)):
			libtcod.console_set_default_foreground(con, self.color)
			libtcod.console_put_char(con, self.x, self.y, self.char, libtcod.BKGND_NONE)

	def clear(self):
		# erase the character that represents this object
		libtcod.console_put_char(con, self.x, self.y, ' ', libtcod.BKGND_NONE)

	def move_towards(self, target_x, target_y):
		# draw vector from this object to the target
		dx = target_x - self.x
		dy = target_y - self.y
		distance = math.sqrt(dx ** 2 + dy ** 2)

		# normalize to length 1, then round and convert to integer so movement
		#  is restricted to the map grid
		dx = int(round(dx / distance))
		dy = int(round(dy / distance))
		self.move(dx, dy)

	def distance_to(self, other):
		# return distance to other object
		dx = other.x - self.x
		dy = other.y - self.y
		return math.sqrt(dx ** 2 + dy ** 2)

	def distance(self, x, y):
		# return the distance to some coordinates
		return math.sqrt((x - self.x) ** 2 + (y - self.y) ** 2)

	def send_to_back(self):
		global objects
		objects.remove(self)
		objects.insert(0, self)



class Tile:
	# a tile of the map and its properties
	def __init__(self, blocked, block_sight = None):
		self.blocked = blocked
		self.explored = False

		# by default, if a tile is blocked, it also blocks sight
		if block_sight is None: block_sight = blocked
		self.block_sight = block_sight



class Rect:
	# a rectangle on the map, used to characterize a room
	def __init__(self, x, y, w, h):
		self.x1 = x
		self.y1 = y
		self.x2 = x + w
		self.y2 = y + h

	def center(self):
		center_x = (self.x1 + self.x2) / 2
		center_y = (self.y1 + self.y2) / 2
		return (center_x, center_y)

	def intersect(self, other):
		# returns true if this rectangle intersects with another one
		return (self.x1 <= other.x2 and self.x2 >= other.x1 and
				self.y1 <= other.y2 and self.y2 >= other.y1)



class Fighter:
	# combat-related properties and methods (for monsters, players, NPCs, etc.)
	def __init__(self, hp, defense, power, xp, death_function = None):
		self.base_max_hp = hp
		self.hp = hp
		self.base_defense = defense
		self.base_power = power
		self.xp = xp
		self.death_function = death_function

	def take_damage(self, damage):
		# apply damage if possible
		if damage > 0:
			self.hp -= damage
		# check for death. if there's a death function, call it
		if self.hp <= 0:
			function = self.death_function
			if self.owner != player:
				# yield experience to the player
				player.fighter.xp += self.xp
			if function is not None:
				function(self.owner)

	def attack(self, target):
		# a simple formula for attack damage
		damage = self.power - target.fighter.defense

		if damage > 0:
			# make target take some damage
			message(self.owner.name.capitalize() + ' attacks ' + target.name + 
				' for ' + str(damage) + ' hit points.')
			target.fighter.take_damage(damage)
		else:
			message(self.owner.name.capitalize() + ' attacks ' + target.name +
				'but it has no effect!')

	def heal(self, amount):
		# heal by given amount, without going over max hp
		self.hp += amount
		if self.hp > self.max_hp:
			self.hp = self.max_hp

	@property
	def power(self):
		bonus = sum(equipment.power_bonus for equipment in 
					get_all_equipped(self.owner))
		return self.base_power + bonus
	
	@property
	def defense(self):
		bonus = sum(equipment.defense_bonus for equipment in
					get_all_equipped(self.owner))	
		return self.base_defense + bonus
	
	@property
	def max_hp(self):
		bonus = sum(equipment.max_hp_bonus for equipment in
					get_all_equipped(self.owner))
		return self.base_max_hp + bonus



class BasicMonster:
	# AI for a basic monster.
	def take_turn(self):
		monster = self.owner
		if libtcod.map_is_in_fov(fov_map, monster.x, monster.y):
			# line of sight is reciprocal. so take turn if player can see monster
			if monster.distance_to(player) >= 2:
				# move towards player if not adjacent
				monster.move_towards(player.x, player.y)
			elif player.fighter.hp > 0:
				monster.fighter.attack(player)



class ConfusedMonster:
	# AI for a temporarily confused monster (reverts to previous AI after a while)
	def __init__(self, old_ai, num_turns = CONFUSE_NUM_TURNS):
		self.old_ai = old_ai
		self.num_turns = num_turns

	def take_turn(self):
		if self.num_turns > 0:
			# if still confused, move in a random direction and decrease num_turns
			self.owner.move(libtcod.random_get_int(0, -1, 1), 
							libtcod.random_get_int(0, -1, 1))
			self.num_turns -= 1
		else:
			# restore the previous AI and delete this one
			self.owner.ai = self.old_ai
			message('The ' + self.owner.name + ' is no longer confused.')



class Item:
	# an item that can be picked up and used
	def __init__(self, use_function = None):
		self.use_function = use_function

	def pick_up(self):
		# add to player's inventory and remove from the map
		if len(inventory) >= 26:
			message('Your inventory is full, cannot pick up ' +
					self.owner.name + '.', libtcod.red)
		else:
			inventory.append(self.owner)
			objects.remove(self.owner)
			message('You pick up a ' + self.owner.name + '.',
					libtcod.green)
			# special case: equip something if slot is open
			equipment = self.owner.equipment
			if equipment and get_equipped_in_slot(equipment.slot) is None:
				equipment.equip()

	def use(self):
		# special case: if object is Equipment, 'use' is (un)equip
		if self.owner.equipment:
			self.owner.equipment.toggle_equip()
			return
		# just call the use_function if it's defined
		if self.use_function is None:
			message('The ' + self.owner.name + ' cannot be used.')
		else:
			if self.use_function() != 'cancelled':
				# destroy after use, unless cancelled
				inventory.remove(self.owner)

	def drop(self):
		# add to the map and remove from the player's inventory
		objects.append(self.owner)
		inventory.remove(self.owner)
		self.owner.x = player.x
		self.owner.y = player.y
		# special case: remove item, if it's equipment
		if self.owner.equipment:
			self.owner.equipment.unequip()
		message('You dropped a ' + self.owner.name + '.', libtcod.yellow)



class Equipment:
	# an object that can be equipped, yielding bonuses.
	def __init__(self, slot, power_bonus = 0, defense_bonus = 0,
				 max_hp_bonus = 0):
		self.slot = slot
		self.power_bonus = power_bonus
		self.defense_bonus = defense_bonus
		self.max_hp_bonus = max_hp_bonus
		self.is_equipped = False
	
	def toggle_equip(self):
		# toggle equip/unequip status
		if self.is_equipped:
			self.unequip()
		else:
			self.equip()
	
	def equip(self):
		# if the slot is already being used, unequip whatever is there
		old_equipment = get_equipped_in_slot(self.slot)
		if old_equipment is not None:
			old_equipment.unequip()

		# equip an object and show a message about it
		self.is_equipped = True
		message('Equipped ' + self.owner.name + ' on ' + self.slot + '.',
				libtcod.light_green)
	
	def unequip(self):
		# unequip an object and show a message about it
		if not self.is_equipped: return
		self.is_equipped = False
		message('Unequipped ' + self.owner.name + ' from ' + self.slot +
				'.', libtcod.light_yellow)



#########################
####### FUNCTIONS #######
#########################
def new_game():
	global player, inventory, game_msgs, game_state, dungeon_level

	# create object representing the player
	fighter_component = Fighter(hp = 100 , defense = 1, power = 2,
			  				    xp = 0,
				   			    death_function = player_death)
	player = Object(0, 0, '@', 'player', libtcod.white, blocks = True,
					fighter = fighter_component)

	player.level = 1

	# generate the map (but don't draw to screen yet) and
	#  initialize fov
	dungeon_level = 1
	make_map()
	initialize_fov()

	game_state = 'playing'
	inventory = []

	# create list of game message and their colors
	game_msgs = []

	# initial equipment: a dagger
	equipment_component = Equipment(slot = 'right hand', power_bonus = 2)
	obj = Object(0, 0, '-', 'dagger', libtcod.sky,
				 equipment = equipment_component)
	inventory.append(obj)
	equipment_component.equip()
	obj.always_visible = True

	# test welcome message
	message('Welcome to Hideous Truths!', libtcod.purple)



def initialize_fov():
	global fov_recompute, fov_map
	fov_recompute = True

	# make sure unexplored areas start black
	libtcod.console_clear(con)

	# create FOV map according to generated map
	fov_map = libtcod.map_new(MAP_WIDTH, MAP_HEIGHT)
	for y in range(MAP_HEIGHT):
		for x in range(MAP_WIDTH):
			libtcod.map_set_properties(fov_map, x, y, not map[x][y].block_sight, not map[x][y].blocked)



def play_game():
	global key, mouse

	player_action = None

	# get mouse and keyboard for input
	mouse = libtcod.Mouse()
	key = libtcod.Key()

	while not libtcod.console_is_window_closed():
		# render the screen
		libtcod.sys_check_for_event(libtcod.EVENT_KEY_PRESS | libtcod.EVENT_MOUSE,key, mouse)
		render_all()
		
		# update on-screen console
		libtcod.console_flush()
		check_level_up()

		# clear all objects (to avoid objects showing up in all of their previous
		#  positions once they've moved)
		for object in objects:
			object.clear()

		# handle keys and exit game if needed
		player_action = handle_keys()
		if player_action == 'exit':
			save_game()
			break

		# let monsters take their turn
		if game_state == 'playing' and player_action != 'didnt-take-turn':
			for object in objects:
				if object.ai:
					object.ai.take_turn()



def main_menu():
	img = libtcod.image_load('placeholder_menu_background.png')

	while not libtcod.console_is_window_closed():
		# show the background image, at twice the regular console resolution
		libtcod.image_blit_2x(img, 0, 0, 0)

		# show the game's title, and some credits
		libtcod.console_set_default_foreground(0, libtcod.violet)
		libtcod.console_print_ex(0, SCREEN_WIDTH/2, SCREEN_HEIGHT/2 - 4, 
			libtcod.BKGND_NONE, libtcod.CENTER, 'HIDEOUS TRUTHS')
		libtcod.console_print_ex(0, SCREEN_WIDTH/2, SCREEN_HEIGHT - 2, 
			libtcod.BKGND_NONE, libtcod.CENTER, "By Brian O'Connor")

		# show options and wait for the player's choice
		choice = menu('', ['Play a new game', 'Load a saved game', 'Quit'], 24)

		if choice == 0:
			# new_game
			new_game()
			play_game()
		elif choice == 1:
			# load last game
			try:
				load_game()
			except:
				msgbox('\n No saved game to load.\n', 24)
				continue
			play_game()
		elif choice == 2:
			# quit
			break



def save_game():
	# open a new empty shelve (possibily overwriting an old one) to write the game data
	save = shelve.open('savegame', 'n')
	# save each game state variable. don't save objects if they're also in a saved list
	save['map'] = map
	save['objects'] = objects
	# this avoids the problem mentioned above
	save['player_index'] = objects.index(player)
	save['stairs_index'] = objects.index(stairs)
	save['inventory'] = inventory
	save['game_msgs'] = game_msgs
	save['game_state'] = game_state
	save['dungeon_level'] = dungeon_level
	save.close()



def load_game():
	# open the previously saved shelve and load the game data
	global map, objects, player, inventory, game_msgs, game_state, stairs, dungeon_level

	save = shelve.open('savegame', 'r')
	map = save['map']
	objects = save['objects']
	player = objects[save['player_index']]
	stairs = objects[save['stairs_index']]
	inventory = save['inventory']
	game_msgs = save['game_msgs']
	game_state = save['game_state']
	dungeon_level = save['dungeon_level']
	save.close()

	initialize_fov()



def handle_keys():
	global fov_recompute
	global key

	# non-movement command keys
	if key.vk == libtcod.KEY_ENTER and key.lalt:
		# Alt+Enter: toggle fullscreen
		libtcod.console_set_fullscreen(not libtcod.console_is_fullscreen())
	elif key.vk == libtcod.KEY_ESCAPE:
		# Escape: exit game
		return 'exit'

	if game_state == 'playing':
		# movement keys, only allowed if game is being played
		if (key.vk == libtcod.KEY_UP or 
			key.vk == libtcod.KEY_KP8 or
			(key.vk == libtcod.KEY_CHAR and key.c == ord('k'))):
			# move up
			player_move_or_attack(0, -1)
			fov_recompute = True

		elif (key.vk == libtcod.KEY_DOWN or
			key.vk == libtcod.KEY_KP2 or
			(key.vk == libtcod.KEY_CHAR and key.c == ord('j'))):
			# move down
			player_move_or_attack(0, 1)
			fov_recompute = True

		elif (key.vk == libtcod.KEY_LEFT or
			key.vk == libtcod.KEY_KP4 or
			(key.vk == libtcod.KEY_CHAR and key.c == ord('h'))):
			# move left
			player_move_or_attack(-1, 0)
			fov_recompute = True

		elif (key.vk == libtcod.KEY_RIGHT or
			key.vk == libtcod.KEY_KP6 or
			(key.vk == libtcod.KEY_CHAR and key.c == ord('l'))):
			# move right
			player_move_or_attack(1, 0)
			fov_recompute = True

		elif (key.vk == libtcod.KEY_KP7 or
			(key.vk == libtcod.KEY_CHAR and key.c == ord('y'))):
			# move up-left
			player_move_or_attack(-1, -1)
			fov_recompute = True

		elif (key.vk == libtcod.KEY_KP9 or
			(key.vk == libtcod.KEY_CHAR and key.c == ord('u'))):
			# move up-right
			player_move_or_attack(1, -1)
			fov_recompute = True

		elif (key.vk == libtcod.KEY_KP1 or
			(key.vk == libtcod.KEY_CHAR and key.c == ord('b'))):
			# move down-left
			player_move_or_attack(-1, 1)
			fov_recompute = True

		elif (key.vk == libtcod.KEY_KP3 or
			(key.vk == libtcod.KEY_CHAR and key.c == ord('n'))):
			# move down-right
			player_move_or_attack(1, 1)
			fov_recompute = True

		elif (key.vk == libtcod.KEY_KP3 or
			(key.vk == libtcod.KEY_CHAR and key.c == ord('.'))):
			# do nothing
			pass

		else:
			# test for other keys
			key_char = chr(key.c)

			if key_char == ',':
				# pick up an item
				for object in objects:
					if object.x == player.x and object.y == player.y and object.item:
						object.item.pick_up()
						break

			if key_char == 'i':
				# show the inventory and select an item to use
				chosen_item = inventory_menu('Press the key next to an item ' +
					'to use it, or any other to cancel.\n')
				if chosen_item is not None:
					chosen_item.use()

			if key_char == 'd':
				# show the inventory and select an item to drop
				chosen_item = inventory_menu('Press the key next to an item ' +
					'to drop it, or any other to cancel.\n')
				if chosen_item is not None:
					chosen_item.drop()

			if key_char == 'c':
				# show stats
				level_up_xp = LEVEL_UP_BASE + player.level * LEVEL_UP_FACTOR
				msgbox('Character Information\n\nLevel: ' + str(player.level) + 
					'\nExperience: ' + str(player.fighter.xp) + ' / ' + str(level_up_xp) +
					'\nMaximum HP: ' + str(player.fighter.max_hp) +
					'\nAttack: ' + str(player.fighter.power) +
					'\nDefense: ' + str(player.fighter.defense), 
					CHARACTER_SCREEN_WIDTH)

			if key_char == '/':
				# go down stairs, if player is on them
				if stairs.x == player.x and stairs.y == player.y:
					next_level()

			return 'didnt-take-turn'



def make_map():
	global map, objects, stairs

	# create list of objects with just the player
	objects = [player]

	# fill map with "unblocked" tiles
	map = [[ Tile(True) 
		for y in range(MAP_HEIGHT) ]
			for x in range(MAP_WIDTH) ]

	rooms = []
	num_rooms = 0

	for r in range(MAX_ROOMS):
		# random width and height
		w = libtcod.random_get_int(0, ROOM_MIN_SIZE, ROOM_MAX_SIZE)
		h = libtcod.random_get_int(0, ROOM_MIN_SIZE, ROOM_MAX_SIZE)
		# random position within boundaries of map
		x = libtcod.random_get_int(0, 0, MAP_WIDTH - w - 1)
		y = libtcod.random_get_int(0, 0, MAP_HEIGHT - h - 1)

		new_room = Rect(x, y, w, h)
		failed = False
		for other_room in rooms:
			if new_room.intersect(other_room):
				failed = True
				break

		if not failed:
			# if the room doesn't intersect with any others, add it to the map
			create_room(new_room)
			# get center coordinates of new room
			(new_x, new_y) = new_room.center()

			if num_rooms == 0:
				# start the player in the center of the first room
				player.x = new_x
				player.y = new_y
			else:
				# after the first room, connect to the previous room by tunnel
				# get center of previous room
				(prev_x, prev_y) = rooms[num_rooms - 1].center()

				# randomly decide whether to move horizontally or vetically first
				if libtcod.random_get_int(0, 0, 1) == 1:
					# move horizontally first
					create_h_tunnel(prev_x, new_x, prev_y)
					create_v_tunnel(prev_y, new_y, new_x)
				else:
					# move vertically first
					create_v_tunnel(prev_y, new_y, prev_x)
					create_h_tunnel(prev_x, new_x, new_y)

			place_objects(new_room)
			rooms.append(new_room)
			num_rooms += 1

	# create stairs at the center of the last room
	stairs = Object(new_x, new_y, '>', 'stairs', libtcod.white, always_visible = True)
	objects.append(stairs)
	stairs.send_to_back()



def next_level():
	global dungeon_level
	# advance to the next level
	message('You descend deeper into the heart of the dungeon...', libtcod.red)
	dungeon_level += 1
	make_map()
	initialize_fov()



def render_all():
	global fov_recompute, fov_map

	if fov_recompute:
		# recompute FOV if needed (e.g. the player moved)
		fov_recompute = False
		libtcod.map_compute_fov(fov_map, player.x, player.y, TORCH_RADIUS, FOV_LIGHT_WALLS, FOV_ALGO)

	for y in range(MAP_HEIGHT):
		for x in range(MAP_WIDTH):
			wall = map[x][y].block_sight
			visible = libtcod.map_is_in_fov(fov_map, x, y)
			if not visible:
				if map[x][y].explored:
					# if tile is outside of player's FOV and has been explored
					if wall:
						libtcod.console_set_char_background(con, x, y, color_dark_wall, libtcod.BKGND_SET)
					else:
						libtcod.console_set_char_background(con, x, y, color_dark_ground, libtcod.BKGND_SET)
			else:
				# if tile is visible
				if wall:
					libtcod.console_set_char_background(con, x, y, color_light_wall, libtcod.BKGND_SET)
				else:
					libtcod.console_set_char_background(con, x, y, color_light_ground, libtcod.BKGND_SET)
				map[x][y].explored = True

	# draw all objects in the list, except player
	for object in objects:
		if object != player:
			object.draw()
	# then draw player so it shows up over corpses (and other items)
	player.draw()

	# prepare to render GUI panel
	libtcod.console_set_default_background(panel, libtcod.black)
	libtcod.console_clear(panel)

	# show the player's stats
	render_bar(1, 1, BAR_WIDTH, 'HP', player.fighter.hp, player.fighter.max_hp,
		libtcod.light_red, libtcod.darker_red)

	# show dungeon level
	libtcod.console_set_default_foreground(panel, libtcod.white)
	libtcod.console_print_ex(panel, 1, 3, libtcod.BKGND_NONE, libtcod.LEFT,
		'Dungeon level: ' + str(dungeon_level))

	# display names of objects under the mouse
	libtcod.console_set_default_foreground(panel, libtcod.light_gray)
	libtcod.console_print_ex(panel, 1, 0, libtcod.BKGND_NONE, libtcod.LEFT,
		get_names_under_mouse())

	# blit off-screen console to root console
	libtcod.console_blit(con, 0, 0, MAP_WIDTH, MAP_HEIGHT, 0, 0, 0)

	# blit the contents of "panel" to the root console
	libtcod.console_blit(panel, 0, 0, SCREEN_WIDTH, PANEL_HEIGHT, 0, 0, PANEL_Y)



def create_room(room):
	global map
	# go through the tiles in the rectangle and make them passable
	for x in range(room.x1 + 1, room.x2):
		for y in range(room.y1 + 1, room.y2):
			map[x][y].blocked = False
			map[x][y].block_sight = False



def create_h_tunnel(x1, x2, y):
	global map
	for x in range(min(x1, x2), max(x1, x2) + 1):
		map[x][y].blocked = False
		map[x][y].block_sight = False



def create_v_tunnel(y1, y2, x):
	global map
	for y in range(min(y1, y2), max(y1, y2) + 1):
		map[x][y].blocked = False
		map[x][y].block_sight = False



def place_objects(room):
	# maximum number of monster per room
	max_monsters = from_dungeon_level([[2, 1], [3, 4], [5, 6]])

	# chance of each monster
	monster_chances = {}
	monster_chances['orc'] = 80 # orc always shows up, min 80% chance
	monster_chances['troll'] = from_dungeon_level([[15, 3], [30, 5],
												   [60, 7]])
	
	# maximum number of items per room
	max_items = from_dungeon_level([[1, 1], [2, 4]])

	# chance of each item
	item_chances = {}
	item_chances['heal'] = 35 # healing potion always shows up, min 35%
	item_chances['lightning'] = from_dungeon_level([[25, 4]])
	item_chances['fireball'] = from_dungeon_level([[25, 6]])
	item_chances['confuse'] = from_dungeon_level([[10, 2]])
	item_chances['sword'] = from_dungeon_level([[5, 4]])
	item_chances['shield'] = from_dungeon_level([[15, 8]])

	
	# choose random number of monsters
	num_monsters = libtcod.random_get_int(0, 0, max_monsters)

	for i in range(num_monsters):
		# choose random spot for each monster
		x = libtcod.random_get_int(0, room.x1 + 1, room.x2 - 1)
		y = libtcod.random_get_int(0, room.y1 + 1, room.y2 - 1)


		if not is_blocked(x, y):
			choice = random_choice(monster_chances)
			if choice == 'orc':
				# 80% chance of creating an orc
				fighter_component = Fighter(hp = 20,
											defense = 0,
											power = 4,
											xp = 35,
											death_function = monster_death)
				ai_component = BasicMonster()
				monster = Object(x, y, 'o', 'orc',
								 libtcod.desaturated_green, 
							     blocks = True,
								 fighter = fighter_component,
								 ai = ai_component)
			else:
				# 20% chance of creating a troll
				fighter_component = Fighter(hp = 30,
											defense = 2,
											power = 8,
											xp = 100,
											death_function = monster_death)
				ai_component = BasicMonster()
				monster = Object(x, y, 'T', 'troll', libtcod.darker_green, 
							     blocks = True,
								 fighter = fighter_component,
								 ai = ai_component)

			objects.append(monster)

	# choose random number of items
	num_items = libtcod.random_get_int(0, 0, max_items)

	for i in range(num_items):
		# choose random spot for this item
		x = libtcod.random_get_int(0, room.x1 + 1, room.x2 - 1)
		y = libtcod.random_get_int(0, room.y1 + 1, room.y2 - 1)

		# only place it if tile is not blocked
		if not is_blocked(x, y):
			choice = random_choice(item_chances)
			if choice == 'heal':
				# 70% chance of creating a healing potion
				item_component = Item(use_function = cast_heal)
				item = Object(x, y, '!', 'healing potion', libtcod.violet, 
							  item = item_component, always_visible = True)
			elif choice == 'lightning':
				# 10% chance of creating a lightning bolt scroll
				item_component = Item(use_function = cast_lightning)
				item = Object(x, y, '?', 'scroll of lightning',
							  libtcod.light_yellow, 
							  item = item_component, always_visible = True)
			elif choice == 'fireball':
				# 10% chance of creating a fireball scroll
				item_component = Item(use_function = cast_fireball)
				item = Object(x, y, '?', 'scroll of fireball',
							  libtcod.light_yellow, 
							  item = item_component, always_visible = True)
			elif choice == 'sword':
				# create a sword
				equipment_component = Equipment(slot = 'right hand', 
												power_bonus = 2)
				item = Object(x, y, '/', 'sword', libtcod.sky,
							  equipment = equipment_component)
			elif choice == 'shield':
				# create a shield
				equipment_component = Equipment(slot = 'left hand',
												defense_bonus = 1)
				item = Object(x, y, '[', 'shield', libtcod.darker_orange,
							  equipment = equipment_component)
			else:
				# 15% chance of creating a confuse scroll
				item_component = Item(use_function = cast_confuse)
				item = Object(x, y, '?', 'scroll of confusion',
							  libtcod.light_yellow, 
							  item = item_component, always_visible = True)
			
			objects.append(item)
			item.send_to_back() # items appear below other objects



def is_blocked(x, y):
	# first test if map tile is blocked
	if map[x][y].blocked:
		return True

	# then check for any blocking objects
	for object in objects:
		if object.x == x and object.y == y and object.blocks:
			return True

	return False



def player_move_or_attack(dx, dy):
	global fov_recompute

	# coordinates the player is moving to/attacking
	x = player.x + dx
	y = player.y + dy

	# try to find an attackable object there
	target = None
	for object in objects:
		if object.x == x and object.y == y and object.fighter:
			target = object
			break

	# attack if target found, otherwise move
	if target is not None:
		player.fighter.attack(target)
	else:
		player.move(dx, dy)
		fov_recompute = True



def player_death(player):
	# game over
	global game_state
	message('You die...', libtcod.red)
	game_state = 'dead'

	# transform player into a corpse
	player.char = '%'
	player.color = libtcod.dark_red



def monster_death(monster):
	# transform it into a corpse. doesn't block; can't attack or move
	message('The ' + monster.name + ' dies! You gain ' + str(monster.fighter.xp) +
		' experience points.', libtcod.orange)
	monster.char = '%'
	monster.color = libtcod.dark_red
	monster.blocks = False
	monster.fighter = None
	monster.ai = None
	monster.name = 'remains of ' + monster.name
	monster.send_to_back()



def render_bar(x, y, total_width, name, value, maximum, bar_color, back_color):
	# render display bar for HP, EXP, etc. Calculate bar width first
	bar_width = int(float(value) / maximum * total_width)

	# render background next
	libtcod.console_set_default_background(panel, back_color)
	libtcod.console_rect(panel, x, y, total_width, 1, False, libtcod.BKGND_SCREEN)

	# now render the bar on top
	libtcod.console_set_default_background(panel, bar_color)
	if bar_width > 0:
		libtcod.console_rect(panel, x, y, bar_width, 1, False, libtcod.BKGND_SCREEN)

	# finally, some centered text with stat values
	libtcod.console_set_default_foreground(panel, libtcod.white)
	libtcod.console_print_ex(panel, x + total_width / 2, y, libtcod.BKGND_NONE,
		libtcod.CENTER, name + ': ' + str(value) + '/' + str(maximum))

	# print the game messages, one at a time
	y = 1
	for (line, color) in game_msgs:
		libtcod.console_set_default_foreground(panel, color)
		libtcod.console_print_ex(panel, MSG_X, y, libtcod.BKGND_NONE, 
			libtcod.LEFT, line)
		y += 1



def message(new_msg, color = libtcod.white):
	# split the message if necessary, among multiple lines
	new_msg_lines = textwrap.wrap(new_msg, MSG_WIDTH)

	for line in new_msg_lines:
		# if the buffer is full, remove the first line to make room for the new one
		if len(game_msgs) == MSG_HEIGHT:
			del game_msgs[0]
		# add the new line as a tuple of text and color
		game_msgs.append( (line, color))



def get_names_under_mouse():
	global mouse
	# return a string with the names of all objects under the mouse

	# get mouse's current coordinates
	(x, y) = (mouse.cx, mouse.cy)
	# create a list with the names of all objects in player's FOV at (x,y)
	names = [obj.name for obj in objects
		if obj.x == x and obj.y == y and libtcod.map_is_in_fov(fov_map, obj.x, obj.y)]

	# join the names into a string and return them with first letter capitalized
	names = ', '.join(names)
	return names.capitalize()



def closest_monster(max_range):
	# find closest enemy, up to a maximum range, and in the player's FOV
	closest_enemy = None
	closest_dist = max_range + 1 # start slightly outside of max range

	for object in objects:
		if (object.fighter and not object == player and 
			libtcod.map_is_in_fov(fov_map, object.x, object.y)):
			# calculate distance between object and player
			dist = player.distance_to(object)
			if dist < closest_dist:
				# it's closer, so remember it
				closest_enemy = object
				closest_dist = dist

	return closest_enemy




def menu(header, options, width):
	# if there are more options than letters, raise an error
	if len(options) > 26: raise ValueError('Cannot have a menu with more than 26 options.')

	#calculate total height for the header (after auto-wrap) and one line per option
	if header == '':
		header_height = 0
	else:
		header_height = libtcod.console_get_height_rect(con, 0, 0, width, SCREEN_HEIGHT, header)
	height = len(options) + header_height

	# create an off-screen console that represents the menu's window
	window = libtcod.console_new(width, height)

	# print the header, with auto-wrap
	libtcod.console_set_default_foreground(window, libtcod.white)
	libtcod.console_print_rect_ex(window, 0, 0, width, height, 
		libtcod.BKGND_NONE, libtcod.LEFT, header)

	# print all the options
	y = header_height
	letter_index = ord('a')
	for option_text in options:
		text = '(' + chr(letter_index) + ') ' + option_text
		libtcod.console_print_ex(window, 0, y, libtcod.BKGND_NONE, libtcod.LEFT, text)
		y += 1
		letter_index += 1

	# blit the contents of "window" to the root console
	x = SCREEN_WIDTH/2 - width/2
	y = SCREEN_HEIGHT/2 - height/2
	libtcod.console_blit(window, 0, 0, width, height, 0, x, y, 1.0, 0.7)

	# present the root console (i.e. the menu) and wait for a keypress
	libtcod.console_flush()
	key = libtcod.console_wait_for_keypress(True)

	if key.vk == libtcod.KEY_ENTER and key.lalt:
		# Alt+Enter: toggle fullscreen
		libtcod.console_set_fullscreen(not libtcod.console_is_fullscreen())

	# convert the ASCII code to an index; if it corresponds to an option, return it
	index = key.c - ord('a')
	if index >= 0 and index < len(options):
		return index
	return None



def inventory_menu(header):
	# show a menu with each inventory item as an option
	if len(inventory) == 0:
		options = ['Inventory is empty.']
	else:
		options = []
		for item in inventory:
			text = item.name
			# show additional information if item is equipped
			if item.equipment and item.equipment.is_equipped:
				text = text + ' (on ' + item.equipment.slot + ')'
			options.append(text)

	index = menu(header, options, INVENTORY_WIDTH)

	# if an item was chosen, return it
	if index is None or len(inventory) == 0:
		return None
	return inventory[index].item



def msgbox(text, width = 50):
	menu(text, [], width)



def cast_heal():
	# heal the player
	if player.fighter.hp == player.fighter.max_hp:
		message('You are already at full health.', libtcod.red)
		return 'cancelled'

	message('Your wounds start to feel better!', libtcod.light_violet)
	player.fighter.heal(HEAL_AMOUNT)



def cast_lightning():
	# find closest enemy (inside a max range) and damage it
	monster = closest_monster(LIGHTNING_RANGE)
	if monster is None:
		# no enemy found within maximum range
		message('No enemy is close enough to strike.', libtcod.red)
		return 'cancelled'

	# zap it 
	message('A lightning bolt strikes the ' + monster.name + ' with a loud thunder! ' +
		'The damage is ' + str(LIGHTNING_DAMAGE) + ' hit points.', libtcod.light_blue)
	monster.fighter.take_damage(LIGHTNING_DAMAGE)



def cast_confuse():
	# ask player for a target to confuse
	message('Left-click an enemy to confuse it, or right-click to cancel.', libtcod.light_cyan)
	monster = target_monster(CONFUSE_RANGE)
	if monster is None:
		return 'cancelled' 

	# temporarily replace the monster's AI with a confused one
	old_ai = monster.ai
	monster.ai = ConfusedMonster(old_ai)
	monster.ai.owner = monster # tell the new AI component who owns it
	message('The eyes of the ' + monster.name + ' look vacant as it starts to' +
			' stumble around!', libtcod.light_green)



def cast_fireball():
	# ask the player for a target tile to throw a fireball at
	message('Left-click a target tile for the fireball, or right-click to cancel.',
			libtcod.light_cyan)
	(x, y) = target_tile()
	if x is None:
		return 'cancelled'
	message('The fireball explodes, burning everything within ' + 
			str(FIREBALL_RADIUS) + ' tiles!', libtcod.orange)

	for obj in objects:
		# damage every fighter in range, including the player
		if obj.distance(x, y) <= FIREBALL_RADIUS and obj.fighter:
			message('The ' + obj.name + ' gets burned for ' + 
					str(FIREBALL_DAMAGE) + ' hit points.', libtcod.orange)
			obj.fighter.take_damage(FIREBALL_DAMAGE)



def target_tile(max_range = None):
	# return the position of a tile left-clicked in player's FOV
	global key, mouse
	while True:
		# render the screen. this erases the inventory and shows the names of objects under the mouse
		libtcod.console_flush()
		# this absorbs any key presses while targeting. without this, libtcod
		#  would process any key presses after targeting was done, resulting
		#  in unexpected behavior
		libtcod.sys_check_for_event(libtcod.EVENT_KEY_PRESS | libtcod.EVENT_MOUSE, key, mouse)
		render_all()

		(x, y) = (mouse.cx, mouse.cy)

		if (mouse.lbutton_pressed and libtcod.map_is_in_fov(fov_map, x, y) and
			(max_range is None or player.distance(x, y) <= max_range)):
			return (x, y)
		if mouse.rbutton_pressed or key.vk == libtcod.KEY_ESCAPE:
			# cancel if the player right-clicks or presses ESC
			return (None, None)



def target_monster(max_range = None):
	# returns a clicked monster inside FOV up to a range, or None if right-clicked
	while True:
		(x, y) = target_tile(max_range)
		if x is None:
			# player cancelled
			return None

		# return the first clicked monster, otherwise continue looping
		for obj in objects:
			if obj.x == x and obj.y == y and obj.fighter and obj != player:
				return obj



def check_level_up():
	# see if player's experience is enough to level-up
	level_up_xp = LEVEL_UP_BASE + player.level * LEVEL_UP_FACTOR
	if player.fighter.xp >= level_up_xp:
		# level up
		player.level += 1
		player.fighter.xp -= level_up_xp
		message('Your battle skills grow stronger! You reached level ' +
				str(player.level) + '!', libtcod.yellow)

		# choose a stat to increase
		choice = None
		while choice == None:
			# keep asking until a choice is made
			choice = menu('Level up! Choose a stat to raise:\n',
				['Constitution (+20 HP, from ' + str(player.fighter.max_hp) + ')',
				'Strength (+1 attack, from ' + str(player.fighter.power) + ')',
				'Agility (+1 defense, from ' + str(player.fighter.defense) + ')'],
				LEVEL_SCREEN_WIDTH)

		if choice == 0:
			player.fighter.base_max_hp += 20
		elif choice == 1:
			player.fighter.base_power += 1
		elif choice == 2:
			player.fighter.base_defense += 1

		# restore HP
		player.fighter.hp = player.fighter.max_hp



def random_choice_index(chances):
	# choose on option from list of chances, returning its index
	dice = libtcod.random_get_int(0, 1, sum(chances))

	# go through all chances, keeping the sum so far
	running_sum = 0
	choice = 0
	for w in chances:
		running_sum += w
		# see if the dice landed in the part that corresponds to this choice
		if dice <= running_sum:
			return choice
		choice += 1



def random_choice(chances_dict):
	# choose one option from dictionary of chances, returning its key
	chances = chances_dict.values()
	strings = chances_dict.keys()

	return strings[random_choice_index(chances)]



def from_dungeon_level(table):
	# returns a value that depends on level. the table specifies what value
	#  occurs after each level, default is 0.
	for (value, level) in reversed(table):
		if dungeon_level >= level:
			return value
	return 0



def get_equipped_in_slot(slot):
	# returns the equipment in a slot, or None if it's empty
	for obj in inventory:
		if (obj.equipment and obj.equipment.slot == slot and
			obj.equipment.is_equipped):
			return obj.equipment
	return None



def get_all_equipped(obj):
	# return a list of equipped items
	if obj == player:
		equipped_list = []
		for item in inventory:
			if item.equipment and item.equipment.is_equipped:
				equipped_list.append(item.equipment)
		return equipped_list
	else:
		return []



#########################
##### INITIALIZATION ####
#########################

monster_chances = {'orc': 80, 'troll': 20}
item_chances = {'heal': 70, 'lightning': 10, 'fireball': 10, 'confuse': 10}

# Set font
libtcod.console_set_custom_font('terminal12x12_gs_ro.png', libtcod.FONT_TYPE_GREYSCALE | libtcod.FONT_LAYOUT_ASCII_INROW)

# initialize window
libtcod.console_init_root(SCREEN_WIDTH, SCREEN_HEIGHT, 'LovecraftRL', False)

# set FPS to 20
libtcod.sys_set_fps(LIMIT_FPS)

# create off-screen console to draw on
con = libtcod.console_new(MAP_WIDTH, MAP_HEIGHT)

# create GUI panel
panel = libtcod.console_new(SCREEN_WIDTH, PANEL_HEIGHT)

# start the game by loading the main menu
main_menu()



