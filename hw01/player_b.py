# player_b.py
# UDP Server and TCP Client

import socket

def main():
    UDP_IP = ''
    UDP_PORT = 18324 

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))

    print(f"Player B is waiting for game invitations on port {UDP_PORT}...")

    while True:
        data, addr = sock.recvfrom(1024)
        message = data.decode()
        print(f"Received message from {addr}: {message}")

        if message == "ARE_YOU_AVAILABLE":
            sock.sendto(b"AVAILABLE", addr)
            print(f"Sent availability response to {addr}")
        elif message == "GAME_INVITATION":
            response = input("Do you want to accept the invitation? (y/N): ").strip().lower()
            if response == 'y':
                sock.sendto(b"ACCEPTED", addr)
                print("Invitation accepted, waiting for TCP port info...")

                data, addr = sock.recvfrom(1024)
                tcp_port_info = data.decode()
                TCP_PORT = int(tcp_port_info)
                print(f"Received TCP port info from Player A: {TCP_PORT}")

                play_game(addr[0], TCP_PORT)
                print("Game finished. Returning to wait for new invitations.")
            else:
                sock.sendto(b"DECLINED", addr)
                print("Invitation declined, waiting for new invitations...")
        else:
            pass

def play_game(player_a_ip, tcp_port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((player_a_ip, tcp_port))
    print(f"Connected to Player A's game server at {player_a_ip}:{tcp_port}")

    while True:
        data = sock.recv(1024)
        if not data:
            print("Connection closed by server.")
            break
        message = data.decode()
        print(f"Server says: {message}")

        if message == "MAKE_MOVE":
            move = input("Enter your move (rock/paper/scissors): ").strip().lower()
            while move not in ['rock', 'paper', 'scissors']:
                move = input("Invalid move. Enter your move (rock/paper/scissors): ").strip().lower()
            sock.sendall(move.encode())
        elif message.startswith("RESULT"):
            print(message)
        elif message == "GAME_OVER":
            print("Game over.")
            break

    sock.close()

if __name__ == "__main__":
    main()
