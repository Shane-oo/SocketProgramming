# CITS3002 2021 Assignment
# Shane Monck 22501734
# This file implements a basic server that allows a single client to play a
#
#
# server that adds all connected clients into a pool of players. 
# when countdown for a new game ends, the server
# will create a game with a random sample of those players (no more than
# tiles.PLAYER_LIMIT players will be in any one game). Players will take turns
# in an order determined by the server, continuing until the game is finished
# (there are less than two players remaining). When the game is finished, if
# there are enough players available the server will start a new game with a
# new selection of clients.
# Clients not selected to play the game become spectators and watch the playing clients.
# If a client joins mid game they become a spectator and their board is the caught up to the
# current playing game.
# If client does not make a move within 10s for their turn, a turn is done for the player.
import socket
import sys
import tiles


import threading
import time
from queue import Queue
import random
from random import randrange

#Three things being done simultaneously
NUMBER_OF_THREADS = 3
#Job no1 = listen for connection and accept
#job no2 = send commands and handle connections with clients
JOB_NUMBER =[1,2]
queue = Queue()
all_connections = []
all_addresses = []
in_game_clients = []
spectator_clients = []
buffer = None
board = None
clientCount = 0
gameOver = None
brd = [[0,0],[1,0],[2,0], [3,0],[4,0],[0,1],[1,1],[2,1],[3,1],
  [4,1],[0,2],[1,2],[2,2],[3,2],[4,2],[0,3],[1,3],[2,3],[3,3],[4,3],
  [0,4],[1,4],[2,4],[3,4],[4,4]]
class Player:
    def __init__(self,connection,idnum,tileHand,turns,currentPos):
        self.connection = connection
        self.idnum = idnum
        # Assign name to their raddr host and port name
        self.name = '{}:{}'.format(connection.getpeername()[0],connection.getpeername()[1])
        self.tileHand = tileHand
        self.turns = turns
        self.currentPos = currentPos

# this cool countdown function was taken from 
# https://www.geeksforgeeks.org/how-to-create-a-countdown-timer-using-python/
def countdown(t):
    while t:
        mins, secs = divmod(t, 60)
        timer = '{:02d}:{:02d}'.format(mins, secs)
        print("New game commences in",timer, end="\r")
        time.sleep(1)
        t -= 1
    print('New Game Starting')
# Remove any messages lingering from a previous game
# Will clear any messages sent from elimated players so that it does not carry over to the next game
def clear_buffer(client):
    client.connection.settimeout(0.1)
    try:
        chunk = client.connection.recv(4096)
        if chunk:
            # found messages from previous games
            client.connection.settimeout(None)
            chunk = 0
    except socket.timeout:
        # client had nothing to send
        client.connection.settimeout(None)

    return

#intialise the game for all clients and notify all clients of new joining client
def welcome_all_players():
    global board 
    #intialise the game for all clients
    for players in in_game_clients:
        if(is_socket_closed(players.connection)==True):
            #do not welcome client
            continue
        players.connection.send(tiles.MessageWelcome(players.idnum).pack())
        #Notify client that a new game is starting
        players.connection.send(tiles.MessageGameStart().pack())
        # Notify all already joined clients of new player name and idnum
        dontNotifyId = players.idnum
        for otherPlayers in in_game_clients:
            if(dontNotifyId != otherPlayers.idnum):
                if(is_socket_closed(otherPlayers.connection)==True):
                    #do not send anything to this other player as they arent there anymore
                    continue
                otherPlayers.connection.send(tiles.MessagePlayerJoined(players.name, players.idnum).pack())
        # Fill new players hand
        for _ in range(tiles.HAND_SIZE):
            tileid = tiles.get_random_tileid()
            players.connection.send(tiles.MessageAddTileToHand(tileid).pack())
            players.tileHand.append(tileid)
        
# intialise the game for all spectator clients and notify them of all in game clients
def welcome_spectators():
    global board 
    for players in spectator_clients:
        if(is_socket_closed(players.connection)==True):
            #do not welcome spectator
            continue
        #Notify client of their id
        players.connection.send(tiles.MessageWelcome(players.idnum).pack())
        #Notify client that a new game is starting
        players.connection.send(tiles.MessageGameStart().pack())
        # Notify spectator of playing clients
        for otherPlayers in in_game_clients:
                players.connection.send(tiles.MessagePlayerJoined(otherPlayers.name, otherPlayers.idnum).pack())

