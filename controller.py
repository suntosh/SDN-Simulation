#!/usr/bin/env python

"""This is the Controller Starter Code for ECE50863 Lab Project 1
Author: Xin Du
Email: du201@purdue.edu
Last Modified Date: December 9th, 2021
"""

import sys
import socket, pickle
from datetime import date, datetime

# Please do not modify the name of the log file, otherwise you will lose points because the grader won't be able to find your log file
LOG_FILE = "Controller.log"

# Those are logging functions to help you follow the correct logging standard

# "Register Request" Format is below:
#
# Timestamp
# Register Request <Switch-ID>

IP = '0.0.0.0'
PORT = 3999

class Route(object):

    def __init__(self, from_node, to_node, cost ):
        self.from_node = from_node
        self.to_node = to_node
        self.cost = cost
        self.nexthop = None

    def __str__(self):
        return f'{self.from_node} {self.to_node} {self.cost}'
    
    def toList(self):
        return [self.from_node, self.to_node, self.cost, self.nexthop]


class SwitchNode(object):
    
    def __init__(self, id):
        self.id = id
        self.neighbours = {}

    def add_neighbour(self, id, cost ):
        self.neighbours[id] = cost

    def __str__(self):
        return f'{self.id} -- {self.neighbours}'

class NetworkSwitch(object):

    def __init__(self, id, addr, port):
        self.id = id 
        self.addr = addr
        self.port = port

    def __str__(self):
        return f'{self.id} {self.addr} {self.port}'

class NetworkGraph(object):
      
    def __init__(self, filename):
        self.fileName = filename
        self.network_table = []
        self.switch_nodes = {}
        self.nodes = []
        self.cost_sheet = {} 
        self.raw_lines = None 
    
    def buildNetworkTable(self):
        with open(self.fileName) as f:
            self.raw_lines = f.readlines()
            f.close()
        
        
        
        for line in self.raw_lines:
            line = line.strip()
            if ( len(line) == 1 ):
                self.num_nodes = int(line)
            else:
                route = line.split()
                src = int(route[0])
                dest = int(route[1])
                cost = int(route[2]) 
                rte = Route( src, dest, cost  )
                self.network_table.append( rte )
                self.nodes.append(src)
                self.nodes.append(dest)
                str_rte = f'{src}, {dest}'
                self.cost_sheet[str_rte] = cost
                str_rte = f'{dest}, {src}'
                self.cost_sheet[str_rte] = cost
                if src not in self.switch_nodes:
                    self.switch_nodes[src] = SwitchNode(src)
                self.switch_nodes[src].add_neighbour(dest, cost)
                if dest not in self.switch_nodes:
                    self.switch_nodes[dest] = SwitchNode(dest)
                self.switch_nodes[dest].add_neighbour(src, cost)

        self.nodes =  sorted(set(self.nodes))
        return None


    def remove_dead_link( self, node_id ):
        """marked_for_removal = None
        for i in range(0, len(self.network_table)) :
            if self.network_table[i].from_node == node_id or self.network_table.to_node == node_id:
                marked_for_removal.append(i)
        for i in marked_for_removal:
            self.network_table.pop(i)"""
            
        """self.nodes.remove( node_id)
        remove_cost = []
        for key in self.cost_sheet.keys():
            if str(3) in key:
                remove_cost.append(key)
                print(key)
                
        for k in remove_cost:
            del self.cost_sheet[k]"""
            
        
            
    
                 

    def compute_shortest_paths(self):
        self.buildNetworkTable()
        shortest_paths= {}
        for i in self.nodes:
            for j in self.nodes:
                paths = {}
                if ( i == j ):
                    path = f'{i}, {j}'
                    shortest_paths[path] = 0
                else:
                    self.recursive_graph_pathing( i, j , paths , [i],0)
                    cheapest_cost = sorted(paths.values())[0]
                    path_with_least_hops = [x for x,v in paths.items() if int(v) == cheapest_cost]
                    shortest_paths[sorted(path_with_least_hops, key=len)[0]] = cheapest_cost
                    shortest_paths = {key.strip("[]"): item for key, item in shortest_paths.items()}
        return shortest_paths

    def generate_routing_table(self):
        shortest_paths = self.compute_shortest_paths()
        routing_table = []
        for key in shortest_paths:
            nodes = key.split(',')
            if (len(nodes) == 2):
                if nodes[0].strip() != nodes[1].strip():
                    routing_table.append( [ int(nodes[0]), int(nodes[1]), int(nodes[1]), self.cost_sheet[nodes[0]+','+nodes[1]] ] )
                else:
                    routing_table.append( [ int(nodes[0]), int(nodes[1]), int(nodes[1]), 0 ] )
            else:
                routing_table.append( [ int(nodes[0]), int(nodes[len(nodes)-1]), int(nodes[1]), self.cost_sheet[nodes[0]+','+nodes[1]] ] )

        return routing_table
    
    def recursive_graph_pathing(self, src, dest , hops, path, cost):
        node = self.switch_nodes[src]
        neighbours = node.neighbours
        for i in neighbours:
             if dest == i :
                path_copy1 = path[:]
                path_copy1.append(i) 
                hops[ str(path_copy1) ] = neighbours[i] +cost
             else:
                if ( i not in path ):
                    path_copy2 = path[:]
                    path_copy2.append(i) 
                    self.recursive_graph_pathing( i , dest , hops, path_copy2, cost + neighbours[i])
               
    def toList(self):
        routing_table = []
        for route in self.network_table:
            routing_table.append( route.toList() )
        return routing_table

    
    def dump_network(self):
        for route in self.network_table:
            print(route)


