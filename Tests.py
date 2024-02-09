#!/usr/bin/env python
import socket, pickle 
import time, datetime 
import threading

"""with socket() as s:
    s.bind(('',0))
    print(s.getsockname()[1])
    time.sleep(0.20)
    s.close() """

import threading

class KeepAliveThread(threading.Thread):

    def __init__(self, value, neighbours):
        # execute the base constructor
        threading.Thread.__init__(self)
        # store the value
        self.interval = value
        self.neighbours = neighbours

    def run(self):
        while True:
            timeval = self.interval
            while timeval > 0:
                timer = datetime.timedelta(seconds = timeval )
                time.sleep(1)
                print(timer)
                timeval -= 1
            print("Woke up " , self.interval)
            for k, j in self.neighbours.items():
                print(k,j)


            
        


def send_message( sock, ip , port, msg ):
    addr = (ip, port)
    sock.sendto( msg.encode(encoding='UTF-8'), addr)
    
    
    
def main():
    print ('hey')
    
    t = [1,3,5,6,7,8,3,4,5,8]
    print(t)
    t_del = []
    for i in range(0, len(t)):
        if t[i] == 3:
            t_del.append(i)
    for d in t_del:
        t.pop(d)
    
    print( t )
            
            
    return
            
        
    
    
    addresses = { 52609 : '127.0.0.1', 50022 : '127.0.0.1' , 61146 : '127.0.0.1' }
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    for key in addresses:
        send_message( client_socket , addresses[key], key , f'I am sending you your key - {key} ')
        time.sleep(1)
    
    client_socket.close() 

if __name__ == "__main__":
    main()

    neighbrs = {'192.67.89.9': 5676, '192.67.9.9': 5670, '192.70.89.9': 5679,'192.7.89.9': 5678}
    t = KeepAliveThread(3, neighbrs)
    t1 = KeepAliveThread(7, neighbrs)
    t2 = KeepAliveThread(4, neighbrs)
    t.start()
    t1.start()
    t2.start()
    
    
    
    
    