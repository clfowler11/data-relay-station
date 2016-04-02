### receiver.py

import serial
import struct
from xbee.zigbee import ZigBee
from sys import platform as _platform

# The max allowed size for an api packet
MAX_PACKET_SIZE = 256


class WriteToFileMiddleware:
    """Take a generator, write each element out to file and
    forward it
    """
    def __init__(self, gen, filename, header):
        print('initing {}'.format(self.__class__))
        self.gen = gen
        self.filename = filename
        self.header = header
        #self.transport = gen.transport

    def data_lines(self):
        # write header line out to file
        print('writing headers')
        with open(self.filename, 'w') as outfile:
            outfile.write("{}\r\n".format(self.header))

        for line in self.gen.data_lines():
            # write element to file
            with open(self.filename, 'a') as outfile:
                outfile.write(str(line).replace('(','').replace(')','').replace('None','') + '\n')
            # re-yield element
            yield line


class Receiver:

    def __init__(self, db_type):
        self.data_shape = {key:struct.Struct(
            ''.join(map(lambda x: x[0], packet))) for key, packet in db_type.iteritems()}

        #Check if all packets have the same size
        self.data_size = self.data_shape[self.data_shape.keys()[0]].size
        for i in xrange(1,len(self.data_shape)):
            if (self.data_shape[i].size != self.data_size):
                print("Data Packets are not the same in size: " + self.data_size + " " + self.data_shape[i].size)
        
        self.expected_packets = self.data_size / MAX_PACKET_SIZE + 1
        self.source_addr = None
        self.source_addr_long = None
        self.packet_type = None
        self.outbound = []
        self.rssi = -100

    def async_tx(self, command):
        """Eventually send a command
        """
        self.outbound.append(command)

    def __enter__(self):
        #Change this to search for USB, Unhardcode the ports
        if _platform == "linux" or _platform == "linux2":
            self.ser = serial.Serial('/dev/ttyUSB0', 38400)#TODO: Change to 115200
        elif _platform == "win32":
            self.ser = serial.Serial('COM5', 38400)#TODO: Change to 115200
        self.xbee = ZigBee(self.ser)
        print 'xbee created/initialized'
        return self

    def data_lines(self):
        while True:
            payload = ''
            for x in xrange(self.expected_packets):

                packet = self.xbee.wait_read_frame()
                while packet.get('id', None) == 'tx_status':
                    print('got tx_status frame')
                    packet = self.xbee.wait_read_frame()
                self.source_addr_long = packet.get(
                        'source_addr_long', self.source_addr_long)
                self.source_addr = packet.get(
                        'source_addr', self.source_addr)

                #TODO: Implement RSSI
                #self.rssi = packet['rssi']
                #print self.rssi

                payload += packet['rf_data']

                # Read first two bytes, to determine packet type
                packet_type = struct.unpack("h",payload[:2])[0]

                #Preallocate space
                stored_data = ()

                # Unpack Struct according to ID, and update global parameters
                for data_type, data_shape in self.data_shape.iteritems():
                    if (packet_type == data_type):
                        stored_data += data_shape.unpack(payload)
                    else:
                        stored_data += tuple([None] * len([i for i in data_shape.format if i != 'x']))
                    

            # let our data be processed - unpacks an array of tuples into one single tuple
            yield stored_data

            # flush the command queue to the xbee
            for cmd in self.outbound:
                self.xbee.tx(dest_addr_long=self.source_addr_long,
                        dest_addr=self.source_addr, data=cmd)
                print("command {}".format(' '.join("0x{:02x}".format(i) for i in cmd)))
                print "sent a command"
            self.outbound = []


    def __exit__(self, type, value, traceback):
        self.xbee = None
        self.ser.close()
        if isinstance(value, serial.SerialException):
            print traceback
            return True
