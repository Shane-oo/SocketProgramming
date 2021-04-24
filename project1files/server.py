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

import selectors 
import types

def client_handler(key,mask,connection, address):
  host, port = address
  name = '{}:{}'.format(host, port)

  sock = key.fileobj
  data = key.data

  idnum = 0
  live_idnums = [idnum]

  sock.send(tiles.MessageWelcome(idnum).pack())
  sock.send(tiles.MessagePlayerJoined(name, idnum).pack())
  sock.send(tiles.MessageGameStart().pack())

  for _ in range(tiles.HAND_SIZE):
    tileid = tiles.get_random_tileid()
    sock.send(tiles.MessageAddTileToHand(tileid).pack())
    
  sock.send(tiles.MessagePlayerTurn(idnum).pack())
  
  board = tiles.Board()

  buffer = bytearray()

  while True:
    if mask & selectors.EVENT_WRITE:
      print('echoing', repr(data.outb), 'to', data.address)
      sock.send(tiles.MessagePlayerTurn(idnum).pack())
      
      
    if mask & selectors.EVENT_READ:
      chunk = sock.recv(4096)
      print("YYOOY")
      if not chunk:
        print('client {} disconnected'.format(address))
        sel.unregister(sock)
        sock.close()
        return

      buffer.extend(chunk)

      while True:
        msg, consumed = tiles.read_message_from_bytearray(buffer)
        if not consumed:
          break

        buffer = buffer[consumed:]

        print('received message {}'.format(msg))

        # sent by the player to put a tile onto the board (in all turns except
        # their second)
        if isinstance(msg, tiles.MessagePlaceTile):
          if board.set_tile(msg.x, msg.y, msg.tileid, msg.rotation, msg.idnum):
            # notify client that placement was successful
            sock.send(msg.pack())

            # check for token movement
            positionupdates, eliminated = board.do_player_movement(live_idnums)

            for msg in positionupdates:
              sock.send(msg.pack())
          
            if idnum in eliminated:
              sock.send(tiles.MessagePlayerEliminated(idnum).pack())
              return

            # pickup a new tile
            tileid = tiles.get_random_tileid()
            sock.send(tiles.MessageAddTileToHand(tileid).pack())

            # start next turn
            sock.send(tiles.MessagePlayerTurn(idnum).pack())

        # sent by the player in the second turn, to choose their token's
        # starting path
        elif isinstance(msg, tiles.MessageMoveToken):
          if not board.have_player_position(msg.idnum):
            if board.set_player_start_position(msg.idnum, msg.x, msg.y, msg.position):
              # check for token movement
              positionupdates, eliminated = board.do_player_movement(live_idnums)

              for msg in positionupdates:
                sock.send(msg.pack())
            
              if idnum in eliminated:
                sock.send(tiles.MessagePlayerEliminated(idnum).pack())
                return
            
              # start next turn
              sock.send(tiles.MessagePlayerTurn(idnum).pack())

sel = selectors.DefaultSelector()
# create a TCP/IP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# listen on all network interfaces
server_address = ('', 30020)
sock.bind(server_address)

print('listening on {}'.format(sock.getsockname()))

sock.listen(5)
#config the socket in non-blocking mode
sock.setblocking(False) 
#registers the socket to be monitired with sel.select() for the events
sel.register(sock,selectors.EVENT_READ,data = None)


def accept_wrapper(sock):
  global connection, client_address 
  connection,client_address = sock.accept()
  print('received connection from {}'.format(client_address))
  connection.setblocking(False)
  data = types.SimpleNamespace(address =client_address, inb = b'', outb = b'')
  events = selectors.EVENT_READ | selectors.EVENT_WRITE
  sel.register(connection, events,data = data)

#Event Loop
while True:
  #blocks until there are sockets ready for I/O
  #returns a list of (key,events) tuples for each socket
  events = sel.select(timeout=None)
  for key, mask in events:
    if key.data is None:
      #key.fileobj is the socket object
      accept_wrapper(key.fileobj)
    else:
      print("hi")
      #mask is an event mask of the operations that are ready
      #service_connection(key,mask)
      #client_handler(key, mask,connection,client_address)
  # handle each new connection independently
  #connection, client_address = sock.accept()
  #print('received connection from {}'.format(client_address))

  #client_handler(connection, client_address)