def register_request_received(switch_id):
    log = []
    log.append(str(datetime.time(datetime.now())) + "\n")
    log.append(f"Register Request {switch_id}\n")
    write_to_log(log)

# "Register Responses" Format is below (for every switch):
#
# Timestamp
# Register Response <Switch-ID>

def register_response_sent(switch_id):
    log = []
    log.append(str(datetime.time(datetime.now())) + "\n")
    log.append(f"Register Response {switch_id}\n")
    write_to_log(log) 

# For the parameter "routing_table", it should be a list of lists in the form of [[...], [...], ...]. 
# Within each list in the outermost list, the first element is <Switch ID>. The second is <Dest ID>, and the third is <Next Hop>, and the fourth is <Shortest distance>
# "Routing Update" Format is below:
#
# Timestamp
# Routing Update 
# <Switch ID>,<Dest ID>:<Next Hop>,<Shortest distance>
# ...
# ...
# Routing Complete
#
# You should also include all of the Self routes in your routing_table argument -- e.g.,  Switch (ID = 4) should include the following entry: 		
# 4,4:4,0
# 0 indicates ‘zero‘ distance
#
# For switches that can’t be reached, the next hop and shortest distance should be ‘-1’ and ‘9999’ respectively. (9999 means infinite distance so that that switch can’t be reached)
#  E.g, If switch=4 cannot reach switch=5, the following should be printed
#  4,5:-1,9999
#
# For any switch that has been killed, do not include the routes that are going out from that switch. 
# One example can be found in the sample log in starter code. 
# After switch 1 is killed, the routing update from the controller does not have routes from switch 1 to other switches.

def routing_table_update(routing_table):
    log = []
    log.append(str(datetime.time(datetime.now())) + "\n")
    log.append("Routing Update\n")
    for row in routing_table:
        log.append(f"{row[0]},{row[1]}:{row[2]},{row[3]}\n")
    log.append("Routing Complete\n")
    write_to_log(log)

# "Topology Update: Link Dead" Format is below: (Note: We do not require you to print out Link Alive log in this project)
#
#  Timestamp
#  Link Dead <Switch ID 1>,<Switch ID 2>

def topology_update_link_dead(switch_id_1, switch_id_2):
    log = []
    log.append(str(datetime.time(datetime.now())) + "\n")
    log.append(f"Link Dead {switch_id_1},{switch_id_2}\n")
    write_to_log(log) 

# "Topology Update: Switch Dead" Format is below:
#
#  Timestamp
#  Switch Dead <Switch ID>

def topology_update_switch_dead(switch_id):
    log = []
    log.append(str(datetime.time(datetime.now())) + "\n")
    log.append(f"Switch Dead {switch_id}\n")
    write_to_log(log) 

# "Topology Update: Switch Alive" Format is below:
#
#  Timestamp
#  Switch Alive <Switch ID>

def topology_update_switch_alive(switch_id):
    log = []
    log.append(str(datetime.time(datetime.now())) + "\n")
    log.append(f"Switch Alive {switch_id}\n")
    write_to_log(log) 

def write_to_log(log):
    with open(LOG_FILE, 'a+') as log_file:
        log_file.write("\n\n")
        # Write to log
        log_file.writelines(log)