# function for when a spectator join mid game
def new_spectator(joinedInGameSpect):
    global board
    global live_idnums
    if(is_socket_closed(joinedInGameSpect.connection)==True):
            #do not welcome spectator
            return
    #let new client catch up to the game state
    #Notify client of their id
    joinedInGameSpect.connection.send(tiles.MessageWelcome(joinedInGameSpect.idnum).pack())
     # Notify spectator of playing clients
    for Players in gameOrder:
        joinedInGameSpect.connection.send(tiles.MessagePlayerJoined(Players.name, Players.idnum).pack())
        joinedInGameSpect.connection.send(tiles.MessagePlayerTurn(Players.idnum).pack())
    index = 0
    boardIds = []
    # Send what tiles are on the board
    for gamerIds in board.tileplaceids:
      if(board.tileplaceids[index]!=None):
        #save who has placed tiles on the board
        if gamerIds not in boardIds:
          boardIds.append(gamerIds)
        coords = index
        x = brd[coords][0]
        y = brd[coords][1]
        print("the x and y and id of tile on board",x,y,gamerIds)
        # get what tile is in the x and y position
        tileid,rotation = board.get_tile(x, y)[0],board.get_tile(x, y)[1]
        # send where tile is and what tile it is to spectator
        joinedInGameSpect.connection.send(tiles.MessagePlaceTile(board.tileplaceids[index], tileid, rotation, x, y).pack())
      index+=1
    # Send where tokens are and if they are elimated
    for Players in gameOrder:
      idnum = Players.idnum
      if(board.have_player_position(idnum)):
        # Get where token currently is
        x,y,position = board.get_player_position(idnum)[0],board.get_player_position(idnum)[1],board.get_player_position(idnum)[2]
        joinedInGameSpect.connection.send(tiles.MessageMoveToken(idnum, x, y, position).pack())
      if(idnum not in live_idnums and idnum in boardIds):
        # let joinedInGameSpect know of eliminated players
        joinedInGameSpect.connection.send(tiles.MessagePlayerEliminated(idnum).pack())

#notify all clients of whats been played
def send_to_all(message):
    global in_game_clients
    global spectator_clients
    global board 
    for players in in_game_clients:
        if(is_socket_closed(players.connection)==True):
            #do not notify player
            continue
        players.connection.send(message)
    for spectators in spectator_clients:
        #check to see if spectator is still in game
        if(is_socket_closed(spectators.connection)==True):
            #do not notify spectator
            continue
        spectators.connection.send(message)

#function to send to all of connected clients that may be in game or out of game
def send_to_all_connected(message):
    global board 
    for players in all_connections:
        if(is_socket_closed(players.connection)==True):
            #client is not connected
            continue
        players.connection.send(message)

# check elimations
def check_elimination(idnum,connection):
    global board
    global live_idnums
    eliminated = board.do_player_movement(live_idnums)[1]
    if idnum in eliminated:
      if(is_socket_closed(connection)==False):
        # Let connected client know they have been eliminated
        connection.send(tiles.MessagePlayerEliminated(idnum).pack())
        # remove player from in_game_clients and liveidnums 
        elimate_player(idnum)
        return True
    else:
        return False

def check_all_eliminations():
    global live_idnums
    global board 
    for idnums in live_idnums:
        for players in in_game_clients:
            if idnums == players.idnum:
                check_elimination(players.idnum, players.connection)

# Remove the player from the live game variables
def elimate_player(eliminatedIdnum):
    global live_idnums
    global in_game_clients
    global board 
    live_idnums = [aliveIds for aliveIds in live_idnums if aliveIds != eliminatedIdnum]
    print("live idnums after eliminated player ",live_idnums,"id",eliminatedIdnum,"eliminated")
    # remove from in_game_clients
    for player in in_game_clients:
        if(player.idnum == eliminatedIdnum):
            in_game_clients = [connectedPlayers for connectedPlayers in in_game_clients if connectedPlayers != player]
    # Let all clients know of elimated player
    send_to_all(tiles.MessagePlayerEliminated(eliminatedIdnum).pack())
    # eliminated player becomes a spectator
    for clients in all_connections:
        if clients not in in_game_clients and clients not in spectator_clients:
            spectator_clients.append(clients)
    
