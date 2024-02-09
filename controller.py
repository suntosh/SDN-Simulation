#!/usr/bin/env python

"""This is the Controller Starter Code for ECE50863 Lab Project 1
Author: Xin Du
Email: du201@purdue.edu
Last Modified Date: December 9th, 2021
"""

import sys
import socket, pickle, time, os
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
        self.bad_routes = []
        self.num_of_switches = 0
        self.active_nodes = 0 
        self.list_of_registered_switches = {}
        self.controller_socket = None 
        self.dead_links = []
        self.routing_tables = None
    
    def reset_structures(self):
        self.network_table.clear()
        self.switch_nodes.clear()
        self.cost_sheet.clear()
        self.bad_routes.clear()
        self.nodes.clear()
    

    def buildNetworkTable(self):
        self.reset_structures()
        if self.raw_lines is None:
            with open(self.fileName) as f:
                self.raw_lines = f.readlines()
                print(self.raw_lines)
                f.close()
            
        for line in self.raw_lines:
            src = None
            dest = None
            cost = None 
            #print(' this line ', line)
            line = line.strip()
            if ( len(line) == 1 ):
                self.num_of_switches = int(line)
                continue
            process = True
            route = line.split() # Eliminating broken links 
            src = int(route[0])
            dest = int(route[1])
            cost = int(route[2]) 
            for d in self.dead_links:
                if d == src or d == dest:
                    process = False
            if ( process == False ):
                self.bad_routes.append( [src, dest , -1 , 9999] )
                continue

            #print('Them raw lines ', line)
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

        for row in self.bad_routes:
            topology_update_link_dead(row[0], row[1])
            
        self.routing_tables = routing_table + self.bad_routes
        return self.routing_tables
    
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
            
    def dispatch_switch_addresses(self):
        for k in self.list_of_registered_switches.values():
            self.controller_socket.sendto( pickle.dumps(['LOCATIONS',self.list_of_registered_switches]), ( k.addr , k.port))
    
    def add_dead_link(self, bl):
        self.dead_links.append(bl) 

    def Start_Server(self, port):
    
        print("Creating socket")
        self.controller_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # not SOCK_STREAM, which is for TCP. We want UDP, which requires SOCK_DGRAM

        print(f"Binding socket to ip_addr {IP} and port {port}")
        self.controller_socket.bind((IP, int(port)))

        print(f"We've now bound the socket to {self.controller_socket.getsockname()}, so we can now send messages to the server by specifying its address in sendto")
        
        registered = 0; 
        
        print("started process", os.getpid())

        while True:

            (data, client_addr) = self.controller_socket.recvfrom(1024) # Client address really is a tuple of (ip_addr, port number) from the sender

            print(f"Recieved message from client")
            
            data =  data.decode('utf-8')
            data = data.split()
            if data[0].startswith('SWITCH_ALIVE'):
                mn = int(data[1])
                if mn in self.dead_links:
                    topology_update_switch_alive(mn)
                    self.dead_links.remove(mn)
                    routing_tables  =  self.generate_routing_table()
                data=''
                continue
            
            if data[0].startswith('SWITCH_DEAD') or data[0].startswith('LINK_DOWN'):
                mn = int(data[1])
                if mn not in self.dead_links:
                    if data[0].startswith('SWITCH_DEAD'):
                        topology_update_switch_dead(mn)
                    self.dead_links.append(mn)
                    routing_tables  =  self.generate_routing_table()
                    routing_table_update(routing_tables)
                    for  nd in self.list_of_registered_switches.values() :
                        route_update = ['ROUTE_UPDATE']
                        if int(nd.id) not in self.dead_links:
                            for row in self.routing_tables:
                                if ( data[0].startswith('LINK_DOWN') and int(row[2]) == -1):
                                    topology_update_link_dead(row[0], row[1])
                                if int(nd.id) == int(row[0]):
                                    route_update.append([row[0],row[1],row[2]])
                                if int(nd.id) == int(row[1]) and int(row[2]) == -1:
                                    route_update.append([row[1],row[0],row[2]])
                            self.controller_socket.sendto( pickle.dumps(route_update), (nd.addr, nd.port))

                data=''
                continue
            
                            
            network_switch =  NetworkSwitch( data[0].strip(), client_addr[0], client_addr[1])
            self.list_of_registered_switches[data[0].strip()] = network_switch
            register_request_received(network_switch.id)
            if int(network_switch.id) in self.dead_links:
                    self.dead_links.remove(mn)
                    
            register_response = "\r\n"+str(network_switch.id)+"\r\n"

            for nd in self.list_of_registered_switches.values():
                register_response += str(nd.id)+" "+nd.addr+" "+str(nd.port)+"\r\n"

            registered += 1

            print(f"Acknowledged Register Request for Switch { network_switch.id }")

            self.controller_socket.sendto(register_response.encode('UTF-8'), client_addr)
           
            if ( registered >= self.num_of_switches) :
                self.generate_routing_table()
                routing_table_update(self.routing_tables)
                for nd in self.list_of_registered_switches.values() :
                    route_update = ['ROUTE_UPDATE']
                    for row in self.routing_tables:
                        if int(nd.id) == int(row[0]):
                            route_update.append([row[0],row[1],row[2]])
                        if int(nd.id) == int(row[1]) and int(row[2]) == -1:
                            route_update.append([row[1],row[0],row[2]])
                    self.controller_socket.sendto( pickle.dumps(route_update), (nd.addr, nd.port))

            

                self.dispatch_switch_addresses()

                
            
                    
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



def main():
    
    # This is good 
    num_args = len(sys.argv)
    if num_args < 3:
        print ("Usage: python controller.py <port> <config file>\n")
        sys.exit(1)

    print(sys.argv)
    network =  NetworkGraph(sys.argv[2])
    
   
    
    network.generate_routing_table()
    network.dump_network()
    #print( routing_tables)
    
    network.Start_Server( int(sys.argv[1]))
  
    return
    
    
    
    
if __name__ == "__main__":
    main()












""" Code References

#https://gist.github.com/gabrielfalcao/20e567e188f588b65ba2
#https://www.bogotobogo.com/python/Multithread/python_multithreading_subclassing_creating_threads.php
#https://www.udacity.com/blog/2021/09/create-a-timer-in-python-step-by-step-guide.html

"""