#!/usr/bin/env python

"""This is the Switch Starter Code for ECE50863 Lab Project 1
Author: Xin Du
Email: du201@purdue.edu
Last Modified Date: December 9th, 2021
"""

import sys, os
from datetime import date, datetime
import socket, pickle , threading, time

# Please do not modify the name of the log file, otherwise you will lose points because the grader won't be able to find your log file
LOG_FILE = "switch#.log" # The log file for switches are switch#.log, where # is the id of that switch (i.e. switch0.log, switch1.log). The code for replacing # with a real number has been given to you in the main function.

# Those are logging functions to help you follow the correct logging standard

# "Register Request" Format is below:
#
# Timestamp
# Register Request Sent

#globals 
ROUTING_TABLE = {}
LOCATIONS = {}
SWITCH_ID = -1
BAD_SWITCH = -1 
NEIGHBOUR_SWITCH_STATUS = {}
K = 2

def register_request_sent():
    log = []
    log.append(str(datetime.time(datetime.now())) + "\n")
    log.append(f"Register Request Sent\n")
    write_to_log(log)

# "Register Response" Format is below:
#
# Timestamp
# Register Response Received

def register_response_received():
    log = []
    log.append(str(datetime.time(datetime.now())) + "\n")
    log.append(f"Register Response received\n")
    write_to_log(log) 

# For the parameter "routing_table", it should be a list of lists in the form of [[...], [...], ...]. 
# Within each list in the outermost list, the first element is <Switch ID>. The second is <Dest ID>, and the third is <Next Hop>.
# "Routing Update" Format is below:
#
# Timestamp
# Routing Update 
# <Switch ID>,<Dest ID>:<Next Hop>
# ...
# ...
# Routing Complete
# 
# You should also include all of the Self routes in your routing_table argument -- e.g.,  Switch (ID = 4) should include the following entry: 		
# 4,4:4

def routing_table_update(routing_table):
    log = []
    log.append(str(datetime.time(datetime.now())) + "\n")
    log.append("Routing Update\n")
    for row in routing_table:
        log.append(f"{row[0]},{row[1]}:{row[2]}\n")
    log.append("Routing Complete\n")
    write_to_log(log)

# "Unresponsive/Dead Neighbor Detected" Format is below:
#
# Timestamp
# Neighbor Dead <Neighbor ID>

class NetworkSwitch(object):

    def __init__(self, id, addr, port):
        self.id = id 
        self.addr = addr
        self.port = port

    def __str__(self):
        return f'{self.id} {self.addr} {self.port}'


class KeepAliveThread(threading.Thread):

    def __init__(self, keep_alive_value):
        # execute the base constructor
        threading.Thread.__init__(self)
        # store the value
        self.interval = keep_alive_value
        print('Thread Created', flush= True)
        
        
    def run(self):
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        while True:
            timeval = self.interval
            while timeval > 0:
                time.sleep(1)
                timeval -= 1
            
         
            for k, j in ROUTING_TABLE.items():
                if  j != -1 and k != SWITCH_ID:
                    nt = LOCATIONS[k]
                    client_socket.sendto(pickle.dumps(['KEEP_ALIVE', SWITCH_ID]),( nt.addr, nt.port ))
            



def neighbor_dead(switch_id):
    log = []
    log.append(str(datetime.time(datetime.now())) + "\n")
    log.append(f"Neighbor Dead {switch_id}\n")
    write_to_log(log) 

# "Unresponsive/Dead Neighbor comes back online" Format is below:
#
# Timestamp
# Neighbor Alive <Neighbor ID>

def neighbor_alive(switch_id):
    log = []
    log.append(str(datetime.time(datetime.now())) + "\n")
    log.append(f"Neighbor Alive {switch_id}\n")
    write_to_log(log) 

def write_to_log(log):
    with open(LOG_FILE, 'a+') as log_file:
        log_file.write("\n\n")
        # Write to log
        log_file.writelines(log)


def process_data(data):
     network_data = pickle.loads(data)
     global ROUTING_TABLE
     global LOCATIONS

     if network_data[0] == 'ROUTE_UPDATE':
        network_data.pop(0)
        routing_table_update( network_data )
        for rte in network_data:
            ROUTING_TABLE[rte[1]] = rte[2]
     elif network_data[0] == 'LOCATIONS':
        network_data.pop(0)
        print('LOCATIONS' , network_data)
        for j,k in network_data[0].items():
            print(j, '  ', k)
            LOCATIONS[int(j)] = k
     elif network_data[0] == 'KEEP_ALIVE':
         NEIGHBOUR_SWITCH_STATUS[network_data[1]] = datetime.now()

     for j,k in NEIGHBOUR_SWITCH_STATUS.items():
         if k != -1: 
            diff = datetime.now() - k
            if diff.total_seconds() > float(( K * 3)):
                NEIGHBOUR_SWITCH_STATUS[j] = -1
                print( 'Switch ', j , 'dead')
     
     print(network_data)


def Socket_Client(switchid, port):
        
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    msg = f'{switchid} Register_Request'.encode(encoding='UTF-8')

    # This is the server address, which we hard coded in server.py
    addr = ("127.0.0.1", port)

    # Before sending the socket is unbound, and hence has no ability to receieve data
    #print(f"Before sending data the socket address is {client_socket.getsockname()}")

    client_socket.sendto(msg, addr)
    register_request_sent()

    print(f"The socket is now bound to {client_socket.getsockname()}")
    print(f"Recieving data from client")
   
    registered = False 
    while True: 
        (data, server_addr) = client_socket.recvfrom(1024)

        
        if registered == False:
            print(f"Server Response is '{data.decode('utf-8')}'")
            register_response_received()
            registered = True
        else:
           process_data(data)

       
    return None


def main():

    global LOG_FILE

    global BAD_SWITCH

    print("started process", os.getpid())

    #Check for number of arguments and exit if host/port not provided
    num_args = len(sys.argv)
    if num_args < 4:
        print ("switch.py <Id_self> <Controller hostname> <Controller Port>\n")
        sys.exit(1)

    if num_args == 5:
        BAD_SWITCH = int(sys.argv[4])

    my_id = int(sys.argv[1])
    LOG_FILE = 'switch' + str(my_id) + ".log" 

    global SWITCH_ID
    SWITCH_ID = my_id 

    t = KeepAliveThread(5)
    t.start()
    print( t.is_alive)
    Socket_Client( sys.argv[1], int(sys.argv[3]))
    # Write your code below or elsewhere in this file
    t.join()

if __name__ == "__main__":
    main()