# enter bot_mode when socket timeout after no activity for 10s
def bot_mode(player):
    global live_idnums
    global board
    global buffer
    connection = player.connection
    idnum = player.idnum
    tileHand = player.tileHand
    turns = player.turns
    print("Player",idnum, "has had",turns," turns")
    # board border numbers
    borderSquares = [brd[0],brd[1],brd[2],brd[3],brd[4],brd[5],brd[9],brd[10],brd[14],brd[15],brd[19],brd[20],
    brd[21],brd[22],brd[23],brd[24]]
    print("Placing Tile/ or Selecting Token for timeout player")
    tilePlaced = False
    if(is_socket_closed(connection)==True):
        #do not play turn
        return
    # continue to attempt turn for client until the tile/token was successfully placed on board
    while(tilePlaced == False):
      if(turns!=1):
        position = [0,0]
        # choose random tile from players hand
        tileId = random.choice(tileHand)
        if(turns ==0):
          # place tile on board's border
          position = random.choice(borderSquares)
        elif(turns>1):
            # find x and y of tokens current position on board
            position[0] = board.get_player_position(idnum)[0]
            position[1] = board.get_player_position(idnum)[1]
            print("Player postion",position)
        x =  position[0]
        y =  position[1]
        rotation = random.randint(0,3)
        #returns false if position not allowed
        if(board.set_tile(x, y, tileId , rotation, idnum) == True):
          send_to_all(tiles.MessagePlaceTile(idnum, tileId, rotation, x, y).pack())
          tilePlaced = True
          player.tileHand.remove(tileId)
      else:
        #players second turn
        #select a token at random
        if not board.have_player_position(idnum):
            coords = board.tileplaceids.index(idnum)
            x = brd[coords][0]
            y = brd[coords][1]
            # choose a starting token position at random
            randPosition = random.randint(0, 7)
            #returns false if position not allowed
            if board.set_player_start_position(idnum, x, y, randPosition):
              print("placing starting tokent at",x,y,randPosition)
              send_to_all(tiles.MessageMoveToken(idnum, x, y, randPosition).pack())
              tilePlaced = True
      
    #positionupdates[0] returns MessageMoveToken messages describing all of the
    #updated token positions. send to all clients
    positionupdates = board.do_player_movement(live_idnums)[0]
    for messages in positionupdates:
        send_to_all(messages.pack())
    # check to see if players token has been eliminated
    if (check_elimination(idnum, connection)):
        #player has been eliminated
        return
    # need to update tile hand
    if(turns!=1):
        if(is_socket_closed(connection)==True):
            #do not play turn client is no longer there
            return
        #pick up a new tile
        tileid = tiles.get_random_tileid()
        player.tileHand.append(tileid)
        connection.send(tiles.MessageAddTileToHand(tileid).pack())
    player.turns +=1
    print("END OF  BOT_MODE")
# play clients turn 
def play_turn(player):
    global live_idnums
    global board
    global buffer
    connection = player.connection
    idnum = player.idnum
    tileHand = player.tileHand
    turns = player.turns
    if(is_socket_closed(connection)==True):
            #do not play turn
            return
    # let client know its their turn
    connection.send(tiles.MessagePlayerTurn(idnum).pack())
    # Timeout setting
    connection.settimeout(10)
    try:
        chunk = connection.recv(4096)
        if chunk:
            connection.settimeout(None)
            print("client responded in time")
    except socket.timeout:
      connection.settimeout(None)
      print("client inactive calling bot_mode")
      bot_mode(player)
      return
    buffer.extend(chunk)
    msg, consumed = tiles.read_message_from_bytearray(buffer)
    if not consumed:
        # unable to read a message
        # are they still there?
        is_socket_closed(connection)
        return
    buffer = buffer[consumed:]
    print('received message {}'.format(msg))
    # sent by the player to put a tile onto the board (in all turns except
    # their second)
    if isinstance(msg, tiles.MessagePlaceTile):
        if(msg.tileid  in player.tileHand):
            if board.set_tile(msg.x, msg.y, msg.tileid, msg.rotation, msg.idnum):
                print("titleId",msg.tileid)
                print("tilehand",player.tileHand)
                #notify clients that placement was successful
                send_to_all(msg.pack())
                #update whats in players hand
                player.tileHand.remove(msg.tileid)
                # check for token movement
                positionupdates = board.do_player_movement(live_idnums)[0]
                for msg in positionupdates:
                    send_to_all(msg.pack())
                # check to see if players token has been eliminated
                if (check_elimination(idnum, connection)):
                    #player has been eliminated
                    return
                # pickup a new tile
                tileid = tiles.get_random_tileid()
                connection.send(tiles.MessageAddTileToHand(tileid).pack())
                #update whats in players hand
                player.tileHand.append(tileid)
                player.turns +=1
            else:
                # turn was not valid 
                # client has to wait until its their next turn
                return
       
   # sent by the player in the second turn, to choose their token's
    # starting path
    elif isinstance(msg, tiles.MessageMoveToken):
        if not board.have_player_position(msg.idnum):
            if board.set_player_start_position(msg.idnum, msg.x, msg.y, msg.position):
                # check for token movement
                positionupdates = board.do_player_movement(live_idnums) [0]
                #player.currentPos = [msg.x,msg.y]
                for msg in positionupdates:
                    #connection.send(msg.pack())
                    send_to_all(msg.pack())
                # check to see if players token has been eliminated
                if (check_elimination(idnum, connection)):
                    #player has been eliminated
                    return
                player.turns +=1
            else:
                # turn was not valid 
                # client has to wait until its their next turn
                return
                
