# player_b.py
# UDP Server and TCP Client

import socket

def main():
    # Player B's UDP server
    UDP_IP = ''  # Listen on all interfaces
    UDP_PORT = 18000  # Port above 10000

    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((UDP_IP, UDP_PORT))

    print(f"Player B is waiting for game invitations on port {UDP_PORT}...")

    while True:
        data, addr = sock.recvfrom(1024)  # Buffer size is 1024 bytes
        message = data.decode()
        print(f"Received message from {addr}: {message}")

        if message == "ARE_YOU_AVAILABLE":
            # Respond that we are available
            sock.sendto(b"AVAILABLE", addr)
            print(f"Sent availability response to {addr}")
        elif message == "GAME_INVITATION":
            # Ask user to accept or decline
            response = input("Do you want to accept the invitation? (y/n): ").strip().lower()
            if response == 'y':
                # Send acceptance via UDP
                sock.sendto(b"ACCEPTED", addr)
                print("Invitation accepted, waiting for TCP port info...")

                # Receive TCP port info from Player A
                data, addr = sock.recvfrom(1024)
                tcp_port_info = data.decode()
                TCP_PORT = int(tcp_port_info)
                print(f"Received TCP port info from Player A: {TCP_PORT}")

                # Now connect via TCP to Player A
                play_game(addr[0], TCP_PORT)
                print("Game finished. Returning to wait for new invitations.")
            else:
                # Send decline message via UDP
                sock.sendto(b"DECLINED", addr)
                print("Invitation declined, waiting for new invitations...")
        else:
            # Ignore other messages
            pass

def play_game(player_a_ip, tcp_port):
    # TCP client to connect to Player A's TCP server and play the game
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((player_a_ip, tcp_port))
    print(f"Connected to Player A's game server at {player_a_ip}:{tcp_port}")

    # Now play the game (rock-paper-scissors)
    while True:
        # Receive message from server
        data = sock.recv(1024)
        if not data:
            print("Connection closed by server.")
            break
        message = data.decode()
        print(f"Server says: {message}")

        if message == "MAKE_MOVE":
            # Prompt user for move
            move = input("Enter your move (rock/paper/scissors): ").strip().lower()
            while move not in ['rock', 'paper', 'scissors']:
                move = input("Invalid move. Enter your move (rock/paper/scissors): ").strip().lower()
            sock.sendall(move.encode())
        elif message.startswith("RESULT"):
            # Display result
            print(message)
        elif message == "GAME_OVER":
            print("Game over.")
            break

    sock.close()

if __name__ == "__main__":
    main()
