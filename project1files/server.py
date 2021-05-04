# CITS3002 2021 Assignment
#
# This file implements a basic server that allows a single client to play a
# single game with no other participants, and very little error checking.
#
# Any other clients that connect during this time will need to wait for the
# first client's game to complete.
#
# Your task will be to write a new server that adds all connected clients into
# a pool of players. When enough players are available (two or more), the server
# will create a game with a random sample of those players (no more than
# tiles.PLAYER_LIMIT players will be in any one game). Players will take turns
# in an order determined by the server, continuing until the game is finished
# (there are less than two players remaining). When the game is finished, if
# there are enough players available the server will start a new game with a
# new selection of clients.

import socket
import sys
import tiles


import threading
import time
from queue import Queue
import random


import select

#Two things being done simultaneously
NUMBER_OF_THREADS = 2
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



class Player:
    def __init__(self,connection,idnum):
        self.connection = connection
        self.idnum = idnum
        # Assign name to their raddr host and port name
        self.name = '{}:{}'.format(connection.getpeername()[0],connection.getpeername()[1])

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



#intialise the game for all clients and notify all clients of new joining client
def welcome_all_players():
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

def welcome_spectators():
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

#notify all clients of whats been played
def send_to_all(func):
    global in_game_clients
    global spectator_clients
    for players in in_game_clients:
        if(is_socket_closed(players.connection)==True):
            #do not notify player
            continue
        players.connection.send(func)
       
    for spectators in spectator_clients:
        #check to see if spectator is still in game
        if(is_socket_closed(spectators.connection)==True):
            #do not welcome spectator
            continue
        spectators.connection.send(func)
        

#function to send to all of connected clients that may be in game or out of game
def send_to_all_connected(func):
    for players in all_connections:
        if(is_socket_closed(players.connection)==True):
            #player is not connected
            continue
        players.connection.send(func)


def check_elimination(idnum,connection):
    global board
    global buffer
    global live_idnums
    eliminated = board.do_player_movement(live_idnums)[1]
    if idnum in eliminated:
                if(is_socket_closed(connection)==False):
                    # Let connected client know they have been eliminated
                    connection.send(tiles.MessagePlayerEliminated(idnum).pack())
                # remove player from in_game_clients and liveidnums 
                elimate_player(idnum)
                # Let all clients know of elimated player
                #moved this to elimate_player()
                #send_to_all(tiles.MessagePlayerEliminated(idnum).pack())
                return True
    else:
        return False

def check_all_eliminations():
    print("checking eliminations")
    global live_idnums
    for idnums in live_idnums:
        for players in in_game_clients:
            if idnums == players.idnum:
                check_elimination(players.idnum, players.connection)


# Remove the player from the live game variables
def elimate_player(eliminatedIdnum):
    global live_idnums
    global in_game_clients
    #print("remove live idnum:",live_idnums.remove(eliminatedIdnum))
    print("live_id before removal",live_idnums)
    live_idnums = [aliveIds for aliveIds in live_idnums if aliveIds != eliminatedIdnum]
    print("live_ids after removal",live_idnums)
    for player in in_game_clients:
        if(player.idnum == eliminatedIdnum):
            print("befor elim",in_game_clients)
            in_game_clients = [connectedPlayers for connectedPlayers in in_game_clients if connectedPlayers != player]
            print("Player " ,player.name," with id " ,player.idnum," has been eliminated")
            print("after",in_game_clients)
    # Let all clients know of elimated player
    send_to_all(tiles.MessagePlayerEliminated(eliminatedIdnum).pack())
            
def play_turn(connection,idnum):
    global live_idnums
    global board
    global buffer
    if(is_socket_closed(connection)==True):
            #do not play turn
            return
    connection.send(tiles.MessagePlayerTurn(idnum).pack())
    chunk = connection.recv(4096)
    buffer.extend(chunk)
    msg, consumed = tiles.read_message_from_bytearray(buffer)
    if not consumed:
        return
    buffer = buffer[consumed:]

    print('received message {}'.format(msg))
    # sent by the player to put a tile onto the board (in all turns except
    # their second)
    if isinstance(msg, tiles.MessagePlaceTile):
        if board.set_tile(msg.x, msg.y, msg.tileid, msg.rotation, msg.idnum):
            #notify client that placement was successful
            #connection.send(msg.pack())
            send_to_all(msg.pack())

            # check for token movement
            positionupdates = board.do_player_movement(live_idnums)[0]

            for msg in positionupdates:
                # connection.send(msg.pack())
                send_to_all(msg.pack())
            # check to see if players token has been eliminated
            if (check_elimination(idnum, connection)):
                #player has been eliminated
                return

            # pickup a new tile
            tileid = tiles.get_random_tileid()
            connection.send(tiles.MessageAddTileToHand(tileid).pack())
            # sent by the player in the second turn, to choose their token's
            # starting path
    elif isinstance(msg, tiles.MessageMoveToken):
        if not board.have_player_position(msg.idnum):
            if board.set_player_start_position(msg.idnum, msg.x, msg.y, msg.position):
                # check for token movement
                positionupdates = board.do_player_movement(live_idnums) [0]

                for msg in positionupdates:
                    #connection.send(msg.pack())
                    send_to_all(msg.pack())
                # check to see if players token has been eliminated
                if (check_elimination(idnum, connection)):
                    #player has been eliminated
                    return
                