def client_handler():
    global gameOver
    global live_idnums
    global board 
    global buffer
    live_idnums = []
    #Clear any previous messages lingering from previous games
    for clients in all_connections:
            print("clearing buffer")
            clear_buffer(clients)
    #intialise live_idnums with all in_game_clients ids
    for players in in_game_clients:
        live_idnums.append(players.idnum)
    #check to see if multiplayer or single player game
    if(len(live_idnums)>1):
        multiplayer = True
    else:
        multiplayer = False
    # Add the four players into the game and give them their starting hand    
    welcome_all_players()
    # initalise spectator game for spectators
    welcome_spectators()

    board = tiles.Board()
    buffer = bytearray()
    #Start playing loop
    gameOver = False
    while (gameOver != True ):
        #sending a MessagePlayerTurn for everyone at the beginning of the game, 
        #so that all clients know about all players from the beginning (this will also establish the player colours)
        for players in in_game_clients:
            send_to_all(tiles.MessagePlayerTurn(players.idnum).pack())
        #check for eliminated players
        check_all_eliminations()
        if(len(live_idnums)>0):
            #game round loop
            for players in in_game_clients:
                # Check to see if player was eliminated by another player
                if (check_elimination(players.idnum, players.connection)):
                    #player has been eliminated
                    print("Player was eliminated by another player do not play turn")
                    continue
                #Do not play players turn if they have disconnected 
                if(players.idnum in live_idnums):
                    # Let clients know that a new turn has started
                    send_to_all(tiles.MessagePlayerTurn(players.idnum).pack())
                    # have player sned their turn message and update board accordingly
                    play_turn(players)
                check_all_eliminations()
                # all players have been elimated therefore game is over
                if(len(live_idnums)==0 or (multiplayer == True and len(live_idnums)==1)):
                    print("GAME OVER")
                    gameOver = True
                    break
        #its multiplayer and theres been a tie for winner at end of game
        else:
            #live_idnums would equal to 0 when in multiplayer mode when there is a tie
            print("GAME OVER")
            gameOver = True
            break
    if(len(all_connections)>0):
        # start countdown for new game
        send_to_all_connected(tiles.MessageCountdown().pack())
        countdown(10)
        assign_order()
    else:
        print("No more connected clients")
        return

# client has disconnected and needs to be removed from all variables
def complete_disconnection(badConnection):
    global all_connections
    global all_addresses 
    global spectator_clients
    #sever from server
    badConnection.close()
    #update connections list
    all_connections = [connectedClients for connectedClients in all_connections if connectedClients.connection != badConnection]
    #remove them from in_game_clients if they are a in game player
    for clients in in_game_clients:
        if clients.connection == badConnection:
            elimate_player(clients.idnum)
            send_to_all(tiles.MessagePlayerLeft(clients.idnum).pack())
    #remove them from spectator_clients if they are a spectator 
    spectator_clients = [connectedSpectators for connectedSpectators in spectator_clients if connectedSpectators.connection != badConnection]

