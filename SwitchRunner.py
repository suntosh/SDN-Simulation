#!/usr/bin/env python3

import argparse
import socket
import threading
import subprocess
import random

def send_udp_packet(hostname, port, iteration):
    message = f"{iteration} Register_Request"
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.sendto(message.encode(), (hostname, port))
            print(f"UDP packet {iteration} sent successfully to {hostname}:{port}")
    except Exception as e:
        print(f"Failed to send UDP packet {iteration} to {hostname}:{port}. Error: {e}")

def start_switch(hostname, port, iteration):
    args = ['switch.py', str(iteration), hostname, str(port)]
    try:
        subprocess.run(args, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Failed to start switch {iteration} to {hostname}:{port}. Error: {e}")

def main():
    # Create argument parser
    parser = argparse.ArgumentParser(description="Send UDP packets to a host and port.")
    parser.add_argument("hostname", help="Target hostname")
    parser.add_argument("port", type=int, help="Target port")
    args = parser.parse_args()

    # clean dem logz
    subprocess.run(['rm *.log'], shell=True)

    # NOTE: how to change tests
    test_fn = start_switch

    # Send five UDP packets concurrently
    threads = []
    for i in range(6):
        thread = threading.Thread(target=test_fn, args=(args.hostname, args.port, i))
        threads.append(thread)
        thread.start()

    # Wait for all threads to finish
    for thread in threads:
        thread.join()

    print("All UDP packets sent.")

if __name__ == "__main__":
    main()