def client_handler():
    global live_idnums
    live_idnums = []
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
    welcome_spectators()
    # must use globals
    global board 
    board = tiles.Board()
    global buffer
    buffer = bytearray()
    #Start playing loop

    gameOver = False
    count = 0
    while (gameOver != True ):
        print("LIVE_IDNUMS=",live_idnums)
        #check for eliminated players
        check_all_eliminations()
        if(len(live_idnums)>0):
            for players in in_game_clients:
                # Check to see if player was eliminated by another player
                if (check_elimination(players.idnum, players.connection)):
                    #player has been eliminated
                    print("Player was eliminated by another player do not play turn")
                    continue
                # Let clients know that a new turn has started
                send_to_all(tiles.MessagePlayerTurn(players.idnum).pack())
                if(players.idnum in live_idnums):
                    play_turn(players.connection,players.idnum)
                check_all_eliminations()
                # all players have been elimated therefore game is over
                if(len(live_idnums)==0 or (multiplayer == True and len(live_idnums)==1)):
                    print("GAME OVER PLAYER",live_idnums,"IS THE WINNER")
                    gameOver = True
                    break
        #its multiplayer and theres been a tie for winner at end of game
        else:
            #live_idnums would equal to 0 when in multiplayer mode when there is a tie
            print("GAME OVER ALL CLIENTS ELIMINATED (TIE FOR WINNER)")
            gameOver = True
            break
    print("OUT OF LOOP")
    if(len(all_connections)>0):
         # start countdown for new game
         #could add a check for disconnected here
        send_to_all_connected(tiles.MessageCountdown().pack())
        countdown(10)
        assign_order()
    else:
        print("No more connected clients")
        return

def complete_disconnection(badConnection):
    global all_connections
    global all_addresses #i never use all_addresses for anyting
    global spectator_clients
    #sever from server
    badConnection.close()
    #update connections list
    all_connections = [connectedClients for connectedClients in all_connections if connectedClients.connection != badConnection]
    
    #remove them from in_game_clients if they are a in game player
    for clients in in_game_clients:
        if clients.connection == badConnection:
            elimate_player(clients.idnum)
    #remove them from spectator_clients if they are a spectator 
    spectator_clients = [connectedSpectators for connectedSpectators in spectator_clients if connectedSpectators.connection != badConnection]

#https://stackoverflow.com/questions/48024720/python-how-to-check-if-socket-is-still-connected
#if return false client is still connected
#if return false client is disconnected and should be removed from all variables and closed its connection
def is_socket_closed(connection):
    client_disconnected = False
    try:
        # this will try to read bytes without blocking and also without removing them from buffer (peek only)
        data = connection.recv(16, socket.MSG_DONTWAIT | socket.MSG_PEEK)
        if len(data) == 0:
            client_disconnected = True
        else:
            client_disconnected = False
    except BlockingIOError:
        return  # socket is open and reading from it would block
    except ConnectionResetError:
        client_disconnected = True  # socket was closed for some other reason
    except Exception as e:
        #logger.exception("unexpected exception when checking if a socket is closed")
        client_disconnected = False
    #if connected client_disconnected would be false here
    if(client_disconnected ==True):
        #run complete disconnection from server
        complete_disconnection(connection)
    print("before is_cocket_closed return client_disconneted=",client_disconnected)
    return client_disconnected

# Create a Socket 
def create_socket():
    try:
        global host
        global port
        global s
        host = ""
        port = 30020
        s = socket.socket()

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
    for c in all_connections:
        c.close()

    del all_connections[:]
    del all_addresses[:]

    while True:
        try:
            conn, address = s.accept()
            s.setblocking(1)  # prevents timeout
            all_connections.append(Player(conn, len(all_connections)))
            all_addresses.append(address)

            print("Connection has been established :" + address[0])
           
        except:
            print("Error accepting connections")
    


def start_commands():
    while True:
        cmd = input('Input> ')
        if cmd == 'start':
            assign_order()
            
        else:
            print("Command not recognized")
            


# Select only four connected clients to play a game
# assign a random turn order to connected clients number_connections
def assign_order():
    # check to see if clients are still connected
    for clients in all_connections:
        is_socket_closed(clients.connection)
    print(all_connections)
    #i dont like this, when did i write this lol?
    if(len(all_connections)==0):
        print("All clients disconnected")
        return -1
    #Clear in_game_clients and spectators for a new round
    in_game_clients.clear()
    spectator_clients.clear()
    randomList = random.sample(range(len(all_connections)), len(all_connections))
    i = 0
    while(i<tiles.PLAYER_LIMIT and i<len(all_connections)):
        in_game_clients.append(all_connections[randomList[i]])
        print("Selected player =",in_game_clients[i].idnum)
        i+=1
    for player in all_connections:
        if player not in in_game_clients:
            spectator_clients.append(player)
            print("spectator =" ,player.idnum)

    client_handler()
    



# Create worker threads
def create_workers():
    for _ in range(NUMBER_OF_THREADS):
        t = threading.Thread(target=work)
        t.daemon = True
        t.start()

# Do next job that is in the queue (handle connections, send commands)
def work():
    while True:
        x = queue.get()
 
        if x == 1:
            create_socket()
            bind_socket()
            accepting_connections()
        if x == 2:
            print("-"*80+"\n" + "-"*15+"ENTER 'start' TO COMMENCE GAME AT ANY TIME"+"-"*20 +"\n"+"-"*80)
            start_commands()

        queue.task_done()


def create_jobs():
    for x in JOB_NUMBER:
        queue.put(x)

    queue.join()


create_workers()
create_jobs()