# this function was made with help from Michael Petrov on:
# https://stackoverflow.com/questions/48024720/python-how-to-check-if-socket-is-still-connected
# if running on windows remove commented out line under win32 and comment out first data = line
#if return false client is still connected
#if return ture client is disconnected and should be removed from all variables and close its connection from server
def is_socket_closed(connection):
    client_disconnected = False
    #win32
    # connection.setblocking(0)
    try:
        # this will try to read bytes without blocking and also without removing them from buffer (peek only)
        data = connection.recv(16, socket.MSG_DONTWAIT | socket.MSG_PEEK)
        #win32
        # data = connection.rec(16,0)
        if not data:
            client_disconnected = True
        else:
            client_disconnected = False
    except BlockingIOError:
        client_disconnected = False  # socket is open and reading from it would block
    except ConnectionResetError:
        client_disconnected = True  # socket was closed for some other reason
    except  socket.error:
        client_disconnected = True
    #if client is connected client_disconnected would be false here
    if(client_disconnected == True):
        #run complete disconnection from server
        complete_disconnection(connection)
    #win32
    #if(client_disconnected ==False):
        #connection.setblocking(1)
    return client_disconnected

# Create a Socket 
def create_socket():
    try:
        global host
        global port
        global s
        host = ""
        port = 30020
        s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
    except socket.error as msg:
        print("Socket creation error: " + str(msg))

# Binding the socket and listening for connections
def bind_socket():
    try:
        global host
        global port
        global s
        print("Binding the Port: " + str(port))
        s.bind((host, port))
        s.listen(5)
        print('listening on {}'.format(s.getsockname()))
    except socket.error as msg:
        print("Socket Binding error" + str(msg) + "\n" + "Retrying...")
        bind_socket()


# Handling connection from multiple clients and saving to a list
# Closing previous connections when server.py file is restarted
def accepting_connections():
    global clientCount
    for c in all_connections:
        c.close()

    del all_connections[:]
    del all_addresses[:]

    while True:
        try:
            conn, address = s.accept()
            s.setblocking(1)  # prevents timeout
            all_connections.append(Player(conn, clientCount,[],0,[]))
            all_addresses.append(address)
           
            print("Connection has been established :" + address[0])
            clientCount +=1
            if(gameOver==False):
                print("client joined while game in progress")
                # place thread that handles in game joins in queue
                queue.put(3)
        except:
            print("Error accepting connections")
    


gameOrder = []
# Select only four connected clients to play a game
# assign a random turn order to connected clients number_connections
def assign_order():
    global in_game_clients
    global spectator_clients
    global gameOrder
    # check to see if clients are still connected
    for clients in all_connections:
        is_socket_closed(clients.connection)
    if(len(all_connections)==0):
        print("All clients disconnected")
        return -1
    #Clear in_game_clients and spectators for a new round
    in_game_clients.clear()
    spectator_clients.clear()
    gameOrder.clear()

    # decides a random turn order
    randomList = random.sample(range(len(all_connections)), len(all_connections))
    i = 0
    # Select players at random from all_connections
    while(i<tiles.PLAYER_LIMIT and i<len(all_connections)):
        in_game_clients.append(all_connections[randomList[i]])
        print("Selected player id =",in_game_clients[i].idnum)
        gameOrder.append(in_game_clients[i])
        i+=1
    for player in all_connections:
        # clear variables for repeated games
        player.turns = 0
        player.tileHand.clear()
        if player not in in_game_clients:
            spectator_clients.append(player)
            print("Spectator id =" ,player.idnum)
    # start game
    client_handler()
    

# Create worker threads
def create_workers():
    for _ in range(NUMBER_OF_THREADS):
        t = threading.Thread(target=work)
        t.daemon = True
        t.start()

# Do next job that is in the queue 
def work():
    while True:
        x = queue.get()
        if x == 1:
            create_socket()
            bind_socket()
            accepting_connections()
        if x == 2:
            #wait for players to join then start game
            countdown(10)
            assign_order()
            # if no players have joined countdown will start again until there is connected clients
            queue.put(2)
        if x ==3 :
            for clients in all_connections: 
                if clients not in spectator_clients and clients not in in_game_clients:
                    joinedInGameSpect = clients
                    spectator_clients.append(joinedInGameSpect)
                    new_spectator(joinedInGameSpect)
        queue.task_done()

def create_jobs():
    for x in JOB_NUMBER:
        queue.put(x)
    queue.join()
create_workers()
create_jobs()
