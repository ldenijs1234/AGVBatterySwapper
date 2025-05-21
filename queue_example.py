# Example Queues
# Salabim Discrete Event Simulation
#
# Author: Mark Duinkerken
# 2020-06-11
# 
# ordergenerator generates orders from inputfile
# ordermanager checks the order portfolio at regular intervals 


import salabim as sim


# PARAMETERS

# orders
OrderFile = 'orders.txt'


# CLASS DEFINITIONS: attributes and process

class TOrderGenerator (sim.Component):
    def setup (self, Name):                            
        self.FileName = Name

    def process (self):
        with sim.ItemFile(self.FileName) as f:
            while True:
                NextTime = f.read_item_float ()             # each line in inputfile starts with a time
                yield self.hold(till=NextTime)              # wait until next order arrives
                Nr   = f.read_item_int ()                   # read order number
                ClNr = f.read_item_int ()                   # read client number
                NrP  = f.read_item_int ()                   # read number of products in order
                NewOrder = TOrder (a=Nr, b=ClNr, c=NrP)     # create new order             
                NewOrder.enter (Manager.OrderQueue)         # put new order in the orer queue of the 'manager'
        
    
class TOrder (sim.Component):
    def setup (self, a, b, c):
        self.OrderNr    = a
        self.ClientNr   = b
        self.NrProducts = c
                

class TManager (sim.Component):
    def setup (self):
        self.OrderQueue = sim.Queue ('AllOrders') 

    def countproducts (self):                               # this procedure calculates the sum of all products of all orders
        total = 0                                           # start at zero
        order = self.OrderQueue.head()                      # begin with the first order in the queue
        while order != None:                                # while the order exists (thus not referring to 'nothing')
            total = total + order.NrProducts                # add the NrProducts of this order
            order = self.OrderQueue.successor (order)       # order now points to the next order (or to 'nothing' at the end of the queue)
        return total                                        # procedure returns the total number of products
    
    def smallestorder (self):                               # this procedure returns the order with the least number of products
        order = self.OrderQueue.head()                      # works similar to the example above
        smallest = order
        while order != None:
            if order.NrProducts < smallest.NrProducts:
                smallest = order
            order = self.OrderQueue.successor (order)
        return smallest                                     # procedure returns an order
            
    def process (self):
        while True:
            yield self.hold (100)
            print ('\nAantal orders: %d. Aantal products %d' % (self.OrderQueue.length (), self.countproducts ()) )
            orderx = self.smallestorder ()
            print ('Smallest order %d for client %d has %d products\n' % (orderx.OrderNr, orderx.ClientNr, orderx.NrProducts))

   
# INITIALIZATION

env = sim.Environment (trace = True)

Manager = TManager ()
OrderGenerator = TOrderGenerator (Name = OrderFile)

env.run (1001)


# PRINT RESULTS

print ('\n')
Manager.OrderQueue.print_statistics ()

print ('\nREADY')
