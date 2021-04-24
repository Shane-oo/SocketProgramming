import socket
import select

server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server.setblocking(0)
server_address = ('localhost', 10000)
server.bind(server_address)
server.listen(5)

inputs = [server]
outputs = list()

live = True
while live:
    read_ready, write_ready, exceptions = select.select(inputs, outputs, [])

    for s in read_ready:
        # accept connection if server is read-ready
        if s is server:
            connection, client_address = s.accept()
            print ("server received connection: socket " + str(connection.fileno()))
            inputs.append(connection)
        # receive message if a connection is read-ready
        else:
            message = s.recv(1024)
            # handle shutdown signal
            if message == b"end":
                s.send(b"server shutting down")
                live = False
            print ("server received message: " + str(message))