import socket
server_address = ('localhost', 10000)

client1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

# wait for server to start
while client1.connect_ex(server_address) != 0:
    pass
client1.send(b"client 1 hello")

client2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client2.connect(server_address)
client2.send(b"client 2 hello")

end = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
end.connect(server_address)
end.send(b"end")