def  Start_Server(port, num_of_switches , routing_tables):
    
    print("Creating socket")
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # not SOCK_STREAM, which is for TCP. We want UDP, which requires SOCK_DGRAM

    print(f"Binding socket to ip_addr {IP} and port {port}")
    server_socket.bind((IP, int(port)))

    print(f"We've now bound the socket to {server_socket.getsockname()}, so we can now send messages to the server by specifying its address in sendto")
    
    registered = 0; 
    list_of_registered_switches = [] 

    while True:

        (data, client_addr) = server_socket.recvfrom(1024) # Client address really is a tuple of (ip_addr, port number) from the sender

        print(f"Recieved message from client")
        
        data =  data.decode('utf-8')
        data = data.split()
        network_switch =  NetworkSwitch( data[0].strip(), client_addr[0], client_addr[1])
        list_of_registered_switches.append(network_switch)
        register_request_received(network_switch.id)
        register_response = "\r\n"+str(network_switch.id)+"\r\n"

        for nd in list_of_registered_switches:
            register_response += str(nd.id)+" "+nd.addr+" "+str(nd.port)+"\r\n"

        registered += 1

        print(f"Acknowledged Register Request for Switch { network_switch.id }")

        # Note that we're using sendto and recvfrom for both the client and server examples. These functions don't require a connection (ie. they work with UDP) and are the recommended
        # way to communicate over UDP. Some of the other functions for sockets only work with TCP, but it's not obvious which those are unless you read the
        # documentation, which is a good idea but also somewhat annoying. So we would recommend sticking to these functions.
        #server_socket.sendto(register_response.encode('UTF-8'), client_addr)
        

        server_socket.sendto(register_response.encode('UTF-8'), client_addr)
        print( registered, ' ', num_of_switches)
        if ( registered == num_of_switches):
            for  nd in list_of_registered_switches :
                route_update = []
                for row in routing_tables:
                   if int(nd.id) == int(row[0]):
                        route_update.append([row[0],row[1],row[2]])
                server_socket.sendto( pickle.dumps(route_update), (nd.addr, nd.port))



#Gotta try this 
#https://gist.github.com/gabrielfalcao/20e567e188f588b65ba2
#https://www.bogotobogo.com/python/Multithread/python_multithreading_subclassing_creating_threads.php
#https://www.udacity.com/blog/2021/09/create-a-timer-in-python-step-by-step-guide.html

def open_ephemeral_socket( udp ):
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    udp.bind(('', 0))
    return udp.getsockname()

def test_main():
    #Check for number of arguments and exit if host/port not provided
    udp = None 

    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    udp.bind(('', 0))

    host, port =  udp.getsockname()

    print('udp://{host}:{port}'.format(**locals()))

    if udp is not None:
        print('getting here ')
        (data, client_addr) = udp.recvfrom(1024) # Client address really is a tuple of (ip_addr, port number) from the sender
        print(f"Recieved message from client")
        data =  data.decode('utf-8')
        print(data)

    if udp is not None:
        udp.close()
        print( 'closing the socket')
    
    return 

def main():
    
    # This is good 
    num_args = len(sys.argv)
    if num_args < 3:
        print ("Usage: python controller.py <port> <config file>\n")
        sys.exit(1)

    print(sys.argv)
    network =  NetworkGraph(sys.argv[2])
    #routing_tables  =  network.generate_routing_table()
    
    
    
    network.buildNetworkTable()
    
    print("The raw lines" ,network.raw_lines)
    #network.remove_dead_link(3)
    
    
    print( "The Nodes ", network.nodes )
    
    network.remove_dead_link(3)
    
    print(network.cost_sheet) 
    
    routing_tables = network.generate_routing_table()
    
    
    #routing_table_update( routing_tables )

    #network.buildNetworkTable()  # we need to see how we build our datastructures 
    
    #print(network.fileName)
 
    network.dump_network()
    print("##########################  ROUTING TABLES ####################################\n")
    print(routing_tables)
    
    def add_dead_link( k ):
        routes_to_remove = [] 
        for i in range(0,len(routing_tables)):
            x = -1 
            route_entry = routing_tables[i]
            if route_entry[0] == k and route_entry[1] == k:
                routes_to_remove.append(route_entry)
            elif route_entry[2] == k and route_entry[0] != k and route_entry[1] != k:
                routes_to_remove.append(route_entry)
            elif route_entry[0] == k or route_entry[1] == k:
                route_entry[2] = -1 
                route_entry[3] = 9999
                
        return routes_to_remove
    
    routes_to_remove = add_dead_link(3)
    
    for i in routes_to_remove:
        routing_tables.remove(i)
        
        
    print("\n\n\n")
    
    print(routing_tables) 
        

    
    
    
    print(network.cost_sheet)
    
    
    #Start_Server( sys.argv[1], len(network.nodes), routing_tables )

    
    
    # Write your code below or elsewhere in this file

if __name__ == "__main__":
    main()
