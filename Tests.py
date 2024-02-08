#!/usr/bin/env python
import socket, pickle 
import time 

"""with socket() as s:
    s.bind(('',0))
    print(s.getsockname()[1])
    time.sleep(0.20)
    s.close() """

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
    
    
    
    
    