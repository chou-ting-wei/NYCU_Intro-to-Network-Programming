# player_a.py
# UDP Client and TCP Server

import socket
import threading
import time

def main():
    available_players = scan_for_players()

    if not available_players:
        print("No available players found.")
        return

    print("Available players:")
    for idx, player in enumerate(available_players):
        print(f"{idx+1}. {player}")

    while True:
        try:
            choice = int(input("Select a player to invite (number), or enter 0 to exit: "))
            if choice == 0:
                print("Exiting the program...")
                exit() 
            elif 1 <= choice <= len(available_players):
                break
            else:
                print(f"Please enter a number between 1 and {len(available_players)}, or 0 to exit.")
        except ValueError:
            print("Invalid input. Please enter a valid number.")

    selected_player = available_players[choice - 1]
    player_ip, player_port = selected_player.split(':')

    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    message = "GAME_INVITATION"
    udp_sock.sendto(message.encode(), (player_ip, int(player_port)))
    print(f"Invitation sent to {player_ip}:{player_port}")

    udp_sock.settimeout(10)
    try:
        data, addr = udp_sock.recvfrom(1024)
        response = data.decode()
        if response == "ACCEPTED":
            print("Invitation accepted.")

            tcp_port = 19000 
            threading.Thread(target=start_tcp_server, args=(tcp_port,)).start()
            time.sleep(1)  # Give some time for TCP server to start
            udp_sock.sendto(str(tcp_port).encode(), (player_ip, int(player_port)))
            print(f"Sent TCP port info to Player B: {tcp_port}")
        else:
            print("Invitation declined.")
    except socket.timeout:
        print("No response received. Invitation timed out.")

def scan_for_players():
    servers = [
        '140.113.235.151',  # linux1.cs.nycu.edu.tw
        '140.113.235.152',  # linux2.cs.nycu.edu.tw
        '140.113.235.153',  # linux3.cs.nycu.edu.tw
        '140.113.235.154',  # linux4.cs.nycu.edu.tw
    ]

    port_range = range(18000, 18010) 
    available_players = []

    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.settimeout(0.5)

    for server in servers:
        for port in port_range:
            udp_sock.sendto(b"ARE_YOU_AVAILABLE", (server, port))

    start_time = time.time()
    while time.time() - start_time < 2: 
        try:
            data, addr = udp_sock.recvfrom(1024)
            response = data.decode()
            if response == "AVAILABLE":
                available_players.append(f"{addr[0]}:{addr[1]}")
        except socket.timeout:
            break

    udp_sock.close()
    return available_players

def start_tcp_server(tcp_port):
    tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_sock.bind(('', tcp_port))
    tcp_sock.listen(1)
    print(f"TCP game server started on port {tcp_port}, waiting for Player B to connect...")

    conn, addr = tcp_sock.accept()
    print(f"Player B connected from {addr}")

    play_game(conn)

    conn.close()
    tcp_sock.close()

def play_game(conn):
    moves = ['rock', 'paper', 'scissors']

    conn.sendall("MAKE_MOVE".encode())

    player_a_move = input("Enter your move (rock/paper/scissors): ").strip().lower()
    while player_a_move not in moves:
        player_a_move = input("Invalid move. Enter your move (rock/paper/scissors): ").strip().lower()

    data = conn.recv(1024)
    player_b_move = data.decode().strip().lower()
    print(f"Player B chose: {player_b_move}")

    result = determine_winner(player_a_move, player_b_move)
    result_message = f"RESULT: Player A chose {player_a_move}, Player B chose {player_b_move}. {result}"
    print(result_message)
    conn.sendall(result_message.encode())
    conn.sendall("GAME_OVER".encode())

def determine_winner(move_a, move_b):
    if move_a == move_b:
        return "It's a tie!"
    elif (move_a == 'rock' and move_b == 'scissors') or \
         (move_a == 'paper' and move_b == 'rock') or \
         (move_a == 'scissors' and move_b == 'paper'):
        return "Player A wins!"
    else:
        return "Player B wins!"

if __name__ == "__main__":
